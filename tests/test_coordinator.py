"""Tests for the Atrea coordinator."""

from __future__ import annotations

from custom_components.atrea_amotion.__init__ import AtreaAMotionCoordinator


def test_ui_diagram_data_nested_payload_is_unwrapped(hass) -> None:
    """Nested ui_diagram_data payloads should be flattened for derived sensors."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator._apply_ui_diagram_data(
        {
            "ui_diagram_data": {
                "bypass_estim": 0,
                "damper_io_state": True,
                "fan_eta_operating_time": 12602,
                "fan_sup_operating_time": 12602,
            }
        }
    )

    assert coordinator.value("bypass_estim") == 0
    assert coordinator.value("damper_io_state") is True
    assert coordinator.value("fan_eta_operating_time") == 12602
    assert coordinator.value("fan_sup_operating_time") == 12602


def test_motor_role_mapping_is_ambiguous_when_counters_match(hass) -> None:
    """Matching motor and fan counters should be reported as ambiguous."""
    coordinator = AtreaAMotionCoordinator(
        hass=hass,
        name="Atrea",
        host="192.0.2.10",
        username="user",
        password="pass",
        model="aMotion",
        version="1.0.0",
    )

    coordinator._apply_moments(
        {
            "m1_register": 45_395_468,
            "m2_register": 45_395_468,
        }
    )
    coordinator._apply_ui_diagram_data(
        {
            "ui_diagram_data": {
                "fan_eta_operating_time": 12609,
                "fan_sup_operating_time": 12609,
            }
        }
    )

    assert coordinator.value("motor_role_mapping") == "ambiguous"
