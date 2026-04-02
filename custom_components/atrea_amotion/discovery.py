"""UDP broadcast discovery helpers for Atrea aMotion units."""

from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from ipaddress import IPv4Address
from typing import Any

import requests

from .const import API_TIMEOUT, LOGGER

try:
    import psutil
except ImportError:  # pragma: no cover - Home Assistant normally provides this
    psutil = None

DISCOVERY_PORT = 3210
DISCOVERY_TIMEOUT = 2.0
DISCOVERY_REQUEST = bytes.fromhex("41 44 44 54 00 01 00 06 FF FF FF FF FF FF")
DISCOVERY_MAGIC = b"ADDT"

TLV_TYPE_MAC = 1
TLV_TYPE_IP = 2
TLV_TYPE_MASK = 3
TLV_TYPE_GATEWAY = 11
TLV_TYPE_DHCP = 16
KNOWN_TLV_TYPES = {
    0,
    TLV_TYPE_MAC,
    TLV_TYPE_IP,
    TLV_TYPE_MASK,
    TLV_TYPE_GATEWAY,
    TLV_TYPE_DHCP,
}


@dataclass(slots=True)
class _InterfaceTarget:
    """IPv4 interface broadcast target."""

    name: str
    address: str
    netmask: str
    broadcast: str


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Collect UDP responses for the discovery window."""

    def __init__(self) -> None:
        self.responses: list[tuple[bytes, tuple[str, int], float]] = []

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Store raw UDP responses."""
        self.responses.append((data, addr, time.time()))


def normalize_mac(value: str | None) -> str | None:
    """Normalize MAC-like identifiers for matching."""
    if not value:
        return None

    stripped = "".join(char for char in value if char.isalnum()).lower()
    if len(stripped) != 12:
        return value.strip().lower()
    return ":".join(stripped[index : index + 2] for index in range(0, 12, 2))


def _normalize_identifier(value: Any) -> str | None:
    """Normalize string identifiers for equality checks."""
    if value is None:
        return None
    text = str(value).strip()
    return text.casefold() if text else None


def _octets_from_ipv4(value: str) -> list[int] | None:
    """Convert dotted IPv4 to octets."""
    try:
        return [int(part) for part in value.split(".")]
    except ValueError:
        return None


def _compute_broadcast(address: str, netmask: str) -> str | None:
    """Compute the IPv4 broadcast address from address and netmask."""
    address_octets = _octets_from_ipv4(address)
    netmask_octets = _octets_from_ipv4(netmask)
    if address_octets is None or netmask_octets is None:
        return None
    if len(address_octets) != 4 or len(netmask_octets) != 4:
        return None

    try:
        return ".".join(
            str(ip_octet | (255 - mask_octet))
            for ip_octet, mask_octet in zip(address_octets, netmask_octets, strict=True)
        )
    except ValueError:
        return None


def _enumerate_ipv4_targets() -> list[_InterfaceTarget]:
    """Enumerate IPv4 broadcast targets on non-loopback interfaces."""
    if psutil is None:
        LOGGER.debug("psutil is unavailable; UDP discovery cannot enumerate interfaces")
        return []

    targets: list[_InterfaceTarget] = []
    for interface_name, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            if not address.address or not address.netmask:
                continue
            try:
                ip_address = IPv4Address(address.address)
            except ValueError:
                continue
            if ip_address.is_loopback:
                continue

            broadcast = _compute_broadcast(address.address, address.netmask)
            if broadcast is None:
                continue

            targets.append(
                _InterfaceTarget(
                    name=interface_name,
                    address=address.address,
                    netmask=address.netmask,
                    broadcast=broadcast,
                )
            )

    return targets


def _decode_mac(value: bytes) -> str:
    """Decode MAC bytes."""
    return ":".join(f"{octet:02x}" for octet in value)


def _decode_ipv4(value: bytes) -> str:
    """Decode IPv4 bytes."""
    return ".".join(str(octet) for octet in value)


