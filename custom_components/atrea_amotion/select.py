"""Select entities for Atrea aMotion."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


BYPASS_LABELS = {
    "AUTO": "Auto",
    "OPEN": "Open",
    "CLOSED": "Closed",
}

CONFIG_SELECTS = {
    "season_request": {
        "name": "Season settings",
        "labels": {
            "HEATING": "Heating",
            "NON_HEATING": "Non-heating",
            "AUTO_TODA": "Outdoor temp. mean",
            "AUTO_TODA_RATIO": "T-ODA mean+gain",
            "USER": "User",
        },
    },
    "temp_oda_mean_interval": {
        "name": "T-ODA averaging time slot",
        "labels": {
            "HOURS_1": "1 hour",
            "HOURS_3": "3 hours",
            "HOURS_6": "6 hours",
            "HOURS_12": "12 hours",
            "DAYS_1": "1 day",
            "DAYS_2": "2 days",
            "DAYS_3": "3 days",
            "DAYS_4": "4 days",
            "DAYS_5": "5 days",
            "DAYS_6": "6 days",
            "DAYS_7": "7 days",
            "DAYS_8": "8 days",
            "DAYS_9": "9 days",
            "DAYS_10": "10 days",
        },
    },
}


def _label_for_option(option: str, labels: dict[str, str] | None = None) -> str:
    """Return a user-friendly label for a raw option."""
    mapping = labels or BYPASS_LABELS
    return mapping.get(option, option.replace("_", " ").title())


def _option_for_label(label: str, raw_options: list[str], labels: dict[str, str] | None = None) -> str:
    """Return the raw option for a selected label."""
    for option in raw_options:
        if _label_for_option(option, labels) == label:
            return option
    return label


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["atrea"]
    sensor_name = entry.data.get(CONF_NAME) or "aatrea"
    if not coordinator.async_capabilities().has_bypass_control:
        entities = []
    else:
        entities = [AtreaBypassSelect(coordinator, entry, sensor_name)]
    entities.extend(
        AtreaConfigSelect(coordinator, entry, sensor_name, key, meta["name"], meta["labels"])
        for key, meta in CONFIG_SELECTS.items()
        if key in coordinator.async_capabilities().config_fields
    )
    if entities:
        async_add_entities(entities)


class AtreaBypassSelect(SelectEntity):
    """Bypass mode select."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, sensor_name: str) -> None:
        self.coordinator = coordinator
        self._raw_options = coordinator.async_capabilities().enum_for("bypass_control_req")
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-bypass"
        self._attr_name = "Bypass mode"
        self._attr_options = [_label_for_option(option) for option in self._raw_options]
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
    def current_option(self) -> str | None:
        """Return selected bypass mode."""
        option = self.coordinator.value("stored_bypass_control_req") or self.coordinator.requested_value(
            "bypass_control_req"
        )
        if option is None:
            return None
        return _label_for_option(option)

    async def async_select_option(self, option: str) -> None:
        """Set bypass mode."""
        await self.coordinator.async_control(
            {"bypass_control_req": _option_for_label(option, self._raw_options)}
        )


class AtreaConfigSelect(SelectEntity):
    """Select entity backed by Atrea config values."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        sensor_name: str,
        key: str,
        name: str,
        labels: dict[str, str],
    ) -> None:
        self.coordinator = coordinator
        self._key = key
        self._labels = labels
        self._raw_options = coordinator.async_capabilities().enum_for(key)
        self._attr_unique_id = f"{sensor_name}-{entry.data.get(CONF_HOST)}-{key}"
        self._attr_name = name
        self._attr_options = [_label_for_option(option, self._labels) for option in self._raw_options]
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
    def current_option(self) -> str | None:
        """Return selected config option."""
        option = self.coordinator.config_value(self._key)
        if option is None:
            return None
        return _label_for_option(option, self._labels)

    async def async_select_option(self, option: str) -> None:
        """Set config option."""
        await self.coordinator.async_set_config(
            self._key,
            _option_for_label(option, self._raw_options, self._labels),
        )
