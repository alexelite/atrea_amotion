"""Tests for the Atrea coordinator."""

from __future__ import annotations

from custom_components.atrea_amotion.__init__ import AtreaAMotionCoordinator


def test_ui_diagram_data_nested_payload_is_unwrapped(hass) -> None:
    """Nested ui_diagram_data payloads should be flattened for derived sensors."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator._apply_ui_diagram_data(
        {
            "ui_diagram_data": {
                "bypass_estim": 0,
                "damper_io_state": True,
                "fan_eta_operating_time": 12602,
                "fan_sup_operating_time": 12602,
            }
        }
    )

    assert coordinator.value("bypass_estim") == 0
    assert coordinator.value("damper_io_state") is True
    assert coordinator.value("fan_eta_operating_time") == 12602
    assert coordinator.value("fan_sup_operating_time") == 12602


def test_user_config_is_stored_and_available_for_entities(hass) -> None:
    """Persistent config values should be read from user_config_get."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator._apply_user_config(
        {
            "variables": {
                "season_request": "AUTO_TODA",
                "season_switch_temp": 18.5,
                "temp_oda_mean_interval": "HOURS_3",
            }
        }
    )

    assert coordinator.config_value("season_request") == "AUTO_TODA"
    assert coordinator.value("season_switch_temp") == 18.5
    assert coordinator.value("temp_oda_mean_interval") == "HOURS_3"


def test_motor_role_mapping_is_ambiguous_when_counters_match(hass) -> None:
    """Matching motor and fan counters should be reported as ambiguous."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator._apply_moments(
        {
            "m1_register": 45_395_468,
            "m2_register": 45_395_468,
        }
    )
    coordinator._apply_ui_diagram_data(
        {
            "ui_diagram_data": {
                "fan_eta_operating_time": 12609,
                "fan_sup_operating_time": 12609,
            }
        }
    )

    assert coordinator.value("motor_role_mapping") == "ambiguous"


def test_active_notifications_are_normalized_for_cards(hass) -> None:
    """Coordinator should flatten active states into localized card notifications."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator.capabilities.base_states = {
        105: {"id": 105, "purpose": "notify", "severity": 3, "type": "FILTER_INTERVAL"},
        999: {"id": 999, "purpose": "alarm_sr", "severity": 5, "type": "HEATER_FAULT_HEATER_1"},
    }

    coordinator._apply_ui_info(
        {
            "requests": {},
            "unit": {},
            "states": {
                "active": {
                    "105": {"active": True, "name": "FILTER_INTERVAL"},
                    "999": {"active": True, "name": "HEATER_FAULT_HEATER_1"},
                }
            },
        }
    )

    notifications = coordinator.value("notifications")

    assert notifications[0]["message_code"] == "E 999"
    assert notifications[0]["message"] == "Failure of heater A"
    assert notifications[1]["message_code"] == "S 105"
    assert notifications[1]["full_message"] == "S 105 - Filter replacement interval"
    assert coordinator.value("warning_count") == 1
    assert coordinator.value("fault_count") == 1
    assert coordinator.value("has_warning") is True
    assert coordinator.value("has_fault") is True


async def test_async_control_reauthenticates_after_unauthorized(hass) -> None:
    """Control writes should retry once after websocket authorization expires."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    sent_requests: list[tuple[str, object]] = []
    reauth_calls = 0
    control_attempts = 0

    async def fake_async_request(endpoint: str, args: object = None) -> bool:
        sent_requests.append((endpoint, args))
        return True

    async def fake_async_request_message(endpoint: str, args: object = None, timeout: float = 10):
        nonlocal control_attempts
        assert endpoint == "control"
        control_attempts += 1
        if control_attempts == 1:
            return {"id": 1, "code": "UNAUTHORIZED", "response": None, "type": "response"}
        return {"id": 2, "code": "OK", "response": "OK", "type": "response"}

    async def fake_reauthorize() -> bool:
        nonlocal reauth_calls
        reauth_calls += 1
        return True

    coordinator.async_request = fake_async_request  # type: ignore[method-assign]
    coordinator._async_request_message = fake_async_request_message  # type: ignore[method-assign]
    coordinator._async_reauthorize_session = fake_reauthorize  # type: ignore[method-assign]

    assert await coordinator.async_control({"work_regime": "OFF"}) is True
    assert control_attempts == 2
    assert reauth_calls == 1
    assert coordinator.requested_value("work_regime") == "OFF"
    assert ("control_panel", None) in sent_requests
    assert ("ui_info", None) in sent_requests


async def test_async_request_message_times_out_when_response_never_arrives(hass) -> None:
    """Tracked request waiters should be cleaned up after timeouts."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    async def fake_publish_wss(payload):
        return True

    coordinator.publish_wss = fake_publish_wss  # type: ignore[method-assign]

    response = await coordinator._async_request_message("control", {"variables": {}}, timeout=0.01)

    assert response is None
    assert coordinator._response_waiters == {}
    assert coordinator._pending_requests == {}


async def test_async_set_config_refreshes_readback_and_confirms_applied(hass) -> None:
    """Config writes should be confirmed via user_config_get."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    config_reads = 0

    async def fake_async_request(endpoint: str, args: object = None) -> bool:
        nonlocal config_reads
        if endpoint == "user_config_get":
            config_reads += 1
            coordinator._apply_user_config({"variables": {"temp_oda_mean_interval": "HOURS_1"}})
        return True

    async def fake_async_request_message(endpoint: str, args: object = None, timeout: float = 10):
        assert endpoint == "config"
        return {"id": 1, "code": "OK", "response": "OK", "type": "response"}

    coordinator.async_request = fake_async_request  # type: ignore[method-assign]
    coordinator._async_request_message = fake_async_request_message  # type: ignore[method-assign]

    assert await coordinator.async_set_config("temp_oda_mean_interval", "HOURS_1") is True
    assert config_reads == 1


def test_config_variables_for_write_groups_auto_season_settings(hass) -> None:
    """Season-related config writes should include coupled values in auto modes."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator.state.config = {
        "season_request": "AUTO_TODA",
        "season_switch_temp": 18.0,
        "temp_oda_mean_interval": "HOURS_3",
    }

    assert coordinator._config_variables_for_write("temp_oda_mean_interval", "HOURS_1") == {
        "season_request": "AUTO_TODA",
        "season_switch_temp": 18.0,
        "temp_oda_mean_interval": "HOURS_1",
    }
    assert coordinator._config_variables_for_write("season_request", "HEATING") == {
        "season_request": "HEATING"
    }