def parse_discovery_response(
    payload: bytes,
    source: tuple[str, int],
    seen: float | None = None,
) -> dict[str, Any] | None:
    """Parse one UDP discovery response packet."""
    if len(payload) < 8:
        return None
    if payload[0:4] != DISCOVERY_MAGIC or payload[4] != 0 or payload[5] != 2:
        return None

    device: dict[str, Any] = {
        "raw": payload,
        "seen": seen if seen is not None else time.time(),
        "mac": None,
        "ip": None,
        "mask": None,
        "gateway": None,
        "dhcp": None,
        "source_ip": source[0],
        "source_port": source[1],
    }

    offset = 8
    while offset + 2 <= len(payload):
        tlv_type = payload[offset]
        tlv_length = payload[offset + 1]
        offset += 2
        next_offset = offset + tlv_length
        if next_offset > len(payload):
            break
        value = payload[offset:next_offset]
        offset = next_offset

        if tlv_type not in KNOWN_TLV_TYPES:
            break
        if tlv_type == 0:
            continue
        if tlv_type == TLV_TYPE_MAC:
            device["mac"] = _decode_mac(value)
        elif tlv_type == TLV_TYPE_IP:
            device["ip"] = _decode_ipv4(value)
        elif tlv_type == TLV_TYPE_MASK:
            device["mask"] = _decode_ipv4(value)
        elif tlv_type == TLV_TYPE_GATEWAY:
            device["gateway"] = _decode_ipv4(value)
        elif tlv_type == TLV_TYPE_DHCP:
            device["dhcp"] = bool(value and value[0] > 0)

    return device


def _deduplicate_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate responses by MAC with IP fallback."""
    deduplicated: dict[str, dict[str, Any]] = {}

    for device in devices:
        key = normalize_mac(device.get("mac")) or device.get("ip") or device.get("source_ip")
        if key is None:
            continue

        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = device
            continue

        for field in (
            "mac",
            "ip",
            "mask",
            "gateway",
            "dhcp",
            "source_ip",
            "source_port",
        ):
            if existing.get(field) is None and device.get(field) is not None:
                existing[field] = device[field]

        if device.get("seen", 0) > existing.get("seen", 0):
            existing["seen"] = device["seen"]
            existing["raw"] = device["raw"]

    return sorted(
        deduplicated.values(),
        key=lambda item: (item.get("ip") or item.get("source_ip") or "", item.get("mac") or ""),
    )


async def async_discover_devices(
    timeout: float = DISCOVERY_TIMEOUT,
) -> list[dict[str, Any]]:
    """Broadcast the proprietary UDP discovery request and collect responses."""
    loop = asyncio.get_running_loop()
    targets = _enumerate_ipv4_targets()
    if not targets:
        LOGGER.debug("No non-loopback IPv4 interfaces available for UDP discovery")
        return []

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", 0))

    protocol = _DiscoveryProtocol()
    transport, _ = await loop.create_datagram_endpoint(lambda: protocol, sock=sock)

    try:
        sent_targets: set[str] = set()
        for target in targets:
            LOGGER.debug(
                "Atrea UDP discovery broadcast target=%s interface=%s ip=%s mask=%s",
                target.broadcast,
                target.name,
                target.address,
                target.netmask,
            )
            if target.broadcast in sent_targets:
                continue
            sent_targets.add(target.broadcast)
            transport.sendto(DISCOVERY_REQUEST, (target.broadcast, DISCOVERY_PORT))
            LOGGER.debug(
                "Atrea UDP discovery request sent target=%s:%s raw=%s",
                target.broadcast,
                DISCOVERY_PORT,
                DISCOVERY_REQUEST.hex(" "),
            )

        await asyncio.sleep(timeout)
    finally:
        transport.close()

    parsed_devices: list[dict[str, Any]] = []
    for payload, source, seen in protocol.responses:
        LOGGER.debug(
            "Atrea UDP discovery raw response source=%s:%s raw=%s",
            source[0],
            source[1],
            payload.hex(" "),
        )
        parsed = parse_discovery_response(payload, source, seen)
        if parsed is None:
            continue
        LOGGER.debug("Atrea UDP discovery parsed response=%s", parsed)
        parsed_devices.append(parsed)

    return _deduplicate_devices(parsed_devices)


def _fetch_http_discovery(host: str) -> dict[str, Any] | None:
    """Fetch HTTP discovery metadata from one unit."""
    try:
        response = requests.get(f"http://{host}/api/discovery", timeout=API_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as err:
        LOGGER.debug("HTTP discovery failed for %s: %s", host, err)
        return None

    try:
        payload = response.json()
    except ValueError:
        LOGGER.debug("HTTP discovery returned invalid JSON for %s", host)
        return None

    result = payload.get("result")
    return result if isinstance(result, dict) else None


async def async_enrich_devices(
    hass,
    devices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Augment UDP discovery devices with HTTP discovery metadata."""
    async def _enrich(device: dict[str, Any]) -> dict[str, Any]:
        host = device.get("ip") or device.get("source_ip")
        metadata = None
        if host:
            metadata = await hass.async_add_executor_job(partial(_fetch_http_discovery, host))

        enriched = dict(device)
        if metadata:
            enriched["unit_name"] = metadata.get("name")
            enriched["model"] = metadata.get("type")
            enriched["version"] = metadata.get("version")
            enriched["production_number"] = metadata.get("production_number")
            enriched["board_number"] = metadata.get("board_number")
        else:
            enriched["unit_name"] = None
            enriched["model"] = None
            enriched["version"] = None
            enriched["production_number"] = None
            enriched["board_number"] = None
        return enriched

    return await asyncio.gather(*(_enrich(device) for device in devices))


