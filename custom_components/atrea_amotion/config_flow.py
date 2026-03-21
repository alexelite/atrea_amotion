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

from .const import API_TIMEOUT, DOMAIN, LOGGER

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atrea aMotion."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                login_data = {
                    "username": user_input[CONF_USERNAME],
                    "password": user_input[CONF_PASSWORD],
                }
                response = await self.hass.async_add_executor_job(
                    partial(
                        requests.post,
                        f"http://{user_input[CONF_HOST]}/api/login",
                        json=login_data,
                        timeout=API_TIMEOUT,
                    )
                )
                login_response = response.json()

                if login_response.get("code") == "OK" and "result" in login_response:
                    discovery_url = f"http://{user_input[CONF_HOST]}/api/discovery"
                    discovery_response = await self.hass.async_add_executor_job(
                        partial(requests.get, discovery_url, timeout=API_TIMEOUT)
                    )
                    discovery_data = discovery_response.json()
                    result_data = discovery_data.get("result", {})

                    user_input["model"] = result_data.get("type")
                    user_input["version"] = result_data.get("version")
                    user_input["production_number"] = result_data.get(
                        "production_number"
                    )
                    user_input["mac"] = result_data.get("board_number")

                    unique_id = (
                        user_input["mac"]
                        or user_input.get("production_number")
                        or user_input[CONF_HOST]
                    )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"{user_input[CONF_HOST]}", data=user_input
                    )
                if login_response.get("code") == "INVALID_USER":
                    errors["base"] = "invalid_user"
                else:
                    errors["base"] = "invalid_auth"
            except requests.RequestException:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
