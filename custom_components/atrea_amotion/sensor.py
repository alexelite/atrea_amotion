"""Sensors for Atrea aMotion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN


@dataclass(frozen=True)
class AtreaSensorDescription(SensorEntityDescription):
    """Description for aMotion sensor entities."""

    value_key: str = ""
    source: str = "unit"


ATREA_SENSORS: tuple[AtreaSensorDescription, ...] = (
    AtreaSensorDescription(
        key="outside_temperature",
        name="Outside air",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="temp_oda",
    ),
    AtreaSensorDescription(
        key="outside_temperature_mean",
        name="Outside air mean",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="temp_oda_mean",
    ),
    AtreaSensorDescription(
        key="inside_temperature",
        name="Inside air",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="temp_ida",
    ),
    AtreaSensorDescription(
        key="exhaust_temperature",
        name="Exhaust air",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="temp_eha",
    ),
    AtreaSensorDescription(
        key="supply_temperature",
        name="Supply air",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="temp_sup",
    ),
    AtreaSensorDescription(
        key="extract_temperature",
        name="Extract air",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="temp_eta",
    ),
    AtreaSensorDescription(
        key="fan_eta_factor",
        name="Extract fan factor",
        icon="mdi:fan",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="fan_eta_factor",
    ),
    AtreaSensorDescription(
        key="fan_sup_factor",
        name="Supply fan factor",
        icon="mdi:fan",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="fan_sup_factor",
    ),
    AtreaSensorDescription(
        key="season_current",
        name="Current season",
        value_key="season_current",
    ),
    AtreaSensorDescription(
        key="mode_current",
        name="Current mode",
        value_key="mode_current",
    ),
    AtreaSensorDescription(
        key="active_state_count",
        name="Active state count",
        icon="mdi:alert-outline",
        value_key="active",
        source="active",
    ),
)


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up aMotion sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    sensor_name = entry.data.get(CONF_NAME) or "aatrea"
    async_add_entities(
        [
            AtreaAMotionSensor(coordinator, entry, description, sensor_name)
            for description in ATREA_SENSORS
            if _is_supported_sensor(coordinator, description)
        ]
    )


def _is_supported_sensor(coordinator, description: AtreaSensorDescription) -> bool:
    """Return whether a sensor is supported by current capabilities."""
    if description.source == "active":
        return "active" in coordinator.async_capabilities().state_fields
    return description.value_key in coordinator.async_capabilities().unit_fields


class AtreaAMotionSensor(SensorEntity):
    """Representation of a single aMotion sensor."""

    entity_description: AtreaSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description: AtreaSensorDescription, sensor_name) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-{description.key}"
        self._device_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_unique_id)},
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
        """Update HA state from coordinator."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | int | str | None:
        """Return sensor value."""
        if self.entity_description.source == "active":
            return len(self.coordinator.async_state().active_states)
        value = self.coordinator.unit_value(self.entity_description.value_key)
        if isinstance(value, float):
            return round(value, 1)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, list[str] | dict[str, object]]:
        """Return additional attributes for composite sensors."""
        if self.entity_description.source != "active":
            return {}
        active_states = self.coordinator.async_state().active_states
        return {
            "active_state_names": [
                state.get("name")
                for state in active_states.values()
                if isinstance(state, dict) and state.get("name")
            ],
            "active_states": active_states,
        }
