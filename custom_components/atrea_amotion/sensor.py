"""Sensors for Atrea aMotion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

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


def _date_from_parts(value: Any) -> date | None:
    """Build a date from a websocket date object."""
    if not isinstance(value, dict):
        return None
    year = value.get("year")
    month = value.get("month")
    day = value.get("day")
    if not all(isinstance(part, int) for part in (year, month, day)):
        return None
    if year <= 1970 or month <= 0 or day <= 0:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_from_epoch(value: Any) -> date | None:
    """Build a date from an epoch timestamp."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value).date()


@dataclass(frozen=True)
class AtreaSensorDescription(SensorEntityDescription):
    """Description for aMotion sensor entities."""

    value_key: str = ""


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
        state_class=SensorStateClass.MEASUREMENT,
        value_key="fan_eta_factor",
    ),
    AtreaSensorDescription(
        key="fan_sup_factor",
        name="Supply fan factor",
        icon="mdi:fan",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="fan_sup_factor",
    ),
    AtreaSensorDescription(
        key="bypass_estim",
        name="Bypass estimation",
        icon="mdi:pipe-valve",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="bypass_estim",
    ),
    AtreaSensorDescription(
        key="damper_io_state",
        name="Damper state",
        icon="mdi:door-sliding",
        value_key="damper_io_state",
    ),
    AtreaSensorDescription(
        key="fan_eta_operating_time",
        name="Extract fan operating time",
        icon="mdi:timer-outline",
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_key="fan_eta_operating_time",
    ),
    AtreaSensorDescription(
        key="fan_sup_operating_time",
        name="Supply fan operating time",
        icon="mdi:timer-outline",
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_key="fan_sup_operating_time",
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
        state_class=SensorStateClass.MEASUREMENT,
        value_key="active_state_count",
    ),
    AtreaSensorDescription(
        key="filter_interval_active",
        name="Filter interval active",
        icon="mdi:air-filter",
        value_key="filter_interval_active",
    ),
    AtreaSensorDescription(
        key="filter_due_date",
        name="Filter service due",
        icon="mdi:calendar-alert",
        device_class=SensorDeviceClass.DATE,
        value_key="filter_due_date",
    ),
    AtreaSensorDescription(
        key="last_filter_reset",
        name="Last filter replacement",
        icon="mdi:calendar-check",
        device_class=SensorDeviceClass.DATE,
        value_key="last_filter_reset",
    ),
    AtreaSensorDescription(
        key="filter_service_days_remaining",
        name="Filter service days remaining",
        icon="mdi:calendar-clock",
        state_class=SensorStateClass.MEASUREMENT,
        value_key="filter_due_date",
    ),
    AtreaSensorDescription(
        key="m1_register",
        name="Motor 1 register",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_key="m1_register",
    ),
    AtreaSensorDescription(
        key="m2_register",
        name="Motor 2 register",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_key="m2_register",
    ),
    AtreaSensorDescription(
        key="uv_lamp_register",
        name="UV lamp register",
        icon="mdi:lightbulb",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_key="uv_lamp_register",
    ),
    AtreaSensorDescription(
        key="uv_lamp_service_life",
        name="UV lamp service life",
        icon="mdi:lightbulb-on-outline",
        native_unit_of_measurement="h",
        state_class=SensorStateClass.MEASUREMENT,
        value_key="uv_lamp_service_life",
    ),
)

UNIT_SENSOR_KEYS = {
    "temp_oda",
    "temp_oda_mean",
    "temp_ida",
    "temp_eha",
    "temp_sup",
    "temp_eta",
    "fan_eta_factor",
    "fan_sup_factor",
    "season_current",
    "mode_current",
}


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
    if description.value_key in UNIT_SENSOR_KEYS:
        return description.value_key in coordinator.async_capabilities().unit_fields
    return True


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
    def native_value(self) -> float | int | str | date | None:
        """Return sensor value."""
        key = self.entity_description.key
        raw_value = self.coordinator.value(self.entity_description.value_key)

        if key == "filter_due_date":
            return _date_from_parts(raw_value)
        if key == "last_filter_reset":
            return _date_from_epoch(raw_value)
        if key == "filter_service_days_remaining":
            due_date = _date_from_parts(self.coordinator.value("filter_due_date"))
            return (due_date - date.today()).days if due_date is not None else None
        if key == "filter_interval_active":
            return "on" if raw_value else "off"

        if isinstance(raw_value, float):
            return round(raw_value, 1)
        return raw_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes for composite sensors."""
        if self.entity_description.key == "active_state_count":
            return {
                "active_state_names": self.coordinator.value("active_state_names") or [],
                "active_states": self.coordinator.value("active_states") or {},
            }
        return {}
