"""Demo fan platform that has a fake fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    UnitOfEnergy,
    UnitOfTemperature,
    PERCENTAGE,
)
from .const import (
    DOMAIN,
    LOGGER,
)

PRESET_MODE_AUTO = "auto"
PRESET_MODE_SMART = "smart"
PRESET_MODE_SLEEP = "sleep"
PRESET_MODE_ON = "on"

FULL_SUPPORT = (
    FanEntityFeature.SET_SPEED
    | FanEntityFeature.OSCILLATE
    | FanEntityFeature.DIRECTION
    | FanEntityFeature.TURN_OFF
    | FanEntityFeature.TURN_ON
)
LIMITED_SUPPORT = (
    FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Demo config entry."""
    sensor_name = entry.data.get(CONF_NAME)
    # LOGGER.debug("sensor sensor_name: '%s' ", sensor_name)
    if sensor_name is None:
        sensor_name = "aatrea"
    async_add_entities(
        [
            Atrea_aMotionFan(
                hass,
                entry,
                sensor_name,
                "EHA",
                "Percentage Full Fan",
                LIMITED_SUPPORT,
            ),
            Atrea_aMotionFan(
                hass,
                entry,
                sensor_name,
                "SUP",
                "Percentage Full Fan",
                LIMITED_SUPPORT,
            ),
        ]
    )


class BaseFan(FanEntity):
    """A demonstration fan component that uses legacy fan speeds."""

    _attr_should_poll = False
    _attr_translation_key = "demo"
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        sensor_name: str,
        key: str,
        name: str,
        supported_features: FanEntityFeature,
        # preset_modes: list[str] | None,
    ) -> None:
        """Initialize the entity."""
        self.hass = hass
        self.data = hass.data[DOMAIN][entry.entry_id]
        self._atrea = self.data["atrea"]
        self._attr_unique_id = "%s-%s-%s" % (
            sensor_name,
            entry.data.get(CONF_HOST),
            key,
        )
        self._attr_supported_features = supported_features
        self._percentage: int | None = None
        # self._preset_modes = preset_modes
        # self._preset_mode: str | None = None
        self._oscillating: bool | None = None
        self._direction: str | None = None
        self._attr_name = name
        self._name = sensor_name
        if supported_features & FanEntityFeature.OSCILLATE:
            self._oscillating = False
        if supported_features & FanEntityFeature.DIRECTION:
            self._direction = "forward"
        self._device_unique_id = "%s-%s" % (sensor_name, entry.data.get(CONF_HOST))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_unique_id)},
            manufacturer="Atrea CZ",
            model=self._atrea.model,
            name=self._name,
            sw_version=self._atrea.version,
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._attr_unique_id

    @property
    def current_direction(self) -> str | None:
        """Fan direction."""
        return self._direction

    @property
    def oscillating(self) -> bool | None:
        """Oscillating."""
        return self._oscillating


class Atrea_aMotionFan(BaseFan, FanEntity):
    """An async demonstration fan component that uses percentages."""

    @property
    def percentage(self) -> int | None:
        """Return the current speed."""
        return self._percentage

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return 100

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        self._percentage = percentage
        # self._preset_mode = None
        self.async_write_ha_state()

    # @property
    # def preset_mode(self) -> str | None:
    #     """Return the current preset mode, e.g., auto, smart, interval, favorite."""
    #     return self._preset_mode

    # @property
    # def preset_modes(self) -> list[str] | None:
    #     """Return a list of available preset modes."""
    #     return self._preset_modes

    # async def async_set_preset_mode(self, preset_mode: str) -> None:
    #     """Set new preset mode."""
    #     self._preset_mode = preset_mode
    #     self._percentage = None
    #     self.async_write_ha_state()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        # preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the entity."""
        # if preset_mode:
        #     await self.async_set_preset_mode(preset_mode)
        #     return

        if percentage is None:
            percentage = 67

        await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the entity."""
        await self.async_oscillate(False)
        await self.async_set_percentage(0)

    async def async_set_direction(self, direction: str) -> None:
        """Set the direction of the fan."""
        self._direction = direction
        self.async_write_ha_state()

    async def async_oscillate(self, oscillating: bool) -> None:
        """Set oscillation."""
        self._oscillating = oscillating
        self.async_write_ha_state()
