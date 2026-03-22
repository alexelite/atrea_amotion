"""Tests for Atrea select entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.select import async_setup_entry


class _MockCapabilities:
    has_bypass_control = True

    def enum_for(self, variable: str) -> list[str]:
        if variable == "bypass_control_req":
            return ["AUTO", "OPEN", "CLOSED"]
        return []


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.requests = {"bypass_control_req": "OPEN"}
        self.derived = {"stored_bypass_control_req": "CLOSED"}
        self.control_calls: list[dict[str, object]] = []

    def async_capabilities(self):
        return _MockCapabilities()

    def requested_value(self, key: str):
        return self.requests.get(key)

    def value(self, key: str):
        return self.derived.get(key)

    async def async_control(self, variables: dict[str, object]) -> bool:
        self.control_calls.append(variables)
        self.requests.update(variables)
        self.derived.update({f"stored_{key}": value for key, value in variables.items()})
        return True


async def test_bypass_select_uses_friendly_labels_and_stored_value(hass, MockConfigEntry) -> None:
    """Bypass select should expose friendly labels and prefer stored values."""
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
    select = added_entities[0]

    assert select.options == ["Auto", "Open", "Closed"]
    assert select.current_option == "Closed"

    await select.async_select_option("Open")
    assert coordinator.control_calls[-1] == {"bypass_control_req": "OPEN"}
