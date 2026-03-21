"""Switch entities for Atrea aMotion."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


@dataclass(frozen=True)
class AtreaSwitchDescription:
    """Description for aMotion switch entities."""

    key: str
    name: str
    icon: str
    value_key: str
    setter: str


ATREA_SWITCHES: tuple[AtreaSwitchDescription, ...] = (
    AtreaSwitchDescription(
        key="modbus_enabled",
        name="Modbus TCP",
        icon="mdi:transit-connection-variant",
        value_key="modbus_enabled",
        setter="async_set_modbus_enabled",
    ),
    AtreaSwitchDescription(
        key="autoupdate_enabled",
        name="Firmware auto update",
        icon="mdi:package-up",
        value_key="autoupdate_enabled",
        setter="async_set_autoupdate_enabled",
    ),
)


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up switch entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    sensor_name = entry.data.get(CONF_NAME) or "atrea"
    async_add_entities(
        [
            AtreaToggleSwitch(coordinator, entry, description, sensor_name)
            for description in ATREA_SWITCHES
            if coordinator.value(description.value_key) is not None
        ]
    )


class AtreaToggleSwitch(SwitchEntity):
    """Generic on/off switch backed by websocket actions."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: AtreaSwitchDescription,
        sensor_name: str,
    ) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
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
        """Update state."""
        self.schedule_update_ha_state()

    @property
    def is_on(self) -> bool:
        """Return switch state."""
        return bool(self.coordinator.value(self.entity_description.value_key))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await getattr(self.coordinator, self.entity_description.setter)(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await getattr(self.coordinator, self.entity_description.setter)(False)
