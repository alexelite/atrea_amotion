"""Tests for Atrea aMotion climate entity."""

from __future__ import annotations

from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.atrea_amotion.climate import async_setup_entry
from custom_components.atrea_amotion.const import DOMAIN


class _MockCapabilities:
    def __init__(self) -> None:
        self.has_climate_control = True

    def enum_for(self, variable: str) -> list[str]:
        if variable == "work_regime":
            return ["OFF", "AUTO", "VENTILATION", "NIGHT_PRECOOLING", "DISBALANCE"]
        return []


class _MockCoordinator:
    model = "aMotion"
    version = "1.0.0"
    update_signal = "atrea_update"

    def __init__(self) -> None:
        self.requests = {"work_regime": "AUTO", "temp_request": 21.0}
        self.unit = {"temp_ida": 22.0, "mode_current": "NORMAL", "season_current": "HEATING"}
        self.derived = {"stored_work_regime": "AUTO", "stored_temp_request": 21.0}
        self.control_calls: list[dict[str, object]] = []

    def async_capabilities(self):
        return _MockCapabilities()

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
