import logging
from datetime import timedelta

DOMAIN = "atrea_amotion"

LOGGER = logging.getLogger(__name__)
TIMEOUT = 120


DEFAULT_NAME = "Atrea aMotion"
STATE_MANUAL = "manual"
STATE_UNKNOWN = "unknown"
CONF_FAN_MODES = "fan_modes"
CONF_PRESETS = "presets"
DEFAULT_FAN_MODE_LIST = "10,20,30,40,50,60,70,80,90,100"
ALL_PRESET_LIST = [
    "Off",
    "Automatic",
    "Ventilation",
    "Circulation and Ventilation",
    "Circulation",
    "Night precooling",
    "Disbalance",
    "Overpressure",
    "Periodic ventilation",
    "Startup",
    "Rundown",
    "Defrosting",
    "External",
    "HP defrosting",
    "IN1",
    "IN2",
    "D1",
    "D2",
    "D3",
    "D4",
]

# HVAC_MODES = [HVAC_MODE_OFF, HVAC_MODE_AUTO, HVAC_MODE_FAN_ONLY, HVAC_MODE_COOL]
