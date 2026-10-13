"""Hardware identity must survive network and display-name changes."""

from types import SimpleNamespace

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import is_callback

from custom_components.atrea_amotion import AtreaAMotionCoordinator
from custom_components.atrea_amotion.button import AtreaFilterResetButton, AtreaRebootButton
from custom_components.atrea_amotion.climate import AtreaAMotionClimate
from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.fan import AtreaAMotionFan
from custom_components.atrea_amotion.identity import device_identity
from custom_components.atrea_amotion.number import AtreaConfigNumber
from custom_components.atrea_amotion.select import AtreaBypassSelect, AtreaConfigSelect
from custom_components.atrea_amotion.sensor import ATREA_SENSORS, AtreaAMotionSensor
from custom_components.atrea_amotion.switch import AtreaSwitchDescription, AtreaToggleSwitch
from custom_components.atrea_amotion.text import AtreaUnitNameText


@pytest.mark.parametrize("factory", [
    lambda c, e, n: AtreaAMotionClimate(c, e, n),
    lambda c, e, n: AtreaAMotionFan(c, e, n, "fan_power_req", "Fan"),
    lambda c, e, n: AtreaAMotionSensor(c, e, ATREA_SENSORS[0], n),
    lambda c, e, n: AtreaFilterResetButton(c, e, n),
    lambda c, e, n: AtreaRebootButton(c, e, n),
    lambda c, e, n: AtreaConfigNumber(c, e, n, "season_switch_temp", "Temperature"),
    lambda c, e, n: AtreaBypassSelect(c, e, n),
    lambda c, e, n: AtreaConfigSelect(c, e, n, "season_request", "Season", {}),
    lambda c, e, n: AtreaToggleSwitch(c, e, AtreaSwitchDescription(key="modbus", name="Modbus"), n),
    lambda c, e, n: AtreaUnitNameText(c, e, n),
])
def test_all_platforms_keep_identity_when_ip_and_name_change(hass, MockConfigEntry, factory):
    coordinator = AtreaAMotionCoordinator(hass, "Atrea", "192.0.2.10", "user", "pass", "aMotion", "1")
    entities = []
    for host, name in [("192.0.2.10", "Original"), ("192.0.2.20", "Renamed")]:
        entry = MockConfigEntry(domain=DOMAIN, data={CONF_NAME: name, CONF_HOST: host, "production_number": "SN-1"})
        entities.append(factory(coordinator, entry, name))
    assert is_callback(entities[0]._handle_coordinator_update)
    assert entities[0].unique_id == entities[1].unique_id
    assert entities[0].device_info["identifiers"] == {(DOMAIN, "production:SN-1")}
    assert entities[1].device_info["identifiers"] == entities[0].device_info["identifiers"]
    assert entities[0].device_info["serial_number"] == "SN-1"
    assert not entities[0].available
    coordinator.socket_state = "Open"
    coordinator._authorized = True
    coordinator._ui_info_ready.set()
    coordinator._diagram_ready.set()
    coordinator._moments_ready.set()
    assert entities[0].available
    coordinator.on_close(None, 1000, "closed")
    assert not entities[0].available


def test_saved_fallback_never_changes_when_serial_becomes_available():
    entry = SimpleNamespace(entry_id="entry-1", data={"device_identity": "board:board-1", "production_number": "SN-1"})
    assert device_identity(entry) == "board:board-1"


def test_missing_hardware_uses_entry_not_ip():
    entry = SimpleNamespace(entry_id="entry-1", data={CONF_HOST: "192.0.2.10"})
    assert device_identity(entry) == "entry:entry-1"


def test_different_serials_have_different_identities(MockConfigEntry):
    entries = [MockConfigEntry(domain=DOMAIN, data={"production_number": serial}) for serial in ("SN-1", "SN-2")]
    assert device_identity(entries[0]) != device_identity(entries[1])


async def test_filter_days_use_home_assistant_local_date(hass, MockConfigEntry, freezer):
    """At midnight in Bucharest the countdown must use the new local day."""
    await hass.config.async_set_time_zone("Europe/Bucharest")
    freezer.move_to("2026-10-11T21:30:00+00:00")
    coordinator = AtreaAMotionCoordinator(hass, "Atrea", "192.0.2.10", "user", "pass", "aMotion", "1")
    coordinator._apply_moments({"filters": {"year": 2026, "month": 9, "day": 20}})
    entry = MockConfigEntry(domain=DOMAIN, data={"production_number": "SN-1"})
    description = next(d for d in ATREA_SENSORS if d.key == "filter_service_days_remaining")
    sensor = AtreaAMotionSensor(coordinator, entry, description, "Atrea")
    climate = AtreaAMotionClimate(coordinator, entry, "Atrea")
    assert sensor.native_value == -22
    assert climate.extra_state_attributes["filter_days_remaining"] == -22
