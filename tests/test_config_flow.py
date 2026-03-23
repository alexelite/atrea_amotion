"""Tests for Atrea aMotion config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.atrea_amotion.const import CONF_DEBUG_LOGGING, DOMAIN


async def test_options_flow_exposes_debug_toggle(
    hass: HomeAssistant, MockConfigEntry
) -> None:
    """Options flow should expose the debug logging toggle."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Atrea",
        data={
            CONF_NAME: "Atrea",
            CONF_HOST: "192.0.2.10",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            CONF_DEBUG_LOGGING: False,
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert CONF_HOST in result["data_schema"].schema
    assert CONF_USERNAME in result["data_schema"].schema
    assert CONF_PASSWORD in result["data_schema"].schema
    assert CONF_DEBUG_LOGGING in result["data_schema"].schema


async def test_options_flow_saves_debug_toggle(
    hass: HomeAssistant, MockConfigEntry
) -> None:
    """Options flow should persist debug logging selection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Atrea",
        data={
            CONF_NAME: "Atrea",
            CONF_HOST: "192.0.2.10",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            CONF_DEBUG_LOGGING: False,
        },
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.atrea_amotion.config_flow._async_validate_connection",
        AsyncMock(
            return_value=(
                {
                    CONF_HOST: "192.0.2.10",
                    CONF_USERNAME: "user",
                    CONF_PASSWORD: "pass",
                    CONF_DEBUG_LOGGING: True,
                    "model": None,
                    "version": None,
                    "production_number": None,
                    "mac": None,
                },
                None,
            )
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "192.0.2.10",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
                CONF_DEBUG_LOGGING: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: "192.0.2.10",
        CONF_USERNAME: "user",
        CONF_PASSWORD: "pass",
        CONF_DEBUG_LOGGING: True,
    }


async def test_options_flow_updates_connection_details(
    hass: HomeAssistant, MockConfigEntry
) -> None:
    """Options flow should allow editing host and credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Atrea",
        data={
            CONF_NAME: "Atrea",
            CONF_HOST: "192.0.2.10",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            "model": "Old model",
            "version": "1.0.0",
            "production_number": "123",
            "mac": "aa:bb",
            CONF_DEBUG_LOGGING: False,
        },
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.atrea_amotion.config_flow._async_validate_connection",
        AsyncMock(
            return_value=(
                {
                    CONF_HOST: "192.0.2.20",
                    CONF_USERNAME: "admin",
                    CONF_PASSWORD: "secret",
                    CONF_DEBUG_LOGGING: True,
                    "model": "New model",
                    "version": "2.0.0",
                    "production_number": "456",
                    "mac": "cc:dd",
                },
                None,
            )
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_HOST: "192.0.2.20",
                CONF_USERNAME: "admin",
                CONF_PASSWORD: "secret",
                CONF_DEBUG_LOGGING: True,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_HOST] == "192.0.2.20"
    assert entry.data[CONF_USERNAME] == "admin"
    assert entry.data[CONF_PASSWORD] == "secret"
    assert entry.data["model"] == "New model"
    assert entry.title == "192.0.2.20"
    assert result["data"] == {
        CONF_HOST: "192.0.2.20",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        CONF_DEBUG_LOGGING: True,
    }
