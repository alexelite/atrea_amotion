"""Diagnostics support for Atrea aMotion."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    "host",
    "username",
    "password",
    "token",
    "board_number",
    "production_number",
    "mac",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["atrea"]

    diagnostics = {
        "entry": {
            "entry_id": config_entry.entry_id,
            "title": config_entry.title,
            "data": dict(config_entry.data),
            "options": dict(config_entry.options),
        },
        "capabilities": {
            "requests": sorted(coordinator.async_capabilities().requests),
            "unit_fields": sorted(coordinator.async_capabilities().unit_fields),
            "state_fields": sorted(coordinator.async_capabilities().state_fields),
            "enum_values": coordinator.async_capabilities().enum_values,
            "range_types": coordinator.async_capabilities().range_types,
            "diagram_components": coordinator.async_capabilities().diagram_components,
        },
        "state": {
            "discovery": coordinator.async_state().discovery,
            "requests": coordinator.async_state().requests,
            "unit": coordinator.async_state().unit,
            "active_states": coordinator.async_state().active_states,
            "derived": coordinator.async_state().derived,
            "control_panel": coordinator.async_state().control_panel,
            "disposable_plan": coordinator.async_state().disposable_plan,
            "ui_diagram_data": coordinator.async_state().ui_diagram_data,
            "moments": coordinator.async_state().moments,
        },
        "runtime": {
            "socket_state": coordinator.socket_state,
            "authorized": coordinator._authorized,
            "model": coordinator.model,
            "version": coordinator.version,
            "board_type": coordinator.board_type,
        },
    }

    return async_redact_data(diagnostics, TO_REDACT)
