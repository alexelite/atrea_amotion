"""UDP broadcast discovery helpers for Atrea aMotion units."""

from __future__ import annotations

import asyncio
import getpass
import socket
import struct
import time
from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Any

import msgpack

from .const import LOGGER

try:
    import psutil
except ImportError:  # pragma: no cover - Home Assistant normally provides this
    psutil = None

try:
    import fcntl
except ImportError:  # pragma: no cover - not available on every platform
    fcntl = None

DISCOVERY_PORT = 8210
DISCOVERY_TIMEOUT = 2.0
DISCOVERY_REQUIRED_FIELDS = {"board_number", "name", "type", "version"}

SIOCGIFADDR = 0x8915
SIOCGIFNETMASK = 0x891B


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
    if psutil is not None:
        targets = _enumerate_ipv4_targets_psutil()
        if targets:
            return targets
        LOGGER.debug("psutil did not return usable IPv4 targets, falling back to ioctl enumeration")

    targets = _enumerate_ipv4_targets_ioctl()
    if not targets:
        LOGGER.debug("No non-loopback IPv4 interfaces available for UDP discovery")
    return targets


def _enumerate_ipv4_targets_psutil() -> list[_InterfaceTarget]:
    """Enumerate IPv4 targets via psutil when available."""
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


def _ioctl_ipv4_value(sock: socket.socket, interface_name: str, command: int) -> str | None:
    """Read one IPv4 interface value via ioctl."""
    if fcntl is None:
        return None

    try:
        request = struct.pack("256s", interface_name[:15].encode("utf-8"))
        result = fcntl.ioctl(sock.fileno(), command, request)
    except OSError:
        return None
    return socket.inet_ntoa(result[20:24])


def _enumerate_ipv4_targets_ioctl() -> list[_InterfaceTarget]:
    """Enumerate IPv4 targets using only the standard library."""
    if fcntl is None or not hasattr(socket, "if_nameindex"):
        return []

    targets: list[_InterfaceTarget] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for _, interface_name in socket.if_nameindex():
            address = _ioctl_ipv4_value(sock, interface_name, SIOCGIFADDR)
            netmask = _ioctl_ipv4_value(sock, interface_name, SIOCGIFNETMASK)
            if not address or not netmask:
                continue
            try:
                ip_address = IPv4Address(address)
            except ValueError:
                continue
            if ip_address.is_loopback:
                continue

            broadcast = _compute_broadcast(address, netmask)
            if broadcast is None:
                continue

            targets.append(
                _InterfaceTarget(
                    name=interface_name,
                    address=address,
                    netmask=netmask,
                    broadcast=broadcast,
                )
            )
    return targets


def _is_valid_discovery_payload(payload: dict[str, Any]) -> bool:
    """Return whether a decoded payload looks like a unit discovery response."""
    return bool(DISCOVERY_REQUIRED_FIELDS.intersection(payload))


def _build_discovery_request(interface_name: str) -> bytes:
    """Build the MessagePack discovery request for one interface."""
    payload = {
        "pc": socket.gethostname(),
        "user": getpass.getuser(),
        "target": interface_name,
    }
    return msgpack.packb(payload, use_bin_type=True)


def parse_discovery_response(
    payload: bytes,
    source: tuple[str, int],
    seen: float | None = None,
) -> dict[str, Any] | None:
    """Parse one MessagePack UDP discovery response packet."""
    try:
        decoded = msgpack.unpackb(payload, raw=False, strict_map_key=False)
    except (msgpack.ExtraData, msgpack.FormatError, msgpack.StackError, ValueError):
        return None
    if not isinstance(decoded, dict) or not _is_valid_discovery_payload(decoded):
        return None

    device: dict[str, Any] = {
        "raw": payload,
        "seen": seen if seen is not None else time.time(),
        "source_ip": source[0],
        "source_port": source[1],
    }
    device.update(decoded)
    device["board_number"] = normalize_mac(device.get("board_number")) or device.get("board_number")
    device["mac"] = device.get("board_number")
    device["ip"] = source[0]
    return device


def _deduplicate_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate responses by board number with IP fallback."""
    deduplicated: dict[str, dict[str, Any]] = {}

    for device in devices:
        key = (
            normalize_mac(device.get("board_number"))
            or normalize_mac(device.get("mac"))
            or device.get("ip")
            or device.get("source_ip")
        )
        if key is None:
            continue

        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = device
            continue

        for field in (
            "activation_status",
            "board_number",
            "board_type",
            "brand",
            "mac",
            "ip",
            "name",
            "type",
            "version",
            "production_number",
            "service_name",
            "localisation",
            "target",
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
            payload = _build_discovery_request(target.name)
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
            transport.sendto(payload, (target.broadcast, DISCOVERY_PORT))
            LOGGER.debug(
                "Atrea UDP discovery request sent target=%s:%s raw=%s",
                target.broadcast,
                DISCOVERY_PORT,
                payload.hex(" "),
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

    deduplicated = _deduplicate_devices(parsed_devices)
    LOGGER.debug("Atrea UDP discovery completed devices_found=%s", len(deduplicated))
    return deduplicated


async def async_discover_enriched_devices(
    hass,
    timeout: float = DISCOVERY_TIMEOUT,
) -> list[dict[str, Any]]:
    """Run UDP discovery and return the MessagePack metadata."""
    return await async_discover_devices(timeout=timeout)


def _device_match_score(entry_data: Mapping[str, Any], device: Mapping[str, Any]) -> int:
    """Score how well a discovered device matches an existing config entry."""
    score = 0

    entry_network_mac = normalize_mac(entry_data.get("network_mac"))
    device_network_mac = normalize_mac(device.get("board_number") or device.get("mac"))
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
