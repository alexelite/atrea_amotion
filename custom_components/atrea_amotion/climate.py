"""Module for Atrea aMotion climate device integration with Home Assistant."""

from homeassistant.core import HomeAssistant  # noqa: I001
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from collections.abc import Callable
from homeassistant.components.climate.const import HVACAction

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)

from homeassistant.const import (
    UnitOfTemperature,
    CONF_NAME,
    CONF_HOST,
    ATTR_TEMPERATURE,
)
from .const import DOMAIN, LOGGER

HVAC_MODE_MAP = {
    HVACMode.COOL: "NIGHT_PRECOOLING",
    HVACMode.AUTO: "AUTO",
    HVACMode.FAN_ONLY: "VENTILATION",
    HVACMode.OFF: "OFF",
}

# Reverse mapping for converting from mode_current to HVACMode
MODE_CURRENT_MAP = {v: k for k, v in HVAC_MODE_MAP.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Callable
):
    """Set up the AAtrea climate device from a config entry."""
    sensor_name = entry.data.get(CONF_NAME)
    if sensor_name is None:
        sensor_name = "aatrea"
    LOGGER.debug(
        "aatrea climate sensor_name: '%s', CONF_HOST:'%s'",
        sensor_name,
        entry.data.get(CONF_HOST),
    )
    hass.data[DOMAIN][entry.entry_id]["climate"] = Atrea_aMotionClimate(
        hass, entry, sensor_name
    )
    async_add_entities([hass.data[DOMAIN][entry.entry_id]["climate"]])


class Atrea_aMotionClimate(ClimateEntity):
    """Representation of an Atrea aMotion climate device."""

    _attr_supported_features = (
        ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, hass, entry, sensor_name) -> None:
        super().__init__()
        LOGGER.debug("'%s' init!", sensor_name)
        self.data = hass.data[DOMAIN][entry.entry_id]
        self._atrea = self.data["atrea"]
        self._attr_unique_id = "%s-%s" % (sensor_name, entry.data.get(CONF_HOST))
        self.updatePending = False
        self._name = sensor_name
        # fixme - provide this from Atrea_aMotion
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="Atrea CZ",
            model=self._atrea.model,
            name=self._name,
            sw_version=self._atrea.version,
        )

        self._state = None
        self._attr_current_temperature = None
        self._fan_power_req = None
        self._setpoint = None
        self._mode = None
        self._attr_hvac_mode = HVACMode.OFF

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        info = DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._attr_unique_id)
            },
            name=self._name,
            manufacturer="Atrea CZ",
            model=self._atrea.model,
            sw_version=self._atrea.version,
        )
        return info

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation ie. heat, cool mode."""
        return self._attr_hvac_mode

    @property
    def name(self):
        """Return the name of this device."""
        return self._name

    @property
    def hvac_action(self) -> HVACAction:
        """Return current hvac i.e. heat, cool, idle."""
        return self._attr_hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available hvac modes."""
        return [HVACMode.OFF, HVACMode.AUTO, HVACMode.FAN_ONLY, HVACMode.COOL]
        # ['off', 'auto', 'fan_only']

    @property
    def state(self):
        return self._attr_hvac_mode

    # HA function implement.
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        work_regime = HVAC_MODE_MAP.get(hvac_mode, "OFF")

        await self._atrea.publish_wss(
            {"endpoint": "control", "args": {"variables": {"work_regime": work_regime}}}
        )
        # control = json.dumps({'variables': {'work_regime': work_regime}})
        # LOGGER.debug(control)
        # response_id = await self._atrea.send('{ "endpoint": "control", "args": %s }' % control)
        # LOGGER.debug(response_id)
        # await self._atrea.update(response_id)

    # {"endpoint":"control","args":{"variables":{"work_regime":"OFF"}},"id":39}
    # {"endpoint":"control","args":{"variables":{"work_regime":"AUTO"}},"id":27}
    # {"endpoint":"control","args":{"variables":{"work_regime":"VENTILATION"}},"id":41}
    # {"endpoint":"control","args":{"variables":{"work_regime":"NIGHT_PRECOOLING"}},"id":35}
    # {"endpoint":"control","args":{"variables":{"work_regime":"DISBALANCE"}},"id":37}

    # The `turn_on` method should set `hvac_mode` to any other than
    # `HVACMode.OFF` by optimistically setting it from the service action
    # handler or with the next state update
    async def async_turn_on(self):
        """Turn the entity on."""

    # The `turn_off` method should set `hvac_mode` to `HVACMode.OFF` by
    # optimistically setting it from the service action handler or with the
    # next state update
    async def async_turn_off(self):
        """Turn the entity off."""

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._attr_current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._setpoint

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        # TODO move to Atrea_aMotion set_temperature?
        await self._atrea.publish_wss(
            {
                "endpoint": "control",
                "args": {"variables": {"temp_request": kwargs.get(ATTR_TEMPERATURE)}},
            }
        )
        # control = json.dumps({'variables': {'temp_request': kwargs.get(ATTR_TEMPERATURE)}})
        # response_id = await self._atrea.send('{ "endpoint": "control", "args": %s }' % control)
        # LOGGER.debug(response_id)
        # await self._atrea.update(response_id)

    @property
    def fan_mode(self):
        """Return the current fan mode."""
        if self._fan_power_req:
            return str(round(self._fan_power_req, -1))
        return "0"

    @property
    def fan_modes(self):
        return ["0", "20", "40", "50", "60", "70", "80", "90", "100"]

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        # LOGGER.debug("fan_power_req %s ", fan_mode)
        # TODO move to Atrea_aMotion set_fan?
        # control = json.dumps({'variables': {'fan_power_req': int(fan_mode)}})
        # LOGGER.debug(control)
        # response_id = await self._atrea.send('{ "endpoint": "control", "args": %s }' % control)
        await self._atrea.publish_wss(
            {
                "endpoint": "control",
                "args": {"variables": {"fan_power_req_sup": int(fan_mode)}},
            }
        )
        # LOGGER.debug("atrea send called")
        # LOGGER.debug(response_id)
        # await self._atrea.update(response_id)

    async def async_update(self):
        r = self._atrea.ui_info()
        self._attr_current_temperature = r.get("temp_ida", None)
        self._attr_hvac_mode = MODE_CURRENT_MAP.get(
            r.get("work_regime", None), HVACMode.OFF
        )
        self._setpoint = r.get("temp_request", None)
        self._fan_power_req = r.get("fan_power_req", None)
        await self._atrea.async_update()


