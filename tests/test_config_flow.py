"""Tests for Atrea aMotion config and options flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.atrea_amotion.const import CONF_DEBUG_LOGGING, DOMAIN
from custom_components.atrea_amotion.config_flow import CONF_DEVICE_ID


async def test_user_flow_creates_entry_from_discovered_device(hass: HomeAssistant) -> None:
    """User flow should use proprietary UDP discovery results."""
    with (
        patch(
            "custom_components.atrea_amotion.config_flow.async_discover_enriched_devices",
            AsyncMock(
                return_value=[
                    {
                        "ip": "192.0.2.10",
                        "source_ip": "192.0.2.10",
                        "mac": "aa:bb:cc:dd:ee:ff",
                        "unit_name": "Homer HRV",
                        "production_number": "PN-1",
                        "board_number": "BOARD-1",
                    }
                ]
            ),
        ),
        patch(
            "custom_components.atrea_amotion.config_flow._async_validate_connection",
            AsyncMock(
                return_value=(
                    {
                        CONF_NAME: "Homer HRV",
                        CONF_HOST: "192.0.2.10",
                        CONF_USERNAME: "user",
                        CONF_PASSWORD: "pass",
                        CONF_DEBUG_LOGGING: False,
                        "model": "aMotion",
                        "version": "2.0.0",
                        "production_number": "PN-1",
                        "board_number": "BOARD-1",
                        "mac": "BOARD-1",
                        "network_mac": "aa:bb:cc:dd:ee:ff",
                        "unit_name": "Homer HRV",
                    },
                    None,
                )
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] is FlowResultType.FORM
        assert CONF_DEVICE_ID in result["data_schema"].schema

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_DEVICE_ID: "BOARD-1",
                CONF_NAME: "Homer HRV",
                CONF_USERNAME: "user",
                CONF_PASSWORD: "pass",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Homer HRV"
    assert result["data"][CONF_HOST] == "192.0.2.10"
    assert result["data"]["network_mac"] == "aa:bb:cc:dd:ee:ff"


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

    with patch(
        "custom_components.atrea_amotion.config_flow.async_discover_enriched_devices",
        AsyncMock(return_value=[]),
    ):
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

    with (
        patch(
            "custom_components.atrea_amotion.config_flow.async_discover_enriched_devices",
            AsyncMock(return_value=[]),
        ),
        patch(
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
                        "board_number": None,
                        "mac": None,
                        "network_mac": None,
                        "unit_name": None,
                    },
                    None,
                )
            ),
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

    with (
        patch(
            "custom_components.atrea_amotion.config_flow.async_discover_enriched_devices",
            AsyncMock(return_value=[]),
        ),
        patch(
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
                        "board_number": "cc:dd",
                        "mac": "cc:dd",
                        "network_mac": "aa:bb:cc:dd:ee:ff",
                        "unit_name": "Updated Unit",
                    },
                    None,
                )
            ),
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
    assert entry.title == "Updated Unit"
    assert result["data"] == {
        CONF_HOST: "192.0.2.20",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        CONF_DEBUG_LOGGING: True,
    }