async def async_discover_enriched_devices(
    hass,
    timeout: float = DISCOVERY_TIMEOUT,
) -> list[dict[str, Any]]:
    """Run UDP discovery and augment each result with HTTP metadata."""
    devices = await async_discover_devices(timeout=timeout)
    if not devices:
        return []
    return await async_enrich_devices(hass, devices)


def _device_match_score(entry_data: Mapping[str, Any], device: Mapping[str, Any]) -> int:
    """Score how well a discovered device matches an existing config entry."""
    score = 0

    entry_network_mac = normalize_mac(entry_data.get("network_mac"))
    device_network_mac = normalize_mac(device.get("mac"))
    if entry_network_mac and device_network_mac and entry_network_mac == device_network_mac:
        score += 100

    entry_board_number = _normalize_identifier(
        entry_data.get("board_number") or entry_data.get("mac")
    )
    device_board_number = _normalize_identifier(device.get("board_number"))
    if entry_board_number and device_board_number and entry_board_number == device_board_number:
        score += 90

    entry_production = _normalize_identifier(entry_data.get("production_number"))
    device_production = _normalize_identifier(device.get("production_number"))
    if entry_production and device_production and entry_production == device_production:
        score += 70

    entry_unit_name = _normalize_identifier(entry_data.get("unit_name"))
    device_unit_name = _normalize_identifier(device.get("unit_name"))
    if entry_unit_name and device_unit_name and entry_unit_name == device_unit_name:
        score += 40

    entry_host = _normalize_identifier(entry_data.get("host"))
    device_ip = _normalize_identifier(device.get("ip") or device.get("source_ip"))
    if entry_host and device_ip and entry_host == device_ip:
        score += 5

    return score


async def async_rediscover_config_entry(
    hass,
    entry_data: Mapping[str, Any],
    timeout: float = DISCOVERY_TIMEOUT,
) -> dict[str, Any] | None:
    """Find the best replacement host for an existing config entry."""
    devices = await async_discover_enriched_devices(hass, timeout=timeout)
    if not devices:
        return None

    ranked = sorted(
        ((device, _device_match_score(entry_data, device)) for device in devices),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked or ranked[0][1] <= 0:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        LOGGER.debug("Rediscovery is ambiguous between devices: %s", ranked[:2])
        return None

    matched_device, score = ranked[0]
    LOGGER.debug("Rediscovery matched device score=%s device=%s", score, matched_device)
    return dict(matched_device)
