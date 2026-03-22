"""Tests for Atrea sensors."""

from __future__ import annotations

from datetime import date

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.sensor import async_setup_entry
from custom_components.atrea_amotion.const import DOMAIN


class _MockCapabilities:
    unit_fields: set[str] = set()
    requests: set[str] = set()


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def async_capabilities(self):
        return _MockCapabilities()

    def value(self, key: str):
        if key == "last_filter_reset":
            return {"day": 21, "month": 3, "year": 2026}
        return None


async def test_last_filter_reset_accepts_structured_date(hass, MockConfigEntry) -> None:
    """Last filter replacement should parse structured Atrea date objects."""
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

    sensor = next(entity for entity in added_entities if entity.entity_description.key == "last_filter_reset")
    assert sensor.native_value == date(2026, 3, 21)


class _MockFanCapabilities:
    unit_fields = {"fan_sup_factor", "fan_eta_factor"}
    requests = {"fan_power_req_sup", "fan_power_req_eta"}


class _MockFanCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def async_capabilities(self):
        return _MockFanCapabilities()

    def value(self, key: str):
        values = {
            "stored_fan_power_req_sup": "97",
            "stored_fan_power_req_eta": 50,
            "fan_sup_factor": 97,
            "fan_eta_factor": 50,
        }
        return values.get(key)


async def test_requested_fan_speed_sensors_follow_capabilities(hass, MockConfigEntry) -> None:
    """Requested fan speed sensors should appear only for exposed request variables."""
    coordinator = _MockFanCoordinator()
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

    entity_by_key = {entity.entity_description.key: entity for entity in added_entities}

    assert "fan_sup_requested" in entity_by_key
    assert "fan_eta_requested" in entity_by_key
    assert "fan_requested" not in entity_by_key
    assert entity_by_key["fan_sup_requested"].native_value == 97
    assert entity_by_key["fan_eta_requested"].native_value == 50
