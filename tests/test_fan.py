"""Tests for Atrea fan entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.fan import async_setup_entry


class _MockCapabilities:
    requests = {"fan_power_req_sup"}


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def async_capabilities(self):
        return _MockCapabilities()

    def value(self, key: str):
        values = {
            "fan_power_req_sup": 50,
            "stored_fan_power_req_sup": "70",
        }
        return values.get(key)

    def unit_value(self, key: str):
        if key == "fan_sup_factor":
            return 68.5
        return None

    async def async_control(self, variables: dict[str, object]) -> bool:
        return True


async def test_fan_prefers_stored_percentage(hass, MockConfigEntry) -> None:
    """Fan entity should show stored percentage before stale request values."""
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

    assert len(added_entities) == 1
    fan = added_entities[0]

    assert fan.percentage == 70
    assert fan.extra_state_attributes["stored_percentage"] == 70
