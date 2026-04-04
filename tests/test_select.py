"""Tests for Atrea select entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.select import async_setup_entry


class _MockCapabilities:
    has_bypass_control = True
    config_fields: set[str] = set()

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

    def config_value(self, key: str):
        return None

    async def async_set_config(self, key: str, value: object) -> bool:
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


class _MockConfigCapabilities:
    has_bypass_control = False
    config_fields = {"season_request", "temp_oda_mean_interval"}

    def enum_for(self, variable: str) -> list[str]:
        if variable == "season_request":
            return ["AUTO_TODA", "AUTO_TODA_RATIO", "HEATING", "NON_HEATING", "USER"]
        if variable == "temp_oda_mean_interval":
            return ["HOURS_1", "HOURS_3", "DAYS_1"]
        return []


class _MockConfigCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.values = {
            "season_request": "AUTO_TODA",
            "temp_oda_mean_interval": "HOURS_3",
        }
        self.config_calls: list[tuple[str, object]] = []

    def async_capabilities(self):
        return _MockConfigCapabilities()

    def config_value(self, key: str):
        return self.values.get(key)

    async def async_set_config(self, key: str, value: object) -> bool:
        self.config_calls.append((key, value))
        self.values[key] = value
        return True


async def test_config_selects_use_friendly_labels(hass, MockConfigEntry) -> None:
    """Config selects should expose translated labels and set raw enum values."""
    coordinator = _MockConfigCoordinator()
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

    entity_by_name = {entity.name: entity for entity in added_entities}

    season = entity_by_name["Season settings"]
    interval = entity_by_name["T-ODA averaging time slot"]

    assert season.current_option == "Outdoor temp. mean"
    assert interval.current_option == "3 hours"

    await season.async_select_option("Heating")
    await interval.async_select_option("1 hour")

    assert coordinator.config_calls == [
        ("season_request", "HEATING"),
        ("temp_oda_mean_interval", "HOURS_1"),
    ]
