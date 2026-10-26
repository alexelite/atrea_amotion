"""Tests for Atrea number entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.number import async_setup_entry


class _MockCapabilities:
    requests: set[str] = set()
    config_fields = {
        "season_switch_temp",
        "temp_ida_heater_hyst",
        "temp_ida_cooler_hyst",
        "temp_cool_active_offset",
    }

    def range_for(self, key: str) -> dict[str, float]:
        return {
            "season_switch_temp": {"min": -30.0, "max": 50.0, "step": 0.1},
            "temp_ida_heater_hyst": {"min": 0.1, "max": 3.0, "step": 0.1},
            "temp_ida_cooler_hyst": {"min": 0.1, "max": 3.0, "step": 0.1},
            "temp_cool_active_offset": {"min": 0.1, "max": 3.0, "step": 0.1},
        }[key]


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.values = {
            "season_switch_temp": 18.5,
            "temp_ida_heater_hyst": 0.5,
            "temp_ida_cooler_hyst": 0.5,
            "temp_cool_active_offset": 1.0,
        }
        self.calls: list[tuple[str, float]] = []

    def async_capabilities(self):
        return _MockCapabilities()

    def config_value(self, key: str):
        return self.values.get(key)

    async def async_set_config(self, key: str, value: float) -> bool:
        self.calls.append((key, value))
        self.values[key] = value
        return True


async def test_config_numbers_use_range_metadata_and_set_values(hass, MockConfigEntry) -> None:
    """Config numbers should expose readback values and use config writes."""
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

    entity_by_key = {entity.translation_key: entity for entity in added_entities}
    season_switch = entity_by_key["season_switch_temp"]

    assert season_switch.native_value == 18.5
    assert season_switch.native_min_value == -30.0
    assert season_switch.native_max_value == 50.0
    assert season_switch.native_step == 0.1

    await season_switch.async_set_native_value(19.0)
    assert coordinator.calls[-1] == ("season_switch_temp", 19.0)


class _MockFlowCapabilities(_MockCapabilities):
    requests = {"flow_ventilation_req", "temp_request", "work_regime"}

    def range_for(self, key: str) -> dict[str, float]:
        if key == "flow_ventilation_req":
            return {"min": 700.0, "max": 5200.0, "step": 50}
        return super().range_for(key)


class _MockFlowCoordinator(_MockCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.requests = {"flow_ventilation_req": 700}
        self.controls: list[dict[str, int]] = []

    def async_capabilities(self):
        return _MockFlowCapabilities()

    def requested_value(self, key: str):
        return self.requests.get(key)

    async def async_control(self, variables: dict[str, int]) -> bool:
        self.controls.append(variables)
        self.requests.update(variables)
        return True


async def test_flow_ventilation_request_number(hass, MockConfigEntry) -> None:
    """Units controlled by airflow get a number for the requested m³/h, sent as a control request."""
    coordinator = _MockFlowCoordinator()
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

    entity_by_key = {entity.translation_key: entity for entity in added_entities}
    flow = entity_by_key["flow_ventilation_req"]

    assert flow.native_value == 700.0
    assert flow.native_min_value == 700.0
    assert flow.native_max_value == 5200.0
    assert flow.native_step == 50
    assert flow.native_unit_of_measurement == "m³/h"

    await flow.async_set_native_value(3000.0)
    assert coordinator.controls[-1] == {"flow_ventilation_req": 3000}
    assert coordinator.calls == []
