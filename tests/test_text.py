"""Tests for Atrea aMotion text entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.text import async_setup_entry


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.unit_name = "Original name"
        self.set_calls: list[str] = []

    def async_state(self):
        class _State:
            discovery = {"name": "Original name"}

        return _State()

    async def async_set_unit_name(self, value: str) -> bool:
        self.set_calls.append(value)
        return True


async def test_text_entity_sets_unit_name(hass, MockConfigEntry) -> None:
    """Unit name text entity should call coordinator setter."""
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
    assert added_entities[0].native_value == "Original name"
    await added_entities[0].async_set_value("Homer HRV")
    assert coordinator.set_calls == ["Homer HRV"]
