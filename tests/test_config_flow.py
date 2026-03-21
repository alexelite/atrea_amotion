"""Tests for Atrea aMotion config and options flows."""

from __future__ import annotations

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

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_DEBUG_LOGGING: True},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_DEBUG_LOGGING: True}
