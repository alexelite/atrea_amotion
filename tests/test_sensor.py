"""Tests for Atrea sensors."""

from __future__ import annotations

from datetime import date

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.sensor import async_setup_entry
from custom_components.atrea_amotion.const import DOMAIN


class _MockCapabilities:
    unit_fields: set[str] = set()


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
