"""Tests for config entry rediscovery during setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME

from custom_components.atrea_amotion import async_setup_entry
from custom_components.atrea_amotion.const import DOMAIN


async def test_async_setup_entry_rediscovery_updates_host(hass, MockConfigEntry) -> None:
    """Setup should retry with a rediscovered host when the stored one is stale."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old host",
        data={
            CONF_NAME: "Atrea",
            CONF_HOST: "192.0.2.10",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            "board_number": "BOARD-1",
            "production_number": "PN-1",
            "unit_name": "Homer HRV",
        },
    )
    entry.add_to_hass(hass)

    initialize = AsyncMock(side_effect=[Exception("offline"), None])

    with (
        patch(
            "custom_components.atrea_amotion.AtreaAMotionCoordinator.async_initialize",
            initialize,
        ),
        patch(
            "custom_components.atrea_amotion.async_rediscover_config_entry",
            AsyncMock(
                return_value={
                    "ip": "192.0.2.20",
                    "source_ip": "192.0.2.20",
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "board_number": "BOARD-1",
                    "production_number": "PN-1",
                    "unit_name": "Homer HRV",
                    "model": "aMotion",
                    "version": "2.0.0",
                }
            ),
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=True)),
    ):
        assert await async_setup_entry(hass, entry) is True

    assert entry.data[CONF_HOST] == "192.0.2.20"
    assert entry.title == "Homer HRV"
    assert hass.data[DOMAIN][entry.entry_id]["atrea"].host == "192.0.2.20"
