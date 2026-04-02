"""Tests for proprietary UDP discovery."""

from __future__ import annotations

import msgpack

from custom_components.atrea_amotion.discovery import (
    _enumerate_ipv4_targets,
    async_rediscover_config_entry,
    normalize_mac,
    parse_discovery_response,
)


def test_parse_discovery_response_decodes_known_tlvs() -> None:
    """MessagePack response should decode discovery metadata."""
    payload = msgpack.packb(
        {
            "activation_status": "READY",
            "board_number": "70:b8:f6:44:50:89",
            "name": "Atrea HRV",
            "type": "DUPLEX 370 EC5",
            "version": "aMCE-v2.4.5",
            "production_number": "123456789",
        },
        use_bin_type=True,
    )

    parsed = parse_discovery_response(payload, ("192.168.1.50", 3210), seen=123.0)

    assert parsed is not None
    assert parsed["raw"] == payload
    assert parsed["seen"] == 123.0
    assert parsed["board_number"] == "70:b8:f6:44:50:89"
    assert parsed["mac"] == "70:b8:f6:44:50:89"
    assert parsed["ip"] == "192.168.1.50"
    assert parsed["name"] == "Atrea HRV"
    assert parsed["type"] == "DUPLEX 370 EC5"
    assert parsed["version"] == "aMCE-v2.4.5"
    assert parsed["production_number"] == "123456789"
    assert parsed["source_ip"] == "192.168.1.50"
    assert parsed["source_port"] == 3210


def test_normalize_mac_handles_delimiters() -> None:
    """MAC normalization should produce lower-case colon notation."""
    assert normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"


async def test_async_rediscover_config_entry_matches_best_device(hass, monkeypatch) -> None:
    """Rediscovery should prefer the strongest identifier match."""
    devices = [
        {
            "ip": "192.0.2.20",
            "source_ip": "192.0.2.20",
            "mac": "00:11:22:33:44:55",
            "board_number": "BOARD-2",
            "production_number": "PN-2",
            "unit_name": "Other",
            "model": "aMotion",
            "version": "1.0.0",
        },
        {
            "ip": "192.0.2.30",
            "source_ip": "192.0.2.30",
            "mac": "aa:bb:cc:dd:ee:ff",
            "board_number": "BOARD-1",
            "production_number": "PN-1",
            "unit_name": "Atrea HRV",
            "model": "aMotion",
            "version": "2.0.0",
        },
    ]

    async def _fake_discovery(_hass, timeout=2.0):
        return devices

    monkeypatch.setattr(
        "custom_components.atrea_amotion.discovery.async_discover_enriched_devices",
        _fake_discovery,
    )

    rediscovered = await async_rediscover_config_entry(
        hass,
        {
            "host": "192.0.2.10",
            "network_mac": "AA-BB-CC-DD-EE-FF",
            "board_number": "BOARD-1",
            "production_number": "PN-1",
            "unit_name": "Atrea HRV",
        },
    )

    assert rediscovered is not None
    assert rediscovered["ip"] == "192.0.2.30"


def test_enumerate_ipv4_targets_falls_back_without_psutil(monkeypatch) -> None:
    """Interface enumeration should still work when psutil is unavailable."""
    class _DummySocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("custom_components.atrea_amotion.discovery.psutil", None)
    monkeypatch.setattr(
        "custom_components.atrea_amotion.discovery.socket.if_nameindex",
        lambda: [(1, "eth0")],
    )
    monkeypatch.setattr(
        "custom_components.atrea_amotion.discovery.socket.socket",
        lambda *args, **kwargs: _DummySocket(),
    )

    def _fake_ioctl(sock, interface_name, command):
        if command == 0x8915:
            return "192.168.1.10"
        if command == 0x891B:
            return "255.255.255.0"
        return None

    monkeypatch.setattr(
        "custom_components.atrea_amotion.discovery._ioctl_ipv4_value",
        _fake_ioctl,
    )

    targets = _enumerate_ipv4_targets()

    assert len(targets) == 1
    assert targets[0].name == "eth0"
    assert targets[0].broadcast == "192.168.1.255"
