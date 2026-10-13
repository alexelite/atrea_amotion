"""Fan entities for Atrea aMotion."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .identity import AtreaAvailability, device_identity, device_info
from .registry_migration import with_compatibility_aliases

FAN_VARIABLES = (
    ("fan_power_req_sup", "supply_fan"),
    ("fan_power_req_eta", "extract_fan"),
    ("fan_power_req", "ventilation_fan"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up fan entities from a config entry."""
    async_add_entities = with_compatibility_aliases(hass, entry, "fan", async_add_entities)
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    sensor_name = entry.data.get(CONF_NAME) or "aatrea"

    entities: list[AtreaAMotionFan] = []
    for variable, translation_key in FAN_VARIABLES:
        if variable not in coordinator.async_capabilities().requests:
            continue
        entities.append(AtreaAMotionFan(coordinator, entry, sensor_name, variable, translation_key))

    async_add_entities(entities)


class AtreaAMotionFan(AtreaAvailability, FanEntity):
    """A percentage-based fan entity backed by aMotion control variables."""

    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.TURN_ON
    )
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        sensor_name: str,
        request_key: str,
        translation_key: str,
    ) -> None:
        self.coordinator = coordinator
        self.request_key = request_key
        self.factor_key = request_key.replace("power_req", "factor")
        self._attr_unique_id = f"{device_identity(entry)}-{request_key}"
        self._attr_translation_key = translation_key
        self._attr_device_info = device_info(entry, coordinator, sensor_name)
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write updated state to Home Assistant."""
        self.async_write_ha_state()

    @staticmethod
    def _coerce_percentage(value: Any) -> int | None:
        """Convert supported percentage values to int."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return None
        return None

    @property
    def percentage(self) -> int | None:
        """Return the requested percentage."""
        value = self.coordinator.value(f"stored_{self.request_key}")
        if value is None:
            value = self.coordinator.value(self.request_key)
        return self._coerce_percentage(value)

    @property
    def speed_count(self) -> int:
        """Return the number of discrete percentages."""
        return 100

    @property
    def is_on(self) -> bool | None:
        """Return whether the fan is on."""
        percentage = self.percentage
        return percentage is not None and percentage > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return supplemental measured fan data."""
        attributes: dict[str, Any] = {"request_key": self.request_key}
        factor = self.coordinator.unit_value(self.factor_key)
        if factor is not None and self.request_key != "fan_power_req":
            attributes["actual_factor"] = round(factor, 1) if isinstance(factor, float) else factor
        stored_value = self.coordinator.value(f"stored_{self.request_key}")
        if stored_value is not None:
            attributes["stored_percentage"] = self._coerce_percentage(stored_value)
        return attributes

    async def async_set_percentage(self, percentage: int) -> None:
        """Set requested fan percentage."""
        await self.coordinator.async_control({self.request_key: percentage})

    async def async_turn_on(self, percentage: int | None = None, **kwargs: Any) -> None:
        """Turn the fan on."""
        await self.async_set_percentage(percentage if percentage is not None else 50)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        await self.async_set_percentage(0)
