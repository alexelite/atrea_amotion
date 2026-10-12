"""Upgrade real HA registry records without changing automation references."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.atrea_amotion import AtreaAMotionCoordinator
from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.registry_migration import async_migrate_registry
from custom_components.atrea_amotion.sensor import async_setup_entry as setup_sensors
from custom_components.atrea_amotion.text import async_setup_entry as setup_text


def entry_for(hass, factory, serial="SN-1", domain=DOMAIN):
    entry = factory(domain=domain, data={CONF_NAME: "Atrea aMotion", CONF_HOST: "192.168.1.121", "production_number": serial})
    entry.add_to_hass(hass)
    return entry


def device_for(registry, entry, identity, name=None, domain=DOMAIN):
    device = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(domain, identity)}, name="Atrea aMotion")
    if name:
        device = registry.async_update_device(device.id, name_by_user=name)
    return device


def entity_for(registry, entry, device, identity, key="outside_temperature", domain="sensor", object_id="outside_air", disabled_by=None):
    return registry.async_get_or_create(domain, DOMAIN, f"{identity}-{key}", config_entry=entry, device_id=device.id, suggested_object_id=object_id, disabled_by=disabled_by)


def test_clean_upgrade_preserves_ids_settings_and_other_integrations(hass, MockConfigEntry, device_registry, entity_registry):
    entry = entry_for(hass, MockConfigEntry)
    original = device_for(device_registry, entry, "Atrea aMotion-192.168.1.61", "Atrea CORP B TC")
    entity = entity_for(entity_registry, entry, original, "Atrea aMotion-192.168.1.61")
    entity = entity_registry.async_update_entity(entity.entity_id, name="Outside", icon="mdi:thermometer", disabled_by=er.RegistryEntryDisabler.USER)
    other = entry_for(hass, MockConfigEntry, serial="SN-2")
    other_device = device_for(device_registry, other, "Atrea aMotion-192.168.1.67")
    other_entity = entity_for(entity_registry, other, other_device, "Atrea aMotion-192.168.1.67", object_id="other_outside")
    legacy = entry_for(hass, MockConfigEntry, domain="amotionatrea")
    legacy_device = device_for(device_registry, legacy, "Corp B TC-192.168.1.61", domain="amotionatrea")

    assert async_migrate_registry(hass, entry) == {}
    updated = entity_registry.async_get(entity.entity_id)
    assert updated.id == entity.id
    assert updated.device_id == original.id
    assert updated.unique_id == "production:SN-1-outside_temperature"
    assert updated.name == "Outside"
    assert updated.icon == "mdi:thermometer"
    assert updated.disabled_by is er.RegistryEntryDisabler.USER
    assert device_registry.async_get(original.id).name_by_user == "Atrea CORP B TC"
    assert device_registry.async_get(original.id).identifiers == {(DOMAIN, "production:SN-1")}
    assert device_registry.async_get(original.id).serial_number == "SN-1"
    assert device_registry.async_get(other_device.id) == other_device
    assert entity_registry.async_get(other_entity.entity_id) == other_entity
    assert device_registry.async_get(legacy_device.id) == legacy_device
    assert len(device_registry.devices) == 3
    assert len(entity_registry.entities) == 2
    snapshot = (tuple(device_registry.devices), dict(entity_registry.entities))
    assert async_migrate_registry(hass, entry) == {}
    assert snapshot == (tuple(device_registry.devices), dict(entity_registry.entities))


async def test_duplicate_upgrade_keeps_both_automation_targets_working(hass, MockConfigEntry, device_registry, entity_registry, freezer):
    entry = entry_for(hass, MockConfigEntry)
    freezer.move_to("2026-04-03T00:00:00+00:00")
    original = device_for(device_registry, entry, "Atrea aMotion-192.168.1.61", "Atrea CORP B TC")
    old_entity = entity_for(entity_registry, entry, original, "Atrea aMotion-192.168.1.61")
    old_text = entity_for(entity_registry, entry, original, "Atrea aMotion-192.168.1.61", "unit-name", "text", "unit_name")
    freezer.move_to("2026-10-12T05:24:53+00:00")
    duplicate = device_for(device_registry, entry, "Atrea aMotion-192.168.1.121")
    new_entity = entity_for(entity_registry, entry, duplicate, "Atrea aMotion-192.168.1.121", object_id="outside_air_5")
    new_text = entity_for(entity_registry, entry, duplicate, "Atrea aMotion-192.168.1.121", "unit-name", "text", "unit_name_5")
    aliases = async_migrate_registry(hass, entry)
    assert entity_registry.async_get(old_entity.entity_id).unique_id == "production:SN-1-outside_temperature"
    for record in (old_entity, new_entity, old_text, new_text):
        updated = entity_registry.async_get(record.entity_id)
        assert updated.id == record.id
        assert updated.device_id == record.device_id
    assert len(device_registry.devices) == 2
    assert len(entity_registry.entities) == 4
    assert aliases == async_migrate_registry(hass, entry)

    coordinator = AtreaAMotionCoordinator(hass, "Atrea", "192.168.1.121", "user", "pass", "aMotion", "1")
    coordinator.capabilities.unit_fields = {"temp_oda"}
    coordinator.state.unit["temp_oda"] = 16.5
    coordinator.async_set_unit_name = AsyncMock(return_value=True)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"atrea": coordinator, "identity_aliases": aliases}
    sensors = []
    await setup_sensors(hass, entry, sensors.extend)
    for record in (old_entity, new_entity):
        migrated = entity_registry.async_get(record.entity_id)
        sensor = next(entity for entity in sensors if entity.unique_id == migrated.unique_id)
        assert sensor.native_value == 16.5
        assert sensor.device_info["identifiers"] == device_registry.async_get(record.device_id).identifiers
    texts = []
    await setup_text(hass, entry, texts.extend)
    for record in (old_text, new_text):
        migrated = entity_registry.async_get(record.entity_id)
        text = next(entity for entity in texts if entity.unique_id == migrated.unique_id)
        await text.async_set_value("Renamed")
    assert coordinator.async_set_unit_name.await_count == 2


def test_already_created_stable_duplicate_does_not_steal_original_ids(hass, MockConfigEntry, device_registry, entity_registry, freezer):
    entry = entry_for(hass, MockConfigEntry)
    freezer.move_to("2026-04-03T00:00:00+00:00")
    original = device_for(device_registry, entry, "Atrea aMotion-192.168.1.61")
    old = entity_for(entity_registry, entry, original, "Atrea aMotion-192.168.1.61")
    freezer.move_to("2026-10-12T05:24:53+00:00")
    duplicate = device_for(device_registry, entry, "production:SN-1")
    new = entity_for(entity_registry, entry, duplicate, "production:SN-1", object_id="outside_5")
    async_migrate_registry(hass, entry)
    assert entity_registry.async_get(old.entity_id).unique_id == "production:SN-1-outside_temperature"
    assert entity_registry.async_get(new.entity_id).unique_id.startswith("production:SN-1-compat:")
    assert device_registry.async_get(original.id).identifiers == {(DOMAIN, "production:SN-1")}


def test_entity_only_present_on_duplicate_keeps_its_device_target(hass, MockConfigEntry, device_registry, entity_registry, freezer):
    entry = entry_for(hass, MockConfigEntry)
    freezer.move_to("2026-04-03T00:00:00+00:00")
    device_for(device_registry, entry, "Atrea aMotion-192.168.1.61")
    freezer.move_to("2026-10-12T05:24:53+00:00")
    duplicate = device_for(device_registry, entry, "Atrea aMotion-192.168.1.121")
    entity = entity_for(entity_registry, entry, duplicate, "Atrea aMotion-192.168.1.121")
    aliases = async_migrate_registry(hass, entry)
    assert entity_registry.async_get(entity.entity_id).device_id == duplicate.id
    assert aliases[("sensor", "production:SN-1-outside_temperature")]
    assert aliases == async_migrate_registry(hass, entry)


def test_conflicting_identity_aborts_without_changing_any_record(hass, MockConfigEntry, device_registry, entity_registry):
    entry = entry_for(hass, MockConfigEntry)
    original = device_for(device_registry, entry, "Atrea aMotion-192.168.1.61")
    entity_for(entity_registry, entry, original, "Atrea aMotion-192.168.1.61")
    other = entry_for(hass, MockConfigEntry)
    other_device = device_for(device_registry, other, "foreign")
    entity_for(entity_registry, other, other_device, "production:SN-1")
    snapshot = (tuple(device_registry.devices), dict(entity_registry.entities))
    with pytest.raises(ConfigEntryNotReady):
        async_migrate_registry(hass, entry)
    assert snapshot == (tuple(device_registry.devices), dict(entity_registry.entities))


@pytest.mark.parametrize("duplicate_exists", [False, True])
async def test_full_setup_and_reload_reuse_original_and_duplicate_records(hass, MockConfigEntry, device_registry, entity_registry, freezer, duplicate_exists):
    """Real HA platform loading must not create a third device or lose targets."""
    entry = entry_for(hass, MockConfigEntry)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_USERNAME: "user", CONF_PASSWORD: "pass"})
    freezer.move_to("2026-04-03T00:00:00+00:00")
    original = device_for(device_registry, entry, "Atrea aMotion-192.168.1.61", "Atrea CORP B TC")
    old_entity = entity_for(entity_registry, entry, original, "Atrea aMotion-192.168.1.61")
    freezer.move_to("2026-10-12T05:24:53+00:00")
    records = [old_entity]
    if duplicate_exists:
        duplicate = device_for(device_registry, entry, "Atrea aMotion-192.168.1.121")
        records.append(entity_for(entity_registry, entry, duplicate, "Atrea aMotion-192.168.1.121", object_id="outside_air_5"))
    expected_devices = len(records)

    async def initialize(coordinator):
        coordinator.state.discovery["production_number"] = "SN-1"
        coordinator._serial_verified = True
        coordinator.socket_state = "Open"
        coordinator._authorized = True
        coordinator.capabilities.unit_fields = {"temp_oda"}
        coordinator._apply_ui_info({"unit": {"temp_oda": 16.5}})
        coordinator._apply_ui_diagram_data({})
        coordinator._apply_moments({})

    with patch("custom_components.atrea_amotion.AtreaAMotionCoordinator.async_initialize", initialize):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        for record in records:
            assert hass.states.get(record.entity_id).state == "16.5"
            assert entity_registry.async_get(record.entity_id).device_id == record.device_id
        assert len(device_registry.devices) == expected_devices
        count = len(entity_registry.entities)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert len(device_registry.devices) == expected_devices
        assert len(entity_registry.entities) == count
        for record in records:
            assert hass.states.get(record.entity_id).state == "16.5"
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