#          "fan_eta_factor":0,
#          "fan_sup_factor":0,
#          "mode_current":"OFF",
#          "season_current":"NON_HEATING",
#          "temp_eha":19.3,
#          "temp_eta":21.4,
#          "temp_ida":21.4,
#          "temp_oda":null,
#          "temp_oda_mean":null,
#          "temp_sup":null

# ui_info response:
# {
#    "code":"OK",
#    "error":null,
#    "id":null,
#    "response":{
#       "requests":{
#          "bypass_control_req":"CLOSED",
#          "fan_power_req":50,
#          "fan_power_req_eta":40,
#          "fan_power_req_sup":49,
#          "temp_request":23.0,
#          "work_regime":"NIGHT_PRECOOLING"
#       },
#       "states":{
#          "active":{
#             "105":{
#                "active":true,
#                "name":"FILTER_INTERVAL"
#             }
#          }
#       },
#       "unit":{
#          "fan_eta_factor":0,
#          "fan_sup_factor":0,
#          "mode_current":"OFF",
#          "season_current":"NON_HEATING",
#          "temp_eha":19.3,
#          "temp_eta":21.4,
#          "temp_ida":21.4,
#          "temp_oda":null,
#          "temp_oda_mean":null,
#          "temp_sup":null
#       }
#    },
#    "type":"response"
# }


# {
#    "args":{
#       "requests":{
#          "fan_power_req":60,
#          "temp_request":20.0,
#          "work_regime":"VENTILATION"
#       },
#       "states":{
#          "active":{
#          }
#       },
#       "unit":{
#          "fan_eta_factor":60,
#          "fan_sup_factor":60,
#          "mode_current":"NORMAL",
#          "season_current":"NON_HEATING",
#          "temp_eha":23.4,
#          "temp_eta":23.6,
#          "temp_ida":23.6,
#          "temp_oda":16.5,
#          "temp_oda_mean":17.95,
#          "temp_sup":17.8
#       }
#    },
#    "event":"ui_info",
#    "type":"event"
# }

# {
#    "args":{
#       "requests":{
#          "bypass_control_req":"CLOSED",
#          "fan_power_req":50,
#          "fan_power_req_eta":40,
#          "fan_power_req_sup":49,
#          "temp_request":23.0,
#          "work_regime":"VENTILATION"
#       },
#       "states":{
#          "active":{
#             "105":{
#                "active":true,
#                "name":"FILTER_INTERVAL"
#             }
#          }
#       },
#       "unit":{
#          "fan_eta_factor":0,
#          "fan_sup_factor":0,
#          "mode_current":"OFF",
#          "season_current":"NON_HEATING",
#          "temp_eha":20.5,
#          "temp_eta":21.4,
#          "temp_ida":21.4,
#          "temp_oda":null,
#          "temp_oda_mean":null,
#          "temp_sup":null
#       }
#    },
#    "event":"ui_info",
#    "type":"event"
# }


# {
#    "active":false,
#    "countdown":0,
#    "finish":{
#       "day":0,
#       "hour":0,
#       "minute":0,
#       "month":0,
#       "year":0
#    },
#    "sceneId":0,
#    "start":{
#       "day":0,
#       "hour":0,
#       "minute":0,
#       "month":0,
#       "year":0
#    }
# }
