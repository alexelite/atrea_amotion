"""Fixtures for testing."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry as ConfigEntryMock


@pytest.fixture
def MockConfigEntry():
    """Expose the config-entry factory used throughout this suite."""
    return ConfigEntryMock


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return
