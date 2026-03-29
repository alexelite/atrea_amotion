"""Atrea aMotion integration for Home Assistant."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from time import monotonic
from typing import Any

import websocket
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import Throttle

from .const import API_TIMEOUT, CONF_DEBUG_LOGGING, DOMAIN, LOGGER

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=15)
PERIODIC_REFRESH_INTERVAL = 15
CONTROL_BURST_REFRESH_INTERVAL = 1
CONTROL_BURST_REFRESH_CYCLES = 20

SOCK_CONNECTED = "Open"
SOCK_DISCONNECTED = "Close"
SOCK_ERROR = "Error"
N_RETRY = 5
WS_RETRY = 10

PLATFORMS = [
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


@dataclass(slots=True)
class AtreaCapabilities:
    """Capabilities derived from the unit control scheme."""

    requests: set[str] = field(default_factory=set)
    unit_fields: set[str] = field(default_factory=set)
    state_fields: set[str] = field(default_factory=set)
    enum_values: dict[str, list[str]] = field(default_factory=dict)
    range_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagram_components: dict[str, Any] = field(default_factory=dict)
    base_states: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def has_supply_fan_control(self) -> bool:
        return "fan_power_req_sup" in self.requests

    @property
    def has_extract_fan_control(self) -> bool:
        return "fan_power_req_eta" in self.requests

    @property
    def has_unified_fan_control(self) -> bool:
        return "fan_power_req" in self.requests

    @property
    def has_climate_control(self) -> bool:
        return {"work_regime", "temp_request"}.issubset(self.requests)

    @property
    def has_bypass_control(self) -> bool:
        return "bypass_control_req" in self.requests

    def range_for(self, variable: str) -> dict[str, Any]:
        """Return range metadata for a variable."""
        return self.range_types.get(variable, {})

    def enum_for(self, variable: str) -> list[str]:
        """Return enum values for a variable."""
        return self.enum_values.get(variable, [])


@dataclass(slots=True)
class AtreaState:
    """Current unit state."""

    discovery: dict[str, Any] = field(default_factory=dict)
    requests: dict[str, Any] = field(default_factory=dict)
    unit: dict[str, Any] = field(default_factory=dict)
    active_states: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, Any] = field(default_factory=dict)
    control_panel: dict[str, Any] = field(default_factory=dict)
    disposable_plan: dict[str, Any] = field(default_factory=dict)
    ui_diagram_data: dict[str, Any] = field(default_factory=dict)
    moments: dict[str, Any] = field(default_factory=dict)
    modbus: dict[str, Any] = field(default_factory=dict)
    update: dict[str, Any] = field(default_factory=dict)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    try:
        _apply_logger_options(entry)
        atrea = AtreaAMotionCoordinator(
            hass=hass,
            name=entry.data[CONF_NAME],
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            model=entry.data.get("model", "aMotion"),
            version=entry.data.get("version", "unknown"),
        )
        await atrea.async_initialize()
    except Exception as err:
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "atrea": atrea,
        "options_unsub": entry.add_update_listener(_async_entry_updated),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id)
    options_unsub = data.get("options_unsub")
    if options_unsub is not None:
        options_unsub()
    await data["atrea"].async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    _apply_logger_options(entry)
    await hass.config_entries.async_reload(entry.entry_id)


def _apply_logger_options(entry: ConfigEntry) -> None:
    """Apply runtime logger settings from entry options."""
    debug_enabled = entry.options.get(
        CONF_DEBUG_LOGGING,
        entry.data.get(CONF_DEBUG_LOGGING, False),
    )
    LOGGER.setLevel(logging.DEBUG if debug_enabled else logging.NOTSET)


class AtreaAMotionCoordinator:
    """Keep websocket transport, capabilities, and state in one place."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        host: str,
        username: str,
        password: str,
        model: str,
        version: str,
    ) -> None:
        self.hass = hass
        self.name = name
        self.host = host
        self.username = username
        self.password = password
        self.socket_state = SOCK_DISCONNECTED
        self.sent_counter = 0
        self._msg_id = 0
        self._token: str | None = None
        self._login_msg_id: int | None = None
        self._token_msg_id: int | None = None
        self._login_retry = 0
        self._authorized = False
        self._refresh_time = 60
        self._ready = asyncio.Event()
        self._discovery_ready = asyncio.Event()
        self._control_scheme_ready = asyncio.Event()
        self._ui_info_ready = asyncio.Event()
        self._diagram_ready = asyncio.Event()
        self._moments_ready = asyncio.Event()
        self._shutdown = False
        self._thread: threading.Thread | None = None
        self._refresh_task: asyncio.Task | None = None
        self._control_burst_task: asyncio.Task | None = None
        self.ws: websocket.WebSocketApp | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()
        self._pending_requests: dict[int, str] = {}
        self._response_waiters: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._last_message_at = monotonic()

        self.capabilities = AtreaCapabilities()
        self.state = AtreaState(discovery={"type": model, "version": version, "name": name})

    @property
    def model(self) -> str:
        return self.state.discovery.get("type") or self.state.discovery.get("name") or "aMotion"

    @property
    def version(self) -> str:
        return self.state.discovery.get("version", "unknown")

    @property
    def board_type(self) -> str | None:
        return self.state.discovery.get("board_type")

    @property
    def update_signal(self) -> str:
        return f"{DOMAIN}_{self.host}_update"

    async def async_initialize(self) -> None:
        """Open websocket, authenticate, and load initial metadata."""
        self._loop = asyncio.get_running_loop()
        if not await self.connect_wss():
            raise ConfigEntryNotReady("Unable to connect to websocket")

        await self.async_request("discovery")
        await self.async_request("ui_control_scheme")
        await self.async_request("ui_diagram_scheme")
        await self.async_request("ui_info")
        await self.async_request("ui_diagram_data")
        await self.async_request("control_admin/config/moments/get")
        await self.async_request("modbus")
        await self.async_request("update")
        await self.async_request("control_panel")
        await asyncio.wait_for(self._discovery_ready.wait(), timeout=10)
        await asyncio.wait_for(self._control_scheme_ready.wait(), timeout=10)
        await asyncio.wait_for(self._ui_info_ready.wait(), timeout=10)
        await asyncio.wait_for(self._diagram_ready.wait(), timeout=10)
        await asyncio.wait_for(self._moments_ready.wait(), timeout=10)
        self._ensure_refresh_task()

    async def async_shutdown(self) -> None:
        """Stop the websocket connection."""
        self._shutdown = True
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            self._refresh_task = None
        if self._control_burst_task is not None:
            self._control_burst_task.cancel()
            self._control_burst_task = None
        if self.ws is not None:
            await self.hass.async_add_executor_job(self.ws.close)

    def async_state(self) -> AtreaState:
        """Return the current state snapshot."""
        return self.state

    def async_capabilities(self) -> AtreaCapabilities:
        """Return the current capability snapshot."""
        return self.capabilities

    def requested_value(self, key: str) -> Any:
        """Return a requested value."""
        return self.state.requests.get(key)

    def unit_value(self, key: str) -> Any:
        """Return a measured unit value."""
        return self.state.unit.get(key)

    def value(self, key: str) -> Any:
        """Return a flattened value from the known state buckets."""
        if key in self.state.derived:
            return self.state.derived.get(key)
        if key in self.state.unit:
            return self.state.unit.get(key)
        if key in self.state.requests:
            return self.state.requests.get(key)
        return self.state.control_panel.get(key)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self) -> None:
        """Refresh the current unit state."""
        await self.async_request("ui_info")
        await self.async_request("ui_diagram_data")
        await self.async_request("control_admin/config/moments/get")

    async def async_request(self, endpoint: str, args: Any = None) -> bool:
        """Send a websocket request."""
        message_id, success = await self._async_send_request(endpoint, args)
        if not success:
            self._pending_requests.pop(message_id, None)
        return success

    async def _async_request_message(
        self, endpoint: str, args: Any = None, timeout: float = API_TIMEOUT
    ) -> dict[str, Any] | None:
        """Send a websocket request and await its direct response."""
        message_id, success = await self._async_send_request(endpoint, args, expect_response=True)
        if not success:
            self._pending_requests.pop(message_id, None)
            self._response_waiters.pop(message_id, None)
            return None

        waiter = self._response_waiters[message_id]
        try:
            return await asyncio.wait_for(waiter, timeout=timeout)
        except TimeoutError:
            LOGGER.warning("Timed out waiting for %s response", endpoint)
            self._pending_requests.pop(message_id, None)
            return None
        finally:
            self._response_waiters.pop(message_id, None)

    async def _async_send_request(
        self, endpoint: str, args: Any = None, expect_response: bool = False
    ) -> tuple[int, bool]:
        """Allocate an id, enqueue response tracking, and publish the request."""
        async with self._lock:
            self._msg_id += 1
            message_id = self._msg_id
            payload = {"endpoint": endpoint, "id": message_id, "args": args}
            self._pending_requests[message_id] = endpoint
            if expect_response:
                self._response_waiters[message_id] = asyncio.get_running_loop().create_future()
            success = await self.publish_wss(payload)
        return message_id, success

    async def async_control(self, variables: dict[str, Any]) -> bool:
        """Send control variables to the unit."""
        response = await self._async_request_message("control", {"variables": variables})
        if response is not None and response.get("code") == "UNAUTHORIZED":
            LOGGER.warning("Control rejected as unauthorized, reauthorizing websocket session")
            if not await self._async_reauthorize_session():
                return False
            response = await self._async_request_message("control", {"variables": variables})

        if response is None:
            return False
        if response.get("code") != "OK":
            LOGGER.warning("Control request failed with code %s", response.get("code"))
            return False

        self._apply_optimistic_control(variables)
        await self.async_request("control_panel")
        await self.async_request("ui_info")
        self._schedule_control_burst_refresh()
        return True

    async def async_reset_filter_interval(self) -> bool:
        """Confirm filter replacement on the unit."""
        success = await self.async_request("control_admin/config/moments/reset/filter")
        if success:
            await self.async_request("control_admin/config/moments/get")
            await self.async_request("ui_info")
        return success

    async def async_set_unit_name(self, name: str) -> bool:
        """Set the unit name."""
        cleaned_name = name.strip()
        if not cleaned_name:
            return False

        success = await self.async_request("unit/set", {"name": cleaned_name})
        if success:
            await self.async_request("discovery")
        return success

    async def async_set_modbus_enabled(self, enabled: bool) -> bool:
        """Enable or disable Modbus TCP."""
        success = await self.async_request("modbus/set", {"enable": enabled})
        if success:
            await self.async_request("modbus")
        return success

    async def async_set_autoupdate_enabled(self, enabled: bool) -> bool:
        """Enable or disable firmware auto update."""
        success = await self.async_request("update/set", {"autoupdate": enabled})
        if success:
            await self.async_request("update")
        return success

    async def async_reboot(self) -> bool:
        """Request a unit reboot."""
        return await self.async_request("reboot")

    def _ensure_refresh_task(self) -> None:
        """Start the periodic refresh task if needed."""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._periodic_refresh_loop())

    async def _periodic_refresh_loop(self) -> None:
        """Keep state fresh even when the unit does not emit push events."""
        try:
            while not self._shutdown:
                await asyncio.sleep(PERIODIC_REFRESH_INTERVAL)
                if self._shutdown:
                    break
                await self.async_update()
                await self.async_request("control_panel")
        except asyncio.CancelledError:
            return

    def _schedule_control_burst_refresh(self) -> None:
        """Refresh rapidly for a short period after a control change."""
        if self._control_burst_task is not None and not self._control_burst_task.done():
            self._control_burst_task.cancel()
        self._control_burst_task = asyncio.create_task(self._control_burst_refresh_loop())

    async def _control_burst_refresh_loop(self) -> None:
        """Poll frequently after control changes to capture delayed transitions."""
        try:
            for _ in range(CONTROL_BURST_REFRESH_CYCLES):
                if self._shutdown:
                    break
                await asyncio.sleep(CONTROL_BURST_REFRESH_INTERVAL)
                await self.async_request("ui_diagram_data")
                await self.async_request("ui_info")
                await self.async_request("control_panel")
        except asyncio.CancelledError:
            return

    async def connect_wss(self) -> bool:
        """Connect and authorize the websocket session."""
        if self.socket_state == SOCK_CONNECTED and self._authorized:
            return True

        if not await self.open_wss_thread():
            return False

        for attempt in range(WS_RETRY):
            if self.socket_state == SOCK_CONNECTED:
                await self.authenticate_with_server()
                try:
                    await asyncio.wait_for(self._ready.wait(), timeout=5)
                    return True
                except TimeoutError:
                    LOGGER.debug("Timed out waiting for websocket authorization")
            LOGGER.debug("Awaiting websocket authorization... %s", attempt)
            await asyncio.sleep(1)
        return False

    async def open_wss_thread(self) -> bool:
        """Open the websocket and run it in a background thread."""
        LOGGER.debug("Opening websocket to %s", self.host)
        try:
            self.ws = websocket.WebSocketApp(
                f"ws://{self.host}/api/ws",
                header={
                    "Connection": "keep-alive, Upgrade",
                    "handshakeTimeout": "10000",
                },
                on_message=self.on_message,
                on_close=self.on_close,
                on_open=self.on_open,
                on_error=self.on_error,
                on_pong=self.on_pong,
            )
            self._thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self._thread.start()
            return True
        except websocket.WebSocketException as err:
            self.socket_state = SOCK_ERROR
            LOGGER.debug("Error while opening websocket: %s", err)
            return False

    async def authenticate_with_server(self) -> None:
        """Authenticate the websocket session."""
        if self._login_retry > 5:
            LOGGER.error("Too many login attempts")
            return

        self._msg_id += 1
        if self._token is None:
            self._login_retry += 1
            self._login_msg_id = self._msg_id
            await self.publish_wss(
                {
                    "endpoint": "login",
                    "id": self._login_msg_id,
                    "args": {"username": self.username, "password": self.password},
                }
            )
            return

        self._token_msg_id = self._msg_id
        await self.publish_wss(
            {
                "endpoint": "login",
                "id": self._token_msg_id,
                "args": {"token": self._token},
            }
        )

    async def _async_reauthorize_session(self) -> bool:
        """Refresh websocket authorization after an unauthorized control reply."""
        self._authorized = False
        self._ready.clear()

        await self.authenticate_with_server()
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=5)
            return True
        except TimeoutError:
            LOGGER.debug("Token reauthorization timed out, requesting a fresh websocket token")

        self._authorized = False
        self._ready.clear()
        self._token = None
        await self.authenticate_with_server()
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=5)
            return True
        except TimeoutError:
            LOGGER.warning("Websocket reauthorization failed")
            return False

    def on_error(self, ws, error) -> None:
        """Socket error event."""
        details = f"(details: {error})" if error else ""
        LOGGER.debug("Websocket error %s", details)
        self.socket_state = SOCK_ERROR

    def on_close(self, ws, close_status_code, close_msg) -> None:
        """Socket close event."""
        LOGGER.debug("Websocket closed: %s %s", close_status_code, close_msg)
        self.socket_state = SOCK_DISCONNECTED
        self._authorized = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._ready.clear)

    def on_pong(self, ws, message) -> None:
        """Socket pong event."""
        LOGGER.debug("Websocket pong received")

    def on_open(self, ws) -> None:
        """Socket open event."""
        LOGGER.debug("Websocket connected")
        self.socket_state = SOCK_CONNECTED
        self.sent_counter = 0
        self._last_message_at = monotonic()
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self.authenticate_with_server(), self._loop)

    def on_message(self, ws, msg: str) -> None:
        """Socket message event."""
        self.sent_counter = 0
        self._last_message_at = monotonic()
        LOGGER.debug("Received websocket message: %s", msg)
        try:
            message = json.loads(msg)
        except json.JSONDecodeError:
            LOGGER.debug("Ignoring invalid JSON payload")
            return

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._handle_message_on_loop, message)

    def _handle_message_on_loop(self, message: dict[str, Any]) -> None:
        """Handle websocket messages on the HA event loop."""
        message_id = message.get("id")
        if message_id == self._login_msg_id and message.get("code") == "OK":
            self._token = message.get("response")
            self._resolve_response_waiter(message)
            asyncio.create_task(self.authenticate_with_server())
            return

        if message_id == self._token_msg_id:
            self._authorized = message.get("code") == "OK"
            if self._authorized:
                self._login_retry = 0
                self._ready.set()
            self._resolve_response_waiter(message)
            return

        self._resolve_response_waiter(message)
        self._process_message(message)

    def _resolve_response_waiter(self, message: dict[str, Any]) -> None:
        """Resolve any waiter blocked on a direct websocket response."""
        message_id = message.get("id")
        if not isinstance(message_id, int):
            return

        waiter = self._response_waiters.get(message_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(message)

    def _process_message(self, message: dict[str, Any]) -> None:
        """Parse websocket responses and events."""
        event = message.get("event")
        response = message.get("response")
        payload = message.get("args")

        if event == "ui_info":
            self._apply_ui_info(payload or {})
        elif event == "control_panel":
            self._apply_control_panel(payload or {})
            self._notify_state_changed()
        elif event == "unit_config":
            self._notify_state_changed()
            asyncio.create_task(self.async_request("discovery"))
        elif event == "control_invoked":
            self.state.control_panel.setdefault("invoked", payload or {})
            self._notify_state_changed()
        elif event == "disposable_plan":
            self.state.disposable_plan = payload or {}
            self._notify_state_changed()
        elif response is not None:
            endpoint = self._endpoint_from_response(message)
            if endpoint == "discovery":
                self._apply_discovery(response)
            elif endpoint == "ui_control_scheme":
                self._apply_control_scheme(response)
            elif endpoint == "ui_diagram_scheme":
                self._apply_diagram_scheme(response)
            elif endpoint == "ui_info":
                self._apply_ui_info(response)
            elif endpoint == "ui_diagram_data":
                self._apply_ui_diagram_data(response)
            elif endpoint == "control_admin/config/moments/get":
                self._apply_moments(response.get("get", response))
            elif endpoint == "modbus":
                self._apply_modbus(response)
            elif endpoint == "update":
                self._apply_update(response)
            elif endpoint == "control_panel":
                self._apply_control_panel(response.get("control_panel", response))
                self._notify_state_changed()

    def _endpoint_from_response(self, message: dict[str, Any]) -> str | None:
        """Best-effort endpoint detection for responses."""
        message_id = message.get("id")
        if isinstance(message_id, int):
            endpoint = self._pending_requests.pop(message_id, None)
            if endpoint is not None:
                return endpoint

        response = message.get("response")
        if not isinstance(response, dict):
            return None
        if "board_number" in response or "board_type" in response:
            return "discovery"
        if {"requests", "types", "unit"}.issubset(response):
            return "ui_control_scheme"
        if "diagramType" in response or "components" in response:
            return "ui_diagram_scheme"
        if {"requests", "unit", "states"}.issubset(response):
            return "ui_info"
        if {
            "bypass_estim",
            "damper_io_state",
            "fan_eta_operating_time",
            "fan_sup_operating_time",
        }.intersection(response):
            return "ui_diagram_data"
        if {
            "filters",
            "lastFilterReset",
            "m1_register",
            "m2_register",
            "uv_lamp_register",
            "uv_lamp_service_life",
            "get",
        }.intersection(response):
            return "control_admin/config/moments/get"
        if {"active", "enable", "clients", "port"}.intersection(response):
            return "modbus"
        if {"autoupdate", "check", "status"}.intersection(response):
            return "update"
        if "control_panel" in response:
            return "control_panel"
        return None

    def _apply_discovery(self, response: dict[str, Any]) -> None:
        """Store discovery metadata."""
        self.state.discovery.update(response)
        self._discovery_ready.set()
        self._notify_state_changed()

    def _apply_control_scheme(self, response: dict[str, Any]) -> None:
        """Store capabilities from ui_control_scheme."""
        self.capabilities.requests = set(response.get("requests", []))
        self.capabilities.unit_fields = set(response.get("unit", []))
        self.capabilities.state_fields = set(response.get("states", []))
        self.capabilities.enum_values = {
            key: value.get("values", [])
            for key, value in response.get("types", {}).items()
            if value.get("type") == "enum"
        }
        self.capabilities.range_types = {
            key: value
            for key, value in response.get("types", {}).items()
            if value.get("type") == "range"
        }
        self._control_scheme_ready.set()
        self._notify_state_changed()

    def _apply_diagram_scheme(self, response: dict[str, Any]) -> None:
        """Store supplemental diagram metadata."""
        self.capabilities.diagram_components = response.get("components", {})
        self.capabilities.base_states = {
            item["id"]: item
            for item in response.get("baseStates", [])
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        self._notify_state_changed()

    def _apply_ui_info(self, response: dict[str, Any]) -> None:
        """Store current unit data."""
        self.state.requests = response.get("requests", {})
        self.state.unit = response.get("unit", {})
        self.state.active_states = response.get("states", {}).get("active", {})
        self._refresh_derived_state()
        self._ui_info_ready.set()
        self._notify_state_changed()

    def _apply_ui_diagram_data(self, response: dict[str, Any]) -> None:
        """Store live diagram values."""
        diagram_data = response.get("ui_diagram_data", response)
        self.state.ui_diagram_data = (
            diagram_data if isinstance(diagram_data, dict) else {}
        )
        self._refresh_derived_state()
        self._diagram_ready.set()
        self._notify_state_changed()

    def _apply_moments(self, response: dict[str, Any]) -> None:
        """Store maintenance and filter counters."""
        self.state.moments = response
        self._refresh_derived_state()
        self._moments_ready.set()
        self._notify_state_changed()

    def _apply_control_panel(self, response: dict[str, Any]) -> None:
        """Store transient control panel values."""
        self.state.control_panel = response
        self._refresh_derived_state()

    def _apply_optimistic_control(self, variables: dict[str, Any]) -> None:
        """Apply a local optimistic update until the unit echoes fresh state."""
        self.state.requests.update(variables)
        stored = self.state.control_panel.setdefault("stored", {})
        current = self.state.control_panel.setdefault("current", {})
        stored.update(variables)
        current.update(variables)
        self._refresh_derived_state()
        self._notify_state_changed()

    def _apply_modbus(self, response: dict[str, Any]) -> None:
        """Store Modbus TCP state."""
        self.state.modbus = response
        self._refresh_derived_state()
        self._notify_state_changed()

    def _apply_update(self, response: dict[str, Any]) -> None:
        """Store firmware update settings."""
        self.state.update = response
        self._refresh_derived_state()
        self._notify_state_changed()

    @staticmethod
    def _as_int(value: Any) -> int | None:
        """Convert numeric-like values to int."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return None
        return None

    def _infer_motor_role_mapping(
        self,
        motor_1_seconds: Any,
        motor_2_seconds: Any,
        supply_hours: Any,
        extract_hours: Any,
    ) -> str:
        """Infer whether raw motors can be mapped to supply/extract fans."""
        motor_1_hours = (
            int(motor_1_seconds // 3600)
            if isinstance(motor_1_seconds, (int, float))
            else None
        )
        motor_2_hours = (
            int(motor_2_seconds // 3600)
            if isinstance(motor_2_seconds, (int, float))
            else None
        )
        supply_value = self._as_int(supply_hours)
        extract_value = self._as_int(extract_hours)

        if None in {motor_1_hours, motor_2_hours, supply_value, extract_value}:
            return "unknown"

        m1_is_supply = motor_1_hours == supply_value
        m1_is_extract = motor_1_hours == extract_value
        m2_is_supply = motor_2_hours == supply_value
        m2_is_extract = motor_2_hours == extract_value

        if m1_is_supply and m2_is_extract and not (m1_is_extract or m2_is_supply):
            return "M1=supply, M2=extract"
        if m1_is_extract and m2_is_supply and not (m1_is_supply or m2_is_extract):
            return "M1=extract, M2=supply"
        if (
            motor_1_hours == motor_2_hours
            and supply_value == extract_value
            and motor_1_hours == supply_value
        ):
            return "ambiguous"
        return "ambiguous"

    def _refresh_derived_state(self) -> None:
        """Flatten cross-endpoint values that entities can consume directly."""
        active_states = self.state.active_states
        diagram = self.state.ui_diagram_data
        moments = self.state.moments
        filters = moments.get("filters") if isinstance(moments, dict) else None
        last_filter_reset = moments.get("lastFilterReset") if isinstance(moments, dict) else None
        stored = self.state.control_panel.get("stored", {})
        modbus = self.state.modbus
        update = self.state.update

        self.state.derived = {
            "bypass_estim": diagram.get("bypass_estim"),
            "damper_io_state": diagram.get("damper_io_state"),
            "fan_eta_operating_time": diagram.get("fan_eta_operating_time"),
            "fan_sup_operating_time": diagram.get("fan_sup_operating_time"),
            "filters": filters,
            "filter_due_date": filters,
            "lastFilterReset": last_filter_reset,
            "last_filter_reset": last_filter_reset,
            "m1_register": moments.get("m1_register"),
            "m2_register": moments.get("m2_register"),
            "motor_role_mapping": self._infer_motor_role_mapping(
                moments.get("m1_register"),
                moments.get("m2_register"),
                diagram.get("fan_sup_operating_time"),
                diagram.get("fan_eta_operating_time"),
            ),
            "uv_lamp_register": moments.get("uv_lamp_register"),
            "uv_lamp_service_life": moments.get("uv_lamp_service_life"),
            "active_state_count": len(active_states),
            "active_states": active_states,
            "active_state_names": [
                state.get("name")
                for state in active_states.values()
                if isinstance(state, dict) and state.get("name")
            ],
            "warning": any(
                (
                    self.capabilities.base_states.get(int(state_id), {}).get("purpose") in {"warning", "notify"}
                    or self.capabilities.base_states.get(int(state_id), {}).get("severity") in {3, 4}
                )
                for state_id, state in active_states.items()
                if isinstance(state, dict) and state.get("active") and str(state_id).isdigit()
            ),
            "fault": any(
                (
                    str(self.capabilities.base_states.get(int(state_id), {}).get("purpose", "")).startswith("alarm")
                    or (self.capabilities.base_states.get(int(state_id), {}).get("severity") or 0) >= 5
                )
                for state_id, state in active_states.items()
                if isinstance(state, dict) and state.get("active") and str(state_id).isdigit()
            ),
            "filter_interval_active": any(
                isinstance(state, dict) and state.get("name") == "FILTER_INTERVAL"
                for state in active_states.values()
            ),
            "stored_bypass_control_req": stored.get("bypass_control_req"),
            "stored_fan_power_req": stored.get("fan_power_req"),
            "stored_fan_power_req_eta": stored.get("fan_power_req_eta"),
            "stored_fan_power_req_sup": stored.get("fan_power_req_sup"),
            "stored_temp_request": stored.get("temp_request"),
            "stored_work_regime": stored.get("work_regime"),
            "control_panel_visible": self.state.control_panel.get("visible"),
            "control_panel_remaining": self.state.control_panel.get("remaining"),
            "modbus_active": modbus.get("active"),
            "modbus_enabled": modbus.get("enable"),
            "modbus_port": modbus.get("port"),
            "modbus_clients": modbus.get("clients"),
            "autoupdate_enabled": update.get("autoupdate"),
            "update_check_enabled": update.get("check"),
            "update_status": update.get("status"),
        }

    def _notify_state_changed(self) -> None:
        """Broadcast updated state."""
        self.hass.add_job(async_dispatcher_send, self.hass, self.update_signal)

    async def publish_wss(self, payload: dict[str, Any]) -> bool:
        """Publish JSON over websocket."""
        json_message = json.dumps(payload)
        LOGGER.debug("Publishing websocket message: %s", json_message)

        if (
            self.sent_counter >= 5
            and self.ws is not None
            and monotonic() - self._last_message_at > 30
        ):
            LOGGER.warning("Websocket stopped answering, reconnecting")
            self.sent_counter = 0
            self.ws.close()
            self.socket_state = SOCK_DISCONNECTED

        for attempt in range(N_RETRY):
            if self.socket_state == SOCK_CONNECTED and self.ws is not None:
                try:
                    await self.hass.async_add_executor_job(self.ws.send, json_message)
                    self.sent_counter += 1
                    return True
                except websocket.WebSocketConnectionClosedException as err:
                    self.socket_state = SOCK_DISCONNECTED
                    LOGGER.debug("Websocket send error: %s", err)
            else:
                await self.connect_wss()

            LOGGER.debug("Retrying websocket publish, attempt %s", attempt)

        LOGGER.error("Failed to publish websocket message after %s retries", N_RETRY)
        return False
