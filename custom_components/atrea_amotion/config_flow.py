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

from .const import API_TIMEOUT, CONF_DEBUG_LOGGING, DOMAIN, LOGGER

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


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
        validated["mac"] = result_data.get("board_number")
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

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return AtreaOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            validated_input, error = await _async_validate_connection(self.hass, user_input)
            if validated_input is not None:
                user_input = validated_input
                user_input[CONF_DEBUG_LOGGING] = False
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
            else:
                errors["base"] = error or "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class AtreaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Atrea aMotion options."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            validated_input, error = await _async_validate_connection(self.hass, user_input)
            if validated_input is None:
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_HOST,
                                default=user_input.get(CONF_HOST, self.config_entry.data.get(CONF_HOST, "")),
                            ): str,
                            vol.Required(
                                CONF_USERNAME,
                                default=user_input.get(
                                    CONF_USERNAME, self.config_entry.data.get(CONF_USERNAME, "")
                                ),
                            ): str,
                            vol.Required(
                                CONF_PASSWORD,
                                default=user_input.get(
                                    CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD, "")
                                ),
                            ): str,
                            vol.Required(
                                CONF_DEBUG_LOGGING,
                                default=user_input.get(
                                    CONF_DEBUG_LOGGING,
                                    self.config_entry.options.get(
                                        CONF_DEBUG_LOGGING,
                                        self.config_entry.data.get(CONF_DEBUG_LOGGING, False),
                                    ),
                                ),
                            ): bool,
                        }
                    ),
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
                }
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
                title=validated_input[CONF_HOST],
            )
            return self.async_create_entry(title="", data=user_input)

        current_value = self.config_entry.options.get(
            CONF_DEBUG_LOGGING,
            self.config_entry.data.get(CONF_DEBUG_LOGGING, False),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self.config_entry.data.get(CONF_HOST, "")): str,
                    vol.Required(
                        CONF_USERNAME, default=self.config_entry.data.get(CONF_USERNAME, "")
                    ): str,
                    vol.Required(
                        CONF_PASSWORD, default=self.config_entry.data.get(CONF_PASSWORD, "")
                    ): str,
                    vol.Required(CONF_DEBUG_LOGGING, default=current_value): bool,
                }
            ),
        )
