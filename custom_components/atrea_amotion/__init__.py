"""Module provides the Atrea aMotion integration for Home Assistant."""

import asyncio
import json
import threading
from datetime import timedelta
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
from homeassistant.util import Throttle

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=15)

from .const import DOMAIN, LOGGER

# Socket
SOCK_CONNECTED = "Open"
SOCK_DISCONNECTED = "Close"
SOCK_ERROR = "Error"
# API Answer
SUCCESS_OK = "success"
SERVICE_ERROR = "ServiceErrorException"
USER_NOT_EXIST = "UserNotExist"
PASSWORD_NOK = "PasswordInvalid"
# WSS Messages
WS_AUTH_OK = "authorizedWebSocket"
WS_CMD_ACK = "result"
WS_OK = "OK"
N_RETRY = 5
WS_RETRY = 10
ACK_TIMEOUT = 5
HTTP_TIMEOUT = 5

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.FAN]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up connection to atrea."""
    try:
        atrea = Atrea_aMotion(
            hass,
            entry.data[CONF_NAME],
            entry.data[CONF_HOST],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data["model"],
            entry.data["version"],
        )
        await atrea.ping()
        await atrea.get_ui_info()
        await atrea.get_discovery()
    except Exception as e:
        raise ConfigEntryNotReady from e
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN][entry.entry_id] = {
        "atrea": atrea,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class Atrea_aMotion:
    """Atrea aMotion websocket connection."""

    def __init__(
        self,
        hass: HomeAssistant | None,
        name: str,
        host: str,
        username: str,
        password: str,
        model: str,
        version: str,
    ) -> None:
        """Initialize the Atrea aMotion Handle."""
        LOGGER.debug("Atrea aMotion websocket Initialize")
        self._hass = hass
        self._name = name
        self._host = host
        self._username = username
        self._password = password
        self._model = model
        self._version = version
        self._available = True
        self.wst = None
        self.ws = None
        self._refresh_time = 60
        self.sent_counter = 0
        self.socket_state = SOCK_DISCONNECTED
        # Last resort debug uncomment below:
        # websocket.enableTrace(True)
        self._ws = websocket.WebSocket()
        self._msg_id = 0
        self._message = None
        self._token = None
        self._authorized = False
        self._login_msg_id = None
        self._token_msg_id = None
        self._login_retry = 0
        self._discovery_msg_id = None
        self._ping_msg_id = None
        self._ui_info_msg_id = None

        self._ui_info = {}

    def ui_info(self):
        """Return the ui_info."""
        return self._ui_info

    @property
    def model(self):
        return self._model

    @property
    def version(self):
        return self._version

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self, message_id=None):
        """Update the state of the aMotion unit."""
        LOGGER.debug("def update")
        await self.get_ui_info()

    async def ping(self):
        """Send a ping message to the aMotion unit."""
        self._msg_id = self._msg_id + 1
        self._ping_msg_id = self._msg_id
        await self.publish_wss({"endpoint": "ping", "id": self._msg_id, "args": "null"})

    async def get_ui_info(self):
        """Retrieve information from the aMotion unit."""
        self._msg_id = self._msg_id + 1
        self._ui_info_msg_id = self._msg_id
        await self.publish_wss(
            {"endpoint": "ui_info", "id": self._msg_id, "args": "null"}
        )

    async def get_discovery(self):
        """Retrieve device info from the unit."""
        self._msg_id = self._msg_id + 1
        self._discovery_msg_id = self._msg_id
        await self.publish_wss(
            {"endpoint": "discovery", "args": "null", "id": self._discovery_msg_id}
        )

    def ui_info_update(self, data):
        """Store the unit information."""
        self._ui_info.update(
            {
                "temp_sup": data["unit"].get("temp_sup", None),
                "temp_eha": data["unit"].get("temp_eha", None),
                "temp_eta": data["unit"].get("temp_eta", None),
                "temp_ida": data["unit"].get("temp_ida", None),
                "temp_oda": data["unit"].get("temp_oda", None),
                "temp_oda_mean": data["unit"].get("temp_oda_mean", None),
                "fan_eta_factor": data["unit"].get("fan_eta_factor", None),
                "fan_sup_factor": data["unit"].get("fan_sup_factor", None),
                "mode_current": data["unit"].get("mode_current", None),
                "season_current": data["unit"].get("season_current", None),
                "bypass_control_req": data["requests"].get("bypass_control_req", None),
                "fan_power_req": data["requests"].get("fan_power_req", None),
                "fan_power_req_eta": data["requests"].get("fan_power_req_eta", None),
                "fan_power_req_sup": data["requests"].get("fan_power_req_sup", None),
                "setpoint": data["requests"].get("temp_request", None),
                "work_regime": data["requests"].get("work_regime", None),
            }
        )

    async def check_credentials(self):
        """Check if credentials for WSS are OK."""
        LOGGER.debug("aMotion websocket Checking credentials")
        if not self.api_key:
            LOGGER.debug("aMotion websocket api key needed")
            return bool(await self.login())

        LOGGER.debug("aMotion websocket api_key are OK")
        return True

    async def open_wss_thread(self):
        """Connect WebSocket to aMotion unit and create a thread to maintain connection alive."""
        #        if not await self.check_credentials():
        #            LOGGER.error("aMotion websocket Failed to obtain WSS Api Key")
        #            return False

        LOGGER.debug("aMotion websocket Addr=%s / Api Key=%s ", self._host, self._token)

        try:
            self.ws = websocket.WebSocketApp(
                f"ws://{self._host}/api/ws",
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

            self.wst = threading.Thread(target=self.ws.run_forever)
            self.wst.start()

            if self.wst.is_alive():
                LOGGER.debug("aMotion websocket Thread was init")
                return True
            else:
                LOGGER.error("aMotion websocket Thread connection init has FAILED")
                return False

        except websocket.WebSocketException as err:
            self.socket_state = SOCK_ERROR
            LOGGER.debug("aMotion websocket Error while opening socket: %s", err)
            return False

    async def authenticate_with_server(self):
        """Authenticate with aMotion Websocket using username and Api Key."""
        if self._login_retry > 5:
            LOGGER.error("aMotion websocket Too many login attempts. ")
            return
        if self._token is None:
            LOGGER.debug("aMotion websocket Sending credentials. ")
            self._login_retry = self._login_retry + 1
            self._msg_id = self._msg_id + 1
            self._login_msg_id = self._msg_id
            await self.publish_wss(
                {
                    "endpoint": "login",
                    "id": self._login_msg_id,
                    "args": {"username": self._username, "password": self._password},
                }
            )
        else:
            LOGGER.debug("Login with token. %s", self._token)
            self._msg_id = self._msg_id + 1
            self._token_msg_id = self._msg_id
            await self.publish_wss(
                {
                    "endpoint": "login",
                    "id": self._token_msg_id,
                    "args": {"token": self._token},
                }
            )

    async def connect_wss(self):
        """Connect to websocket."""
        if self.socket_state == SOCK_CONNECTED:
            LOGGER.debug("aMotion websocket Already connected... ")
            return True

        LOGGER.debug("aMotion websocket Not connected, connecting")

        if await self.open_wss_thread():
            LOGGER.debug("aMotion websocket Connecting")
        else:
            return False

        for i in range(WS_RETRY):
            LOGGER.debug("aMotion websocket awaiting connection established... %s", i)
            if self.socket_state == SOCK_CONNECTED:
                await self.authenticate_with_server()
                return True
            await asyncio.sleep(3)
        return False

    def on_error(self, ws, error):
        """Socket "On_Error" event."""
        details = ""
        if error:
            details = f"(details : {error})"
        LOGGER.debug("aMotion websocket Error: %s", details)
        self.socket_state = SOCK_ERROR

    def on_close(self, ws, close_status_code, close_msg):
        """Socket "On_Close" event."""
        LOGGER.debug("aMotion websocket Closed")

        if close_status_code or close_msg:
            LOGGER.debug(
                "aMotion websocket Close Status_code: %s", str(close_status_code)
            )
            LOGGER.debug("aMotion websocket Close Message: %s", str(close_msg))
        self.socket_state = SOCK_DISCONNECTED

    def on_pong(self, message):
        """Socket on_pong event."""
        LOGGER.debug("aMotion websocket Got a Pong")

    def on_open(self, ws):
        """Socket "On_Open" event."""
        LOGGER.debug("aMotion websocket Connection established OK")
        self.socket_state = SOCK_CONNECTED

    def on_message(self, ws, msg):
        """Socket "On_Message" event."""
        self.sent_counter = 0
        message = json.loads(msg)
        # LOGGER.debug("aMotion websocket Msg received %s", message)
        # LOGGER.debug("aMotion websocket self.sent_counter %s", self.sent_counter)

        if message.get("id") == self._login_msg_id:
            if message["code"] == "OK":
                self._token = message["response"]
                LOGGER.debug("aMotion websocket Token received. %s", self._token)
                asyncio.run(self.authenticate_with_server())
            else:
                LOGGER.error(
                    "Atrea aMotion websocket Api Key? not authorized based on response form server ???. "
                )
                self._authorized = False
        elif message.get("id") == self._token_msg_id:
            if message["code"] == "OK":
                self._login_retry = 0
                LOGGER.debug("Atrea aMotion websocket Token response received OK")
                self._authorized = True
            else:
                LOGGER.warning(
                    "Atrea aMotion websocket Api Key? not authorized based on response form server ???. "
                )
                self._authorized = False
        elif message.get("id") == self._discovery_msg_id:
            if message["code"] == "OK":
                LOGGER.debug("aMotion websocket Token response received OK")
                self._model = message["response"].get("type", "aMotion")
                self._version = message["response"].get("version", "0")
            else:
                LOGGER.error("aMotion websocket discovery NOT OK. ")
        elif message.get("id") == self._ui_info_msg_id:
            self.ui_info_update(message.get("response", {}))
        elif message.get("event") == "ui_info":
            self.ui_info_update(message.get("args", {}))
        elif message.get("event") == "disposable_plan":
            pass
        # else:
        #     LOGGER.error(
        #         "aMotion websocket Received an unknown message from server: %s", message
        #     )

        # TODO deal with incoming messages and updates
        if "event" in message:
            if message["event"] == "ui_info":
                # LOGGER.debug("aMotion websocket recieved ui_info update message. ")
                if "unit" in message:
                    self.parse_device_update(message)
            else:
                pass
        elif message["type"] == "response":
            if message["id"] == self._login_msg_id:
                if message["code"] != "UNAUTHORIZED":
                    self._token = message["response"]
                    LOGGER.debug(
                        "aMotion websocket Msg: Token received. %s", self._token
                    )
                    asyncio.run(self.authenticate_with_server())
                else:
                    LOGGER.error(
                        "Atrea aMotion websocket Msg: Api Key? not authorized based on response form server ???. "
                    )
            elif "response" in message:
                self.parse_device_update(message)
        else:
            LOGGER.warning(
                "Atrea aMotion websocket Received an unknown message from server: %s",
                message,
            )

    def parse_device_update(self, update):
        """Parse the device update message from websocket and update object with values."""
        self._message = update
        # LOGGER.debug("aMotion websocket: Recieved %s )", update)
        if "event" in update:
            if update["event"] == "ui_info":
                self._message["response"] = update["args"]
        return None

    async def publish_wss(self, dict_message):
        """Publish payload over WSS connexion."""
        json_message = json.dumps(dict_message)
        LOGGER.debug("aMotion websocket Publishing message : %s", json_message)

        if self.sent_counter >= 5:
            LOGGER.warning(
                "Atrea aMotion websocket Link is UP, but server has stopped answering request. "
            )
            self.sent_counter = 0
            self.ws.close()
            self.socket_state = SOCK_DISCONNECTED

        for attempt in range(N_RETRY):
            if self.socket_state == SOCK_CONNECTED:
                try:
                    self.ws.send(json_message)
                    self.sent_counter += 1
                    LOGGER.debug("aMotion websocket Msg published OK (%s)", attempt)
                    return True
                except websocket.WebSocketConnectionClosedException as err:
                    self.socket_state = SOCK_DISCONNECTED
                    LOGGER.debug(
                        "aMotion websocket Error while publishing message (details: %s)",
                        err,
                    )
            else:
                LOGGER.debug(
                    "aMotion websocket Can't publish message socket_state= %s, reconnecting... ",
                    self.socket_state,
                )
                await self.connect_wss()

        LOGGER.error(
            "Atrea aMotion websocket Failed to puslish message after %s retry. ",
            N_RETRY,
        )
        return False

    async def send_command(self, command):
        """Send command to websocket."""
        LOGGER.debug(
            "Atrea aMotion websocket send_command: %s to garage_door: %s",
            command,
            self.device_id,
        )

        await self.publish_wss(command)

    async def refresh_handler(self, d_id):
        """Make sure the websocket is connected every refresh_time interval."""
        LOGGER.debug("Atrea aMotion websocket Start refresh_handler")
        while True:
            try:
                if self.socket_state != SOCK_CONNECTED:
                    await self.connect_wss()

                await asyncio.sleep(self._refresh_time)
            except Exception as err:
                LOGGER.error(
                    "Atrea aMotion websocket Error during refresh_handler (details=%s)",
                    err,
                )
