"""Climate entity for Atrea aMotion comfort control."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.components.climate.const import HVACAction
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, CONF_HOST, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN

PRESET_TO_WORK_REGIME = {
    "Stand-by": "OFF",
    "Intervals": "AUTO",
    "Ventilation": "VENTILATION",
    "Night precooling": "NIGHT_PRECOOLING",
    "Disbalance": "DISBALANCE",
}
WORK_REGIME_TO_PRESET = {
    "OFF": "Stand-by",
    "AUTO": "Intervals",
    "VENTILATION": "Ventilation",
    "NIGHT_PRECOOLING": "Night precooling",
    "DISBALANCE": "Disbalance",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Callable
) -> None:
    """Set up climate entity from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    if not coordinator.async_capabilities().has_climate_control:
        return

    sensor_name = entry.data.get(CONF_NAME) or "aatrea"
    async_add_entities([AtreaAMotionClimate(coordinator, entry, sensor_name)])


class AtreaAMotionClimate(ClimateEntity):
    """Representation of aMotion comfort control."""

    _attr_supported_features = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator, entry: ConfigEntry, sensor_name: str) -> None:
        self.coordinator = coordinator
        self._name = sensor_name
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{sensor_name}-{entry.data.get(CONF_HOST)}")},
            manufacturer="Atrea CZ",
            model=self.coordinator.model,
            name=sensor_name,
            sw_version=self.coordinator.version,
        )
        self._unsubscribe = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        self._unsubscribe = async_dispatcher_connect(
            self.hass, self.coordinator.update_signal, self._handle_coordinator_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect dispatcher listener."""
        if self._unsubscribe is not None:
            self._unsubscribe()

    def _handle_coordinator_update(self) -> None:
        """Update entity state."""
        self.schedule_update_ha_state()

    @property
    def temperature_unit(self) -> str:
        """Return temperature unit."""
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> float | None:
        """Return current indoor temperature."""
        value = self.coordinator.unit_value("temp_ida")
        return round(value, 1) if isinstance(value, float) else value

    @property
    def target_temperature(self) -> float | None:
        """Return requested comfort temperature."""
        value = self.coordinator.value("stored_temp_request")
        if value is None:
            value = self.coordinator.requested_value("temp_request")
        return round(value, 1) if isinstance(value, float) else value

    @property
    def hvac_mode(self) -> HVACMode:
        """Return simplified HVAC mode for Home Assistant."""
        work_regime = self.coordinator.value("stored_work_regime")
        if work_regime is None:
            work_regime = self.coordinator.requested_value("work_regime")
        if work_regime == "OFF":
            return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported generic HVAC modes."""
        return [HVACMode.OFF, HVACMode.AUTO]

    @property
    def preset_mode(self) -> str | None:
        """Return the current unit work regime as a friendly preset."""
        work_regime = self.coordinator.value("stored_work_regime")
        if work_regime is None:
            work_regime = self.coordinator.requested_value("work_regime")
        return WORK_REGIME_TO_PRESET.get(work_regime)

    @property
    def preset_modes(self) -> list[str]:
        """Return exact unit work regimes as presets."""
        available = self.coordinator.async_capabilities().enum_for("work_regime")
        modes: list[str] = []
        if "OFF" in available:
            modes.append("Stand-by")
        if "AUTO" in available:
            modes.append("Intervals")
        if "VENTILATION" in available:
            modes.append("Ventilation")
        if "NIGHT_PRECOOLING" in available:
            modes.append("Night precooling")
        if "DISBALANCE" in available:
            modes.append("Disbalance")
        return modes

    @property
    def hvac_action(self) -> HVACAction:
        """Return effective HVAC action."""
        mode_current = self.coordinator.unit_value("mode_current")
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.preset_mode == "Night precooling":
            return HVACAction.COOLING
        if mode_current in {"STARTUP", "NORMAL", "VENTILATION", "AUTO"}:
            return HVACAction.FAN
        return HVACAction.IDLE

    @property
    def fan_mode(self) -> str:
        """Return the current fan mode."""
        requested = self.coordinator.requested_value("fan_power_req")
        if requested is None:
            requested = self.coordinator.requested_value("fan_power_req_sup")
        if requested is None:
            requested = self.coordinator.requested_value("fan_power_req_eta")
        return str(int(requested)) if requested is not None else "0"

    @property
    def fan_modes(self) -> list[str]:
        """Return the available fan modes."""
        return ["0", "20", "40", "50", "60", "70", "80", "90", "100"]

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return raw requested/effective modes."""
        return {
            "work_regime": self.coordinator.requested_value("work_regime"),
            "stored_work_regime": self.coordinator.value("stored_work_regime"),
            "mode_current": self.coordinator.unit_value("mode_current"),
            "season_current": self.coordinator.unit_value("season_current"),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set generic HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_control({"work_regime": "OFF"})
            return

        if self.preset_mode in self.preset_modes:
            await self.async_set_preset_mode(self.preset_mode)
            return

        if "Intervals" in self.preset_modes:
            await self.async_set_preset_mode("Intervals")
            return

        if "Ventilation" in self.preset_modes:
            await self.async_set_preset_mode("Ventilation")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the exact unit work regime via preset."""
        work_regime = PRESET_TO_WORK_REGIME[preset_mode]
        await self.coordinator.async_control({"work_regime": work_regime})

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return
        await self.coordinator.async_control({"temp_request": kwargs[ATTR_TEMPERATURE]})

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set requested fan power coherently across supported controls."""
        value = int(fan_mode)
        variables: dict[str, int] = {}
        capabilities = self.coordinator.async_capabilities()
        if capabilities.has_unified_fan_control:
            variables["fan_power_req"] = value
        if capabilities.has_supply_fan_control:
            variables["fan_power_req_sup"] = value
        if capabilities.has_extract_fan_control:
            variables["fan_power_req_eta"] = value
        if variables:
            await self.coordinator.async_control(variables)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
