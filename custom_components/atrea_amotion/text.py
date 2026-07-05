"""Text entities for Atrea aMotion."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    if not coordinator.async_state().discovery.get("name"):
        return

    sensor_name = entry.data.get(CONF_NAME) or "atrea"
    async_add_entities([AtreaUnitNameText(coordinator, entry, sensor_name)])


class AtreaUnitNameText(TextEntity):
    """Editable unit name."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Unit name"
    _attr_native_min = 1
    _attr_native_max = 64
    _attr_mode = "text"

    def __init__(self, coordinator, entry: ConfigEntry, sensor_name: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-unit-name"
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
        """Update entity state."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return current unit name."""
        return self.coordinator.async_state().discovery.get("name", "")

    async def async_set_value(self, value: str) -> None:
        """Set a new unit name."""
        await self.coordinator.async_set_unit_name(value)
