# Atrea aMotion for Home Assistant

Home Assistant custom integration for Atrea HRV and ERV units equipped with the aMotion control system.

The integration uses local websocket communication and is designed around the reality that aMotion is not just a thermostat-style device. Depending on the unit capabilities, it can expose ventilation control, comfort control, bypass control, and telemetry.

## Current Direction

The integration is being refactored to be capability-driven.

That means entity creation is based on what the unit actually exposes at runtime, especially through:

- `discovery`
- `ui_control_scheme`
- `ui_diagram_scheme`
- `ui_info`

For units like the currently tested Elementary aM-CE board, the intended entity model is:

- separate `fan` entities for supply and extract when independent fan control is available
- a `climate` entity for temperature request and work regime
- a `select` entity for bypass mode when bypass control is exposed
- `sensor` entities for telemetry and active states

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open the menu and choose `Custom repositories`.
4. Add this GitHub repository as an `Integration`.
5. Search for `Atrea aMotion`.
6. Install it.
7. Restart Home Assistant.
8. Add the integration from `Settings` -> `Devices & services`.

### Manual

1. Copy `custom_components/atrea_amotion` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings` -> `Devices & services`.

## Configuration

The config flow currently asks for:

- name
- host
- username
- password

The integration connects directly to the unit over the local network.

## Status

This project is actively evolving.

The current implementation focuses on:

- local websocket transport
- capability discovery
- separate supply and extract fan support
- climate support for work regime and target temperature
- bypass control as a select entity
- telemetry and active-state sensors
- bypass/runtime sensors such as `bypass_estim`, `damper_io_state`, and fan operating hours
- filter/service sensors such as next filter check, last filter replacement, days remaining, and maintenance registers
- a button action to confirm filter replacement and reset the filter interval on the unit
- switch actions to enable or disable Modbus TCP and firmware auto update
- a maintenance button to request a unit reboot
- a text action to edit the unit name from Home Assistant

Some protocol features are intentionally documented first and planned for later implementation, especially:

- temporary override duration and automatic rollback
- scenes
- calendars
- triggers
- Modbus TCP support
- broader support validation across more aMotion variants

## Protocol Notes

Working protocol and entity-model notes are kept here:

- `docs/WEBSOCKET_API.md`
- `docs/ENTITY_STRATEGY.md`

These files are meant to be the reference for future changes so the integration stays coherent as more capabilities and unit variants are added.

## Attribution

This integration was inspired by and originally derived from the work of `@xbezdick` on an earlier aMotion Atrea integration.

That earlier work helped establish the initial Home Assistant support path for aMotion units. This project continues from that starting point but expands the design toward a broader multi-platform model, because the aMotion system exposes much more than a single `climate` abstraction can comfortably represent.

## Notes

- This integration uses local websocket communication.
- Cloud access is not required for the observed local control flow.
- Different aMotion boards and unit configurations may expose different capabilities, so runtime detection is preferred over hardcoded assumptions.
