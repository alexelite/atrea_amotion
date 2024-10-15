"""Support for Atrea aMotion Sensors."""

import time
import logging
import requests, websocket
import json

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    UnitOfEnergy,
    UnitOfTemperature,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    ENTITY_ID_FORMAT,
)


from .const import (
    DOMAIN,
    LOGGER,
)


@dataclass(frozen=True)
class aMotionSensorEntityDescription(SensorEntityDescription):
    """Entity description for aMotion sensors."""

    json_value: str | None = None


#            "temp_oda" Outdoor air
#            "temp_oda_mean" Outdoor air mean
#            "temp_ida" Indoor air
#            "temp_eha" Exhaust air
#            "temp_sup" Supply air
#            "temp_eta" Extract air

ATREA_SENSORS: tuple[aMotionSensorEntityDescription, ...] = (
    aMotionSensorEntityDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        name="Outside air (ODA)",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="temp_oda",
    ),
    aMotionSensorEntityDescription(
        key="outside_temperature_mean",
        translation_key="outside_temperature_mean",
        name="Outside air mean",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="temp_oda_mean",
    ),
    aMotionSensorEntityDescription(
        key="inside_temperature",
        translation_key="inside_temperature",
        name="Inside air (IDA)",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="temp_ida",
    ),
    aMotionSensorEntityDescription(
        key="exhaust_temperature",
        translation_key="exaust_temperature",
        name="Exhaust Air (EHA)",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="temp_eha",
    ),
    aMotionSensorEntityDescription(
        key="supply_temperature",
        translation_key="supply_temperature",
        name="Supply air (SUP)",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="temp_sup",
    ),
    aMotionSensorEntityDescription(
        key="extract_temperature",
        translation_key="extract_temperature",
        name="Extract air (ETA)",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="temp_eta",
    ),
    aMotionSensorEntityDescription(
        key="fan_eta_factor",
        name="Fan exhaust power factor (ETA)",
        icon="mdi:fan",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="fan_eta_factor",
    ),
    aMotionSensorEntityDescription(
        key="fan_sup_factor",
        name="Fan supply power factor (SUP)",
        icon="mdi:fan",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        json_value="fan_sup_factor",
    ),
    aMotionSensorEntityDescription(
        key="season_current",
        name="Current season",
        # native_unit_of_measurement=PERCENTAGE,
        # device_class=SensorDeviceClass.POWER_FACTOR,
        # state_class=SensorStateClass.MEASUREMENT,
        json_value="season_current",
    ),
    aMotionSensorEntityDescription(
        key="bypass_control_req",
        name="Bypass control",
        # native_unit_of_measurement=PERCENTAGE,
        # device_class=SensorDeviceClass.POWER_FACTOR,
        # state_class=SensorStateClass.MEASUREMENT,
        json_value="bypass_control_req",
    ),
    aMotionSensorEntityDescription(
        key="mode_current",
        name="Current mode",
        # native_unit_of_measurement=PERCENTAGE,
        # device_class=SensorDeviceClass.POWER_FACTOR,
        # state_class=SensorStateClass.MEASUREMENT,
        json_value="mode_current",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable,
):
    sensor_name = entry.data.get(CONF_NAME)
    # LOGGER.debug("sensor sensor_name: '%s' ", sensor_name)
    if sensor_name is None:
        sensor_name = "aatrea"

    # LOGGER.debug("INIT")
    entities: list[Atrea_aMotionSensor] = [
        Atrea_aMotionSensor(hass, entry, description, sensor_name)
        for description in ATREA_SENSORS
    ]
    async_add_entities(entities)


class Atrea_aMotionSensor(SensorEntity):
    entity_description: aMotionSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        hass,
        entry,
        description: aMotionSensorEntityDescription,
        sensor_name,
    ) -> None:
        self.data = hass.data[DOMAIN][entry.entry_id]
        self._atrea = self.data["atrea"]
        self.entity_description = description
        self._name = sensor_name
        self._attr_unique_id = "%s-%s-%s" % (
            sensor_name,
            entry.data.get(CONF_HOST),
            description.key,
        )
        self._device_unique_id = "%s-%s" % (sensor_name, entry.data.get(CONF_HOST))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_unique_id)},
            manufacturer="Atrea CZ",
            model=self._atrea.model,
            name=self._name,
            sw_version=self._atrea.version,
        )
        self.value = None

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        # LOGGER.debug("CALLED %s %s" % (self._name, self.value))
        if isinstance(self.value, int):
            return self.value
        elif isinstance(self.value, float):
            return round(self.value, 1)
        else:
            return self.value
        # return self.value

    async def async_update(self) -> None:
        """Retrieve latest state."""
        r = self._atrea.ui_info()
        # LOGGER.debug("Sensor got response %s" % r)
        if r is not None:
            self.value = r.get(self.entity_description.json_value)
        await self._atrea.async_update()
