"""Tests for Atrea aMotion climate entity."""

from __future__ import annotations

from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.climate import async_setup_entry
from custom_components.atrea_amotion.const import DOMAIN


class _MockCapabilities:
    def __init__(self) -> None:
        self.has_climate_control = True
        self.has_unified_fan_control = False
        self.has_supply_fan_control = True
        self.has_extract_fan_control = True
        self.base_states = {
            105: {"purpose": "notify", "severity": 3},
            999: {"purpose": "alarm_sr", "severity": 5},
        }

    def enum_for(self, variable: str) -> list[str]:
        if variable == "work_regime":
            return ["OFF", "AUTO", "VENTILATION", "NIGHT_PRECOOLING", "DISBALANCE"]
        return []


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.discovery = {"name": "Homer HRV"}
        self.requests = {
            "work_regime": "AUTO",
            "temp_request": 21.0,
            "fan_power_req_sup": 50,
            "fan_power_req_eta": 50,
        }
        self.unit = {"temp_ida": 22.0, "mode_current": "NORMAL", "season_current": "HEATING"}
        self.derived = {
            "stored_work_regime": "AUTO",
            "stored_temp_request": 21.0,
            "stored_fan_power_req_sup": 50,
            "stored_fan_power_req_eta": 50,
            "bypass_estim": 42,
            "damper_io_state": True,
            "filter_due_date": {"day": 25, "month": 3, "year": 2026},
            "warning": True,
            "fault": False,
        }
        self.unit.update(
            {
                "temp_oda": 7.5,
                "temp_eta": 21.2,
                "temp_sup": 18.4,
                "temp_eha": 20.7,
                "fan_sup_factor": 48,
                "fan_eta_factor": 50,
            }
        )
        self.control_calls: list[dict[str, object]] = []

    def async_capabilities(self):
        return _MockCapabilities()

    def async_state(self):
        class _State:
            def __init__(self, discovery):
                self.discovery = discovery

        return _State(self.discovery)

    def requested_value(self, key: str):
        return self.requests.get(key)

    def unit_value(self, key: str):
        return self.unit.get(key)

    def value(self, key: str):
        return self.derived.get(key)

    async def async_control(self, variables: dict[str, object]) -> bool:
        self.control_calls.append(variables)
        self.requests.update(variables)
        self.derived.update({f"stored_{key}": value for key, value in variables.items()})
        return True


async def test_climate_uses_exact_unit_presets(hass, MockConfigEntry) -> None:
    """Climate entity should expose exact unit regimes as presets."""
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
    climate = added_entities[0]

    assert climate.hvac_modes == [HVACMode.OFF, HVACMode.AUTO]
    assert climate.preset_modes == [
        "Stand-by",
        "Intervals",
        "Ventilation",
        "Night precooling",
        "Disbalance",
    ]
    assert climate.preset_mode == "Intervals"
    assert climate.hvac_mode == HVACMode.AUTO

    await climate.async_set_preset_mode("Stand-by")
    assert coordinator.control_calls[-1] == {"work_regime": "OFF"}

    await climate.async_set_hvac_mode(HVACMode.OFF)
    assert coordinator.control_calls[-1] == {"work_regime": "OFF"}

    assert climate.fan_modes == [str(value) for value in range(0, 101, 10)]
    assert climate.fan_mode == "50"

    await climate.async_set_fan_mode("30")
    assert coordinator.control_calls[-1] == {
        "fan_power_req_sup": 30,
        "fan_power_req_eta": 30,
    }

    attrs = climate.extra_state_attributes
    assert attrs["unit_name"] == "Homer HRV"
    assert attrs["outside_air_temperature"] == 7.5
    assert attrs["extract_air_temperature"] == 21.2
    assert attrs["supply_air_temperature"] == 18.4
    assert attrs["exhaust_air_temperature"] == 20.7
    assert attrs["supply_fan_speed_percent"] == 48
    assert attrs["extract_fan_speed_percent"] == 50
    assert attrs["bypass_position_percent"] == 42
    assert attrs["oda_damper_percent"] == 100
    assert attrs["eta_damper_percent"] == 100
    assert attrs["current_mode"] == "NORMAL"
    assert attrs["filter_days_remaining"] is not None
    assert attrs["warning"] is True
    assert attrs["fault"] is False
