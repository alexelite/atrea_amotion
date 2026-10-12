"""Migrate hardware identity while preserving every existing HA reference."""

from collections import defaultdict
from copy import copy

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, LOGGER
from .identity import device_identity, serial_number


@callback
def async_migrate_registry(hass, entry):
    """Change internal keys only; never delete or rename a device or entity."""
    devices_registry = dr.async_get(hass)
    entities_registry = er.async_get(hass)
    identity = device_identity(entry)
    devices = [
        device for device in dr.async_entries_for_config_entry(devices_registry, entry.entry_id)
        if any(domain == DOMAIN for domain, _ in device.identifiers)
    ]
    if not devices:
        return {}

    serial = serial_number(entry.data)
    if any(device.serial_number and serial and device.serial_number != serial for device in devices):
        raise ConfigEntryNotReady("Registry devices have conflicting serial numbers")

    # The earliest device is the original referenced by existing automations.
    primary = min(devices, key=lambda device: (device.created_at, device.id))
    device_keys = {
        device.id: identity if device.id == primary.id else f"{identity}:compat:{device.id}"
        for device in devices
    }
    prefixes = {
        device.id: sorted(
            (value for domain, value in device.identifiers if domain == DOMAIN),
            key=len, reverse=True,
        )
        for device in devices
    }
    all_prefixes = sorted({value for values in prefixes.values() for value in values}, key=len, reverse=True)
    groups = defaultdict(list)
    for entity in er.async_entries_for_config_entry(entities_registry, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        alias_prefix = f"{identity}-compat:{entity.id}-"
        if entity.unique_id.startswith(alias_prefix):
            key = entity.unique_id[len(alias_prefix):]
        elif entity.unique_id.startswith(f"{identity}-"):
            key = entity.unique_id[len(identity) + 1:]
        else:
            key = next((
                entity.unique_id[len(prefix) + 1:]
                for prefix in prefixes.get(entity.device_id, all_prefixes)
                if entity.unique_id.startswith(f"{prefix}-")
            ), None)
        if key:
            groups[(entity.domain, key)].append(entity)

    plans = []
    aliases = defaultdict(list)
    for (domain, key), entities in groups.items():
        originals = [entity for entity in entities if entity.device_id in {primary.id, None}]
        canonical = min(originals, key=lambda entity: (entity.created_at, entity.id)) if originals else None
        for entity in entities:
            if canonical is not None and entity.id == canonical.id:
                target_unique_id = f"{identity}-{key}"
                target_device_id = primary.id
            else:
                target_unique_id = f"{identity}-compat:{entity.id}-{key}"
                target_device_id = entity.device_id if entity.device_id in device_keys else primary.id
                aliases[(domain, f"{identity}-{key}")].append({
                    "unique_id": target_unique_id,
                    "device_identity": device_keys[target_device_id],
                })
            plans.append((entity, target_unique_id, target_device_id))

    # Validate the entire plan before touching either registry.
    planned_ids = {entity.entity_id for entity, _, _ in plans}
    for entity, target_unique_id, _ in plans:
        owner = entities_registry.async_get_entity_id(entity.domain, DOMAIN, target_unique_id)
        if owner is not None and owner not in planned_ids:
            raise ConfigEntryNotReady("Stable entity identity is already owned by another config entry")
    device_ids = set(device_keys)
    for device in devices_registry.devices:
        if device.id not in device_ids and any(
            (DOMAIN, key) in device.identifiers for key in device_keys.values()
        ):
            raise ConfigEntryNotReady("Stable device identity is already owned by another config entry")

    # Move duplicate keys out of the way before promoting the original records.
    changed = 0
    for entity, target_unique_id, target_device_id in sorted(
        plans, key=lambda plan: "-compat:" not in plan[1]
    ):
        if entity.unique_id != target_unique_id or entity.device_id != target_device_id:
            entities_registry.async_update_entity(
                entity.entity_id, new_unique_id=target_unique_id, device_id=target_device_id
            )
            changed += 1
    for device in sorted(devices, key=lambda device: device.id == primary.id):
        identifiers = {
            identifier for identifier in device.identifiers if identifier[0] != DOMAIN
        } | {(DOMAIN, device_keys[device.id])}
        if identifiers != device.identifiers or (serial and device.serial_number != serial):
            devices_registry.async_update_device(
                device.id, new_identifiers=identifiers, serial_number=serial
            )
            changed += 1
    if changed:
        LOGGER.info(
            "Migrated hardware identity for config entry %s: %s registry records; "
            "preserved device IDs, entity IDs and %s compatibility entities",
            entry.entry_id, changed, sum(map(len, aliases.values())),
        )
    return dict(aliases)


def with_compatibility_aliases(hass, entry, domain, add_entities):
    """Keep previously duplicated entity and device references operational."""
    aliases = hass.data[DOMAIN][entry.entry_id].get("identity_aliases", {})

    def add_with_aliases(entities, *args, **kwargs):
        expanded = []
        for entity in entities:
            expanded.append(entity)
            for alias in aliases.get((domain, entity.unique_id), []):
                compatibility_entity = copy(entity)
                compatibility_entity._attr_unique_id = alias["unique_id"]
                compatibility_entity._attr_device_info = {
                    **entity.device_info,
                    "identifiers": {(DOMAIN, alias["device_identity"])},
                }
                # Entity exposes these as cached properties. A shallow copy
                # must not inherit the canonical entity's already-read values.
                compatibility_entity.__dict__.pop("unique_id", None)
                compatibility_entity.__dict__.pop("device_info", None)
                expanded.append(compatibility_entity)
        add_entities(expanded, *args, **kwargs)

    return add_with_aliases
