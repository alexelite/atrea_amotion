"""Number entities for Atrea aMotion config values."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


CONFIG_NUMBERS = {
    "season_switch_temp": "Season switch temperature",
    "temp_ida_heater_hyst": "T-IDA hysteresis for heating",
    "temp_ida_cooler_hyst": "T-IDA hysteresis for cooling",
    "temp_cool_active_offset": "Temperature offset for cooler activation",
}


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    sensor_name = entry.data.get(CONF_NAME) or "aatrea"
    entities = [
        AtreaConfigNumber(coordinator, entry, sensor_name, key, name)
        for key, name in CONFIG_NUMBERS.items()
        if key in coordinator.async_capabilities().config_fields
    ]
    if entities:
        async_add_entities(entities)


class AtreaConfigNumber(NumberEntity):
    """Number entity backed by Atrea config values."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = NumberDeviceClass.TEMPERATURE

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        sensor_name: str,
        key: str,
        name: str,
    ) -> None:
        self.coordinator = coordinator
        self._key = key
        range_meta = coordinator.async_capabilities().range_for(key)
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-{key}"
        self._attr_name = name
        self._attr_native_min_value = range_meta.get("min")
        self._attr_native_max_value = range_meta.get("max")
        self._attr_native_step = range_meta.get("step")
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
    def native_value(self) -> float | None:
        """Return current config value."""
        value = self.coordinator.config_value(self._key)
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Set config value."""
        await self.coordinator.async_set_config(self._key, float(value))
