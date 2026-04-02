"""Config flow for Atrea aMotion integration."""

from __future__ import annotations

from functools import partial
from typing import Any

import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResult

from .const import API_TIMEOUT, CONF_DEBUG_LOGGING, DEFAULT_NAME, DOMAIN, LOGGER
from .discovery import async_discover_enriched_devices

CONF_DEVICE_ID = "device_id"
MANUAL_DEVICE_ID = "__manual__"


async def _async_validate_connection(hass, user_input: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate credentials against the target unit and return discovered metadata."""
    try:
        login_data = {
            "username": user_input[CONF_USERNAME],
            "password": user_input[CONF_PASSWORD],
        }
        response = await hass.async_add_executor_job(
            partial(
                requests.post,
                f"http://{user_input[CONF_HOST]}/api/login",
                json=login_data,
                timeout=API_TIMEOUT,
            )
        )
        login_response = response.json()

        if login_response.get("code") != "OK" or "result" not in login_response:
            if login_response.get("code") == "INVALID_USER":
                return None, "invalid_user"
            return None, "invalid_auth"

        discovery_url = f"http://{user_input[CONF_HOST]}/api/discovery"
        discovery_response = await hass.async_add_executor_job(
            partial(requests.get, discovery_url, timeout=API_TIMEOUT)
        )
        discovery_data = discovery_response.json()
        result_data = discovery_data.get("result", {})

        validated = dict(user_input)
        validated["model"] = result_data.get("type")
        validated["version"] = result_data.get("version")
        validated["production_number"] = result_data.get("production_number")
        validated["board_number"] = result_data.get("board_number")
        validated["mac"] = result_data.get("board_number")
        validated["unit_name"] = result_data.get("name")
        validated["network_mac"] = user_input.get("network_mac")
        validated[CONF_NAME] = (
            user_input.get(CONF_NAME)
            or result_data.get("name")
            or DEFAULT_NAME
        )
        validated[CONF_DEBUG_LOGGING] = user_input.get(CONF_DEBUG_LOGGING, False)
        return validated, None
    except requests.RequestException:
        return None, "cannot_connect"
    except Exception:  # pylint: disable=broad-except
        LOGGER.exception("Unexpected exception")
        return None, "unknown"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atrea aMotion."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._discovered_devices: dict[str, dict[str, Any]] = {}

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return AtreaOptionsFlowHandler(config_entry)

    async def _async_get_discovered_devices(self) -> dict[str, dict[str, Any]]:
        """Load discovered devices once per flow."""
        if not self._discovered_devices:
            devices = await async_discover_enriched_devices(self.hass)
            self._discovered_devices = {
                self._device_key(device): device for device in devices if self._device_key(device)
            }
        return self._discovered_devices

    @staticmethod
    def _device_key(device: dict[str, Any]) -> str | None:
        """Build a stable key for one discovered device."""
        return (
            device.get("board_number")
            or device.get("mac")
            or device.get("ip")
            or device.get("source_ip")
        )

    @staticmethod
    def _device_label(device: dict[str, Any]) -> str:
        """Render one discovered device for the UI."""
        parts = [
            device.get("unit_name") or device.get("model") or "Atrea unit",
            device.get("ip") or device.get("source_ip") or "unknown ip",
        ]
        if device.get("mac"):
            parts.append(f"MAC {device['mac']}")
        if device.get("production_number"):
            parts.append(f"SN {device['production_number']}")
        return " | ".join(parts)

    def _async_user_schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        """Build the user step schema."""
        user_input = user_input or {}
        if self._discovered_devices:
            options = {
                device_id: self._device_label(device)
                for device_id, device in self._discovered_devices.items()
            }
            default_device_id = user_input.get(CONF_DEVICE_ID) or next(iter(options))
            default_name = user_input.get(CONF_NAME) or (
                self._discovered_devices[default_device_id].get("unit_name") or DEFAULT_NAME
            )
            return vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID, default=default_device_id): vol.In(options),
                    vol.Optional(CONF_NAME, default=default_name): str,
                    vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")): str,
                }
            )

        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
                vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")): str,
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        await self._async_get_discovered_devices()
        errors: dict[str, str] = {}
        if user_input is not None:
            resolved_input = dict(user_input)
            if self._discovered_devices:
                selected_device = self._discovered_devices.get(user_input.get(CONF_DEVICE_ID, ""))
                if selected_device is None:
                    errors["base"] = "device_required"
                else:
                    resolved_input[CONF_HOST] = (
                        selected_device.get("ip") or selected_device.get("source_ip")
                    )
                    resolved_input["network_mac"] = selected_device.get("mac")
                    resolved_input["unit_name"] = selected_device.get("unit_name")
                    resolved_input["production_number"] = selected_device.get("production_number")
                    resolved_input["board_number"] = selected_device.get("board_number")

            validated_input, error = (None, None)
            if not errors:
                validated_input, error = await _async_validate_connection(self.hass, resolved_input)
            if validated_input is not None:
                user_input = validated_input
                user_input[CONF_DEBUG_LOGGING] = False
                unique_id = (
                    user_input.get("board_number")
                    or user_input.get("production_number")
                    or user_input.get("network_mac")
                    or user_input[CONF_HOST]
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get("unit_name") or user_input[CONF_HOST],
                    data=user_input,
                )
            else:
                errors["base"] = error or "unknown"

        description_placeholders: dict[str, str] | None = None
        if not self._discovered_devices:
            description_placeholders = {
                "discovery_hint": (
                    "No devices were discovered on the local network. "
                    "Enter the unit IP or hostname manually to continue."
                )
            }

        return self.async_show_form(
            step_id="user",
            data_schema=self._async_user_schema(user_input),
            errors=errors,
            description_placeholders=description_placeholders,
        )


class AtreaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Atrea aMotion options."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._discovered_devices: dict[str, dict[str, Any]] = {}

    async def _async_get_discovered_devices(self) -> dict[str, dict[str, Any]]:
        """Run discovery for the options flow."""
        if not self._discovered_devices:
            devices = await async_discover_enriched_devices(self.hass)
            self._discovered_devices = {
                ConfigFlow._device_key(device): device
                for device in devices
                if ConfigFlow._device_key(device)
            }
        return self._discovered_devices

    def _async_options_schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        """Build the options flow schema."""
        user_input = user_input or {}
        current_value = user_input.get(
            CONF_DEBUG_LOGGING,
            self.config_entry.options.get(
                CONF_DEBUG_LOGGING,
                self.config_entry.data.get(CONF_DEBUG_LOGGING, False),
            ),
        )
        fields: dict[Any, Any] = {}
        if self._discovered_devices:
            options = {MANUAL_DEVICE_ID: "Manual host"}
            options.update({
                device_id: ConfigFlow._device_label(device)
                for device_id, device in self._discovered_devices.items()
            })
            current_host = user_input.get(CONF_HOST, self.config_entry.data.get(CONF_HOST))
            default_device = next(
                (
                    device_id
                    for device_id, device in self._discovered_devices.items()
                    if (device.get("ip") or device.get("source_ip")) == current_host
                ),
                MANUAL_DEVICE_ID,
            )
            fields[vol.Optional(CONF_DEVICE_ID, default=user_input.get(CONF_DEVICE_ID, default_device))] = vol.In(options)

        fields[vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, self.config_entry.data.get(CONF_HOST, "")))] = str
        fields[vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, self.config_entry.data.get(CONF_USERNAME, "")))] = str
        fields[vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD, "")))] = str
        fields[vol.Required(CONF_DEBUG_LOGGING, default=current_value)] = bool
        return vol.Schema(fields)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        await self._async_get_discovered_devices()
        if user_input is not None:
            resolved_input = dict(user_input)
            selected_device = None
            selected_device_id = user_input.get(CONF_DEVICE_ID, "")
            if selected_device_id and selected_device_id != MANUAL_DEVICE_ID:
                selected_device = self._discovered_devices.get(selected_device_id)
            if selected_device is not None:
                resolved_input[CONF_HOST] = selected_device.get("ip") or selected_device.get("source_ip")
                resolved_input["network_mac"] = selected_device.get("mac")
                resolved_input["unit_name"] = selected_device.get("unit_name")
                resolved_input["production_number"] = selected_device.get("production_number")
                resolved_input["board_number"] = selected_device.get("board_number")

            validated_input, error = await _async_validate_connection(self.hass, resolved_input)
            if validated_input is None:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._async_options_schema(user_input),
                    errors={"base": error or "unknown"},
                )

            updated_data = dict(self.config_entry.data)
            updated_data.update(
                {
                    CONF_HOST: validated_input[CONF_HOST],
                    CONF_USERNAME: validated_input[CONF_USERNAME],
                    CONF_PASSWORD: validated_input[CONF_PASSWORD],
                    "model": validated_input.get("model"),
                    "version": validated_input.get("version"),
                    "production_number": validated_input.get("production_number"),
                    "mac": validated_input.get("mac"),
                    "board_number": validated_input.get("board_number"),
                    "unit_name": validated_input.get("unit_name"),
                    "network_mac": validated_input.get("network_mac"),
                }
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
                title=validated_input.get("unit_name") or validated_input[CONF_HOST],
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_HOST: validated_input[CONF_HOST],
                    CONF_USERNAME: validated_input[CONF_USERNAME],
                    CONF_PASSWORD: validated_input[CONF_PASSWORD],
                    CONF_DEBUG_LOGGING: user_input[CONF_DEBUG_LOGGING],
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._async_options_schema(user_input),
        )
