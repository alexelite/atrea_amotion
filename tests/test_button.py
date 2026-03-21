"""Tests for Atrea aMotion button entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.button import async_setup_entry
from custom_components.atrea_amotion.const import DOMAIN


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.reset_called = False
        self.reboot_called = False

    def value(self, key: str):
        if key == "filters":
            return {"day": 19, "month": 6, "year": 2026}
        if key == "last_filter_reset":
            return {"day": 21, "month": 3, "year": 2026}
        return None

    async def async_reset_filter_interval(self) -> bool:
        self.reset_called = True
        return True

    async def async_reboot(self) -> bool:
        self.reboot_called = True
        return True


async def test_buttons_are_created_and_call_actions(hass, MockConfigEntry) -> None:
    """Button entities should call coordinator actions."""
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

    reboot_button = next(entity for entity in added_entities if entity.name == "Reboot unit")
    filter_button = next(
        entity for entity in added_entities if entity.name == "Confirm filter replacement"
    )

    await reboot_button.async_press()
    await filter_button.async_press()

    assert coordinator.reboot_called is True
    assert coordinator.reset_called is True
