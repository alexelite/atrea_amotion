"""Button entities for Atrea aMotion."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .identity import AtreaAvailability, device_identity, device_info
from .registry_migration import with_compatibility_aliases


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from a config entry."""
    async_add_entities = with_compatibility_aliases(hass, entry, "button", async_add_entities)
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    sensor_name = entry.data.get(CONF_NAME) or "atrea"
    entities: list[ButtonEntity] = [AtreaRebootButton(coordinator, entry, sensor_name)]
    if coordinator.value("filters") is not None or coordinator.value("last_filter_reset") is not None:
        entities.append(AtreaFilterResetButton(coordinator, entry, sensor_name))
    async_add_entities(entities)


class AtreaFilterResetButton(AtreaAvailability, ButtonEntity):
    """Button that confirms filter replacement on the unit."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry, sensor_name: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{device_identity(entry)}-reset-filter"
        self._attr_name = "Confirm filter replacement"
        self._attr_icon = "mdi:air-filter"
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
        """Update entity state."""
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Confirm filter replacement."""
        await self.coordinator.async_reset_filter_interval()


class AtreaRebootButton(AtreaAvailability, ButtonEntity):
    """Button that requests a device reboot."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry, sensor_name: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{device_identity(entry)}-reboot"
        self._attr_name = "Reboot unit"
        self._attr_icon = "mdi:restart-alert"
        self._attr_device_info = device_info(entry, coordinator, sensor_name)
        self._attr_extra_state_attributes = {
            "warning": "Manufacturer recommends switching the unit off before reboot."
        }
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
        """Update entity state."""
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Request reboot."""
        await self.coordinator.async_reboot()
