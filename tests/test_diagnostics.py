"""Tests for Atrea aMotion diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field

from custom_components.atrea_amotion.diagnostics import async_get_config_entry_diagnostics
from custom_components.atrea_amotion.const import CONF_DEBUG_LOGGING, DOMAIN


@dataclass
class _MockCapabilities:
    requests: set[str] = field(default_factory=lambda: {"fan_power_req_sup"})
    unit_fields: set[str] = field(default_factory=lambda: {"temp_ida"})
    state_fields: set[str] = field(default_factory=lambda: {"active"})
    enum_values: dict[str, list[str]] = field(default_factory=dict)
    range_types: dict[str, dict] = field(default_factory=dict)
    diagram_components: dict[str, dict] = field(default_factory=dict)


@dataclass
class _MockState:
    discovery: dict = field(
        default_factory=lambda: {"board_number": "secret-board", "version": "1.0.0"}
    )
    requests: dict = field(default_factory=lambda: {"fan_power_req_sup": 50})
    unit: dict = field(default_factory=lambda: {"temp_ida": 22.0})
    active_states: dict = field(default_factory=lambda: {"105": {"name": "FILTER_INTERVAL"}})
    derived: dict = field(default_factory=lambda: {"last_filter_reset": 1234567890})
    control_panel: dict = field(default_factory=lambda: {"stored": {"temp_request": 23}})
    disposable_plan: dict = field(default_factory=dict)
    ui_diagram_data: dict = field(default_factory=lambda: {"bypass_estim": 42})
    moments: dict = field(default_factory=lambda: {"lastFilterReset": 1234567890})


class _MockCoordinator:
    socket_state = "Open"
    _authorized = True
    model = "aMotion"
    version = "1.0.0"
    board_type = "CE"

    def async_capabilities(self):
        return _MockCapabilities()

    def async_state(self):
        return _MockState()


async def test_diagnostics_redacts_sensitive_values(hass, MockConfigEntry) -> None:
    """Diagnostics should redact credentials and host-like identifiers."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Atrea",
        data={
            "host": "192.0.2.10",
            "username": "user",
            "password": "pass",
            "mac": "secret-mac",
            "network_mac": "aa:bb:cc:dd:ee:ff",
            CONF_DEBUG_LOGGING: True,
        },
        options={CONF_DEBUG_LOGGING: True},
    )
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"atrea": _MockCoordinator()}

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"]["host"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["username"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["password"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["mac"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["network_mac"] == "**REDACTED**"
    assert diagnostics["state"]["discovery"]["board_number"] == "**REDACTED**"
    assert diagnostics["runtime"]["authorized"] is True
