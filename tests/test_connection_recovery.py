"""Exercise transport reuse and real login/response handling together."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import is_callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

import custom_components.atrea_amotion as integration
from custom_components.atrea_amotion import AtreaAMotionCoordinator
from custom_components.atrea_amotion.const import DOMAIN
from custom_components.atrea_amotion.sensor import ATREA_SENSORS, AtreaAMotionSensor


def coordinator_for(hass):
    coordinator = AtreaAMotionCoordinator(hass, "Unit", "192.0.2.10", "user", "pass", "aMotion", "1", expected_serial="SN-TEST")
    coordinator._loop = asyncio.get_running_loop()
    return coordinator


def responding_socket(coordinator):
    sent = []
    socket = Mock()

    def send(raw):
        message = json.loads(raw)
        sent.append(message)
        endpoint = message["endpoint"]
        response = {"id": message["id"], "code": "OK"}
        if endpoint == "login":
            args = message["args"]
            if args.get("token") == "expired":
                response["code"] = "UNAUTHORIZED"
            elif "username" in args:
                response["response"] = "fresh"
        elif endpoint == "discovery":
            response["response"] = {"production_number": "SN-TEST"}
        elif endpoint == "control_admin/config/moments/get":
            response["response"] = {"get": {}}
        else:
            response["response"] = {}
        coordinator.on_message(socket, json.dumps(response))

    socket.send.side_effect = send
    return socket, sent


async def test_serial_verification_reuses_authenticated_transport(hass):
    coordinator = coordinator_for(hass)
    coordinator.socket_state = "Open"
    coordinator._authorized = True
    coordinator._ready.set()
    coordinator.ws, sent = responding_socket(coordinator)
    coordinator.open_wss_thread = AsyncMock()
    assert await asyncio.wait_for(coordinator.connect_wss(), 2)
    coordinator.open_wss_thread.assert_not_called()
    assert [m["endpoint"] for m in sent] == ["discovery"]
    coordinator.ws.close.assert_not_called()
    await coordinator.async_shutdown()


async def test_expired_token_recovers_and_refreshes_without_replacing_socket(hass):
    coordinator = coordinator_for(hass)
    coordinator.socket_state = "Open"
    coordinator._token = "expired"
    coordinator.ws, sent = responding_socket(coordinator)
    coordinator.open_wss_thread = AsyncMock()
    assert await asyncio.wait_for(coordinator.connect_wss(), 2)
    assert [m["args"] for m in sent if m["endpoint"] == "login"] == [
        {"token": "expired"}, {"username": "user", "password": "pass"}, {"token": "fresh"}
    ]
    assert coordinator._authorized and coordinator._serial_verified
    assert not coordinator.available
    for endpoint in ["ui_info", "ui_diagram_data", "control_admin/config/moments/get"]:
        assert await coordinator.async_request(endpoint)
    await hass.async_block_till_done()
    assert coordinator.available
    coordinator.open_wss_thread.assert_not_called()
    coordinator.ws.close.assert_not_called()
    await coordinator.async_shutdown()


async def test_concurrent_reconnection_opens_one_transport(hass):
    coordinator = coordinator_for(hass)
    socket, sent = responding_socket(coordinator)

    async def open_transport():
        coordinator.ws = socket
        coordinator.on_open(socket)
        await asyncio.sleep(0)
        return True

    coordinator.open_wss_thread = AsyncMock(side_effect=open_transport)
    assert all(await asyncio.wait_for(asyncio.gather(*(coordinator.connect_wss() for _ in range(4))), 3))
    assert coordinator.open_wss_thread.await_count == 1
    assert len([m for m in sent if m["endpoint"] == "login"]) == 2
    assert len([m for m in sent if m["endpoint"] == "discovery"]) == 1
    await coordinator.async_shutdown()


@pytest.mark.parametrize("thread_stops", [False, True])
async def test_replacement_waits_for_previous_receive_thread(hass, monkeypatch, thread_stops):
    coordinator = coordinator_for(hass)
    old_socket = Mock()
    coordinator.ws = old_socket
    alive = True
    events = []

    def close():
        events.append("close")

    def join(timeout):
        nonlocal alive
        events.append("join")
        alive = not thread_stops

    old_socket.close.side_effect = close
    coordinator._thread = Mock(is_alive=lambda: alive, join=join)
    factory = Mock(return_value=Mock())
    new_thread = Mock()
    new_thread.start.side_effect = lambda: events.append("start")
    monkeypatch.setattr(integration.websocket, "WebSocketApp", factory)
    monkeypatch.setattr(integration, "threading", SimpleNamespace(Thread=Mock(return_value=new_thread)))
    assert await coordinator.open_wss_thread() is thread_stops
    assert events == (["close", "join", "start"] if thread_stops else ["close", "join"])
    assert factory.call_count == int(thread_stops)
    # Avoid a second join against the simulated stuck thread during cleanup.
    coordinator._thread = None
    await coordinator.async_shutdown()


async def test_late_transport_callbacks_cannot_reset_replacement(hass):
    coordinator = coordinator_for(hass)
    old_socket, new_socket = Mock(), Mock()
    coordinator.ws = old_socket
    coordinator.on_close(old_socket, 1000, "closed")
    coordinator.on_message(old_socket, json.dumps({"event": "ui_info", "args": {"unit": {"temp_oda": -99}}}))
    coordinator.ws = new_socket
    coordinator.socket_state = "Open"
    coordinator._authorized = True
    coordinator._serial_verified = True
    coordinator._ready.set()
    coordinator._discovery_ready.set()
    await asyncio.sleep(0)
    assert coordinator._ready.is_set()
    assert coordinator._discovery_ready.is_set()
    assert "temp_oda" not in coordinator.state.unit
    coordinator.on_open(old_socket)
    old_socket.close.assert_called_once()
    assert coordinator._authorized
    await coordinator.async_shutdown()


async def test_rejected_token_clears_stale_ready_flag(hass):
    coordinator = coordinator_for(hass)
    coordinator._ready.set()
    coordinator._token = "expired"
    coordinator._token_msg_id = 7
    coordinator.authenticate_with_server = AsyncMock()
    coordinator._handle_message_on_loop({"id": 7, "code": "UNAUTHORIZED"})
    assert not coordinator._ready.is_set()
    assert coordinator._token is None
    await asyncio.sleep(0)
    coordinator.authenticate_with_server.assert_awaited_once()
    await coordinator.async_shutdown()


async def test_handshake_send_failure_does_not_recurse_into_connect(hass):
    coordinator = coordinator_for(hass)
    coordinator.socket_state = "Open"
    coordinator.ws = Mock(send=Mock(side_effect=integration.websocket.WebSocketConnectionClosedException()))
    coordinator.connect_wss = AsyncMock()
    await coordinator.authenticate_with_server()
    coordinator.connect_wss.assert_not_called()
    assert not coordinator._auth_pending
    assert not coordinator._authorized
    await coordinator.async_shutdown()


async def test_entity_dispatch_writes_state_on_loop(hass, MockConfigEntry):
    coordinator = coordinator_for(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"production_number": "SN-TEST"})
    sensor = AtreaAMotionSensor(coordinator, entry, ATREA_SENSORS[0], "Unit")
    sensor.hass = hass
    sensor.async_write_ha_state = Mock()
    assert is_callback(sensor._handle_coordinator_update)
    await sensor.async_added_to_hass()
    async_dispatcher_send(hass, coordinator.update_signal)
    sensor.async_write_ha_state.assert_called_once()
    await sensor.async_will_remove_from_hass()
    await coordinator.async_shutdown()


async def test_repeated_disconnects_recover_identity_and_fresh_data(hass):
    coordinator = coordinator_for(hass)
    sockets = []

    async def open_transport():
        socket, _ = responding_socket(coordinator)
        sockets.append(socket)
        coordinator.ws = socket
        coordinator.on_open(socket)
        await asyncio.sleep(0)
        return True

    coordinator.open_wss_thread = AsyncMock(side_effect=open_transport)
    for cycle in range(3):
        if cycle:
            coordinator.on_close(coordinator.ws, 1006, "lost")
            await asyncio.sleep(0)
            assert not coordinator.available
            coordinator._token = "expired"
        assert await asyncio.wait_for(coordinator.connect_wss(), 2)
        assert coordinator._serial_verified
        assert not coordinator.available
        for endpoint in ["ui_info", "ui_diagram_data", "control_admin/config/moments/get"]:
            assert await coordinator.async_request(endpoint)
        await hass.async_block_till_done()
        assert coordinator.available
    assert len(sockets) == 3
    await coordinator.async_shutdown()


async def test_refresh_survives_transient_exception(hass, monkeypatch):
    coordinator = coordinator_for(hass)
    monkeypatch.setattr(integration, "PERIODIC_REFRESH_INTERVAL", 0)
    calls = 0

    async def update():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("temporary failure")
        coordinator._shutdown = True

    coordinator.connect_wss = AsyncMock(return_value=True)
    coordinator.async_update = update
    coordinator.async_request = AsyncMock(return_value=False)
    await asyncio.wait_for(coordinator._periodic_refresh_loop(), 2)
    assert calls == 2
    await coordinator.async_shutdown()


async def test_concurrent_authentication_does_not_overwrite_login_id(hass):
    coordinator = coordinator_for(hass)
    coordinator.socket_state = "Open"
    coordinator.publish_wss = AsyncMock(return_value=True)
    await asyncio.gather(*(coordinator.authenticate_with_server() for _ in range(4)))
    assert coordinator.publish_wss.await_count == 1
    assert coordinator._login_msg_id == 1
    await coordinator.async_shutdown()


async def test_offline_recovery_backoff_applies_to_all_callers(hass, monkeypatch):
    coordinator = coordinator_for(hass)
    clock = Mock(return_value=0.0)
    monkeypatch.setattr(integration, "monotonic", clock)
    coordinator._async_connect_once = AsyncMock(return_value=False)
    now = 0.0
    for attempt, pause in enumerate([60, 120, 240, 300, 300], start=1):
        clock.return_value = now
        assert not await coordinator.connect_wss()
        assert coordinator._next_connection_attempt_at == now + pause
        for _ in range(3):
            assert not await coordinator.async_request("ui_info")
        assert coordinator._async_connect_once.await_count == attempt
        now += pause
    clock.return_value = now
    coordinator._async_connect_once.return_value = True
    assert await coordinator.connect_wss()
    assert coordinator._connection_failures == 0
    assert coordinator._next_connection_attempt_at == 0
    await coordinator.async_shutdown()


async def test_runtime_discovery_is_throttled_and_persists_same_serial_host(hass, MockConfigEntry, monkeypatch):
    coordinator = coordinator_for(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"host": coordinator.host, "production_number": "SN-TEST", "device_identity": "production:SN-TEST"})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry
    listener = AsyncMock()
    entry.add_update_listener(listener)
    clock = Mock(return_value=0.0)
    monkeypatch.setattr(integration, "monotonic", clock)
    discover = AsyncMock(return_value=None)
    monkeypatch.setattr(integration, "async_rediscover_config_entry", discover)
    coordinator._connection_failures = 1
    assert not await coordinator._async_rediscover_host()
    discover.assert_not_called()
    coordinator._connection_failures = 2
    assert not await coordinator._async_rediscover_host()
    assert discover.await_count == 1
    clock.return_value = 299
    discover.return_value = {"production_number": "SN-TEST", "ip": "192.0.2.20"}
    assert not await coordinator._async_rediscover_host()
    assert discover.await_count == 1
    clock.return_value = 300
    assert await coordinator._async_rediscover_host()
    await hass.async_block_till_done()
    assert discover.await_count == 2
    assert entry.data["host"] == "192.0.2.20"
    assert entry.data["device_identity"] == "production:SN-TEST"
    listener.assert_awaited_once_with(hass, entry)
    await coordinator.async_shutdown()


@pytest.mark.parametrize("result", [
    {"production_number": "SN-OTHER", "ip": "192.0.2.20"},
    {"ip": "192.0.2.20"},
    {"production_number": "SN-TEST", "ip": "192.0.2.10"},
])
async def test_runtime_discovery_rejects_wrong_missing_serial_and_unchanged_host(hass, MockConfigEntry, monkeypatch, result):
    coordinator = coordinator_for(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"host": coordinator.host, "production_number": "SN-TEST"})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry
    coordinator._connection_failures = 2
    monkeypatch.setattr(integration, "async_rediscover_config_entry", AsyncMock(return_value=result))
    snapshot = dict(entry.data)
    assert not await coordinator._async_rediscover_host()
    assert entry.data == snapshot
    await coordinator.async_shutdown()


async def test_same_address_recovers_after_thirty_minutes_without_reload(hass, monkeypatch):
    coordinator = coordinator_for(hass)
    clock = Mock(return_value=0.0)
    monkeypatch.setattr(integration, "monotonic", clock)
    original_connect = coordinator._async_connect_once
    coordinator._async_connect_once = AsyncMock(return_value=False)
    assert not await coordinator.connect_wss()
    clock.return_value = 60
    assert not await coordinator.connect_wss()
    clock.return_value = 1800
    coordinator._async_connect_once = original_connect
    coordinator.socket_state = "Open"
    coordinator._token = "expired"
    coordinator.ws, _ = responding_socket(coordinator)
    assert await asyncio.wait_for(coordinator.connect_wss(), 2)
    for endpoint in ["ui_info", "ui_diagram_data", "control_admin/config/moments/get"]:
        assert await coordinator.async_request(endpoint)
    await hass.async_block_till_done()
    assert coordinator.available
    assert coordinator.host == "192.0.2.10"
    assert coordinator._connection_failures == 0
    await coordinator.async_shutdown()
