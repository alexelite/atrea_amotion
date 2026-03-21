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

HVAC_MODE_MAP = {
    HVACMode.OFF: "OFF",
    HVACMode.AUTO: "AUTO",
    HVACMode.FAN_ONLY: "VENTILATION",
    HVACMode.COOL: "NIGHT_PRECOOLING",
}
WORK_REGIME_TO_HVAC = {value: key for key, value in HVAC_MODE_MAP.items()}
WORK_REGIME_TO_HVAC["DISBALANCE"] = HVACMode.FAN_ONLY


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
        ClimateEntityFeature.TARGET_TEMPERATURE
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
        self.async_write_ha_state()

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
        value = self.coordinator.requested_value("temp_request")
        return round(value, 1) if isinstance(value, float) else value

    @property
    def hvac_mode(self) -> HVACMode:
        """Return requested HVAC mode."""
        return WORK_REGIME_TO_HVAC.get(
            self.coordinator.requested_value("work_regime"), HVACMode.OFF
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported HVAC modes."""
        available = self.coordinator.async_capabilities().enum_for("work_regime")
        modes = [HVACMode.OFF]
        if "AUTO" in available:
            modes.append(HVACMode.AUTO)
        if "VENTILATION" in available or "DISBALANCE" in available:
            modes.append(HVACMode.FAN_ONLY)
        if "NIGHT_PRECOOLING" in available:
            modes.append(HVACMode.COOL)
        return modes

    @property
    def hvac_action(self) -> HVACAction:
        """Return effective HVAC action."""
        mode_current = self.coordinator.unit_value("mode_current")
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if mode_current in {"STARTUP", "NORMAL", "VENTILATION", "AUTO"}:
            return HVACAction.FAN
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return raw requested/effective modes."""
        return {
            "work_regime": self.coordinator.requested_value("work_regime"),
            "mode_current": self.coordinator.unit_value("mode_current"),
            "season_current": self.coordinator.unit_value("season_current"),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new requested work regime."""
        await self.coordinator.async_control(
            {"work_regime": HVAC_MODE_MAP.get(hvac_mode, "OFF")}
        )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return
        await self.coordinator.async_control({"temp_request": kwargs[ATTR_TEMPERATURE]})

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
