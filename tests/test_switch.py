"""Tests for Atrea aMotion switch entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.switch import async_setup_entry


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.values = {
            "modbus_enabled": True,
            "autoupdate_enabled": True,
        }
        self.modbus_calls: list[bool] = []
        self.autoupdate_calls: list[bool] = []

    def value(self, key: str):
        return self.values.get(key)

    async def async_set_modbus_enabled(self, enabled: bool) -> bool:
        self.modbus_calls.append(enabled)
        self.values["modbus_enabled"] = enabled
        return True

    async def async_set_autoupdate_enabled(self, enabled: bool) -> bool:
        self.autoupdate_calls.append(enabled)
        self.values["autoupdate_enabled"] = enabled
        return True


async def test_switches_are_created_and_call_setters(hass, MockConfigEntry) -> None:
    """Switch entities should toggle coordinator setters."""
    coordinator = _MockCoordinator()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Atrea",
        data={CONF_NAME: "Atrea", CONF_HOST: "192.0.2.10"},
    )
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"atrea": coordinator}

    added_entities = []

    def _async_add_entities(entities):
        added_entities.extend(entities)

    await async_setup_entry(hass, entry, _async_add_entities)

    assert len(added_entities) == 2

    modbus_switch = next(entity for entity in added_entities if entity.name == "Modbus TCP")
    autoupdate_switch = next(
        entity for entity in added_entities if entity.name == "Firmware auto update"
    )

    assert modbus_switch.is_on is True
    assert autoupdate_switch.is_on is True

    await modbus_switch.async_turn_off()
    await autoupdate_switch.async_turn_off()

    assert coordinator.modbus_calls == [False]
    assert coordinator.autoupdate_calls == [False]
