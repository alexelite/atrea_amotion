# Entity Strategy

This document records the current entity-model decision for Home Assistant.

## Principle

Atrea aMotion should be modeled primarily as a ventilation device with additional comfort and automation capabilities.

It should not be modeled as a thermostat-first integration.

## Recommended Entity Priorities

- `fan` is the primary entity family
- `climate` is secondary and attached when supported
- `sensor` exposes telemetry and state
- `select` is used for discrete controls such as bypass mode
- future `binary_sensor` entities may represent alarms or active system states

## Fan Modeling

Use `fan` entities for proportional 0-100% airflow requests.

Rules:

- if the unit exposes independent supply and extract requests, create separate fan entities
- if the unit exposes a single unified fan request, create one main fan entity
- do not fake a unified fan if the protocol only exposes separate requests
- do not reduce proportional control to coarse predefined steps

Observed test-unit mapping:

- `fan_power_req_sup` -> supply fan
- `fan_power_req_eta` -> extract fan

## Climate Modeling

Expose `climate` only when the unit exposes meaningful comfort control such as:

- `temp_request`
- `work_regime`

The climate entity should represent:

- requested comfort temperature
- requested operating regime

The climate entity should not be the primary control surface for airflow when dedicated proportional fan entities are available.

## Bypass Modeling

If `bypass_control_req` is present as a writable enum, expose it as a `select`.

Observed enum values:

- `AUTO`
- `CLOSED`
- `OPEN`

If a future unit reports bypass feedback but not bypass control, expose only telemetry.

## Sensor Modeling

Use sensors for:

- `temp_oda`
- `temp_eta`
- `temp_eha`
- `temp_ida`
- `temp_sup`
- `temp_oda_mean`
- `fan_sup_factor`
- `fan_eta_factor`
- `season_current`
- `mode_current`

Keep requested values and measured values distinct.

## Capability-Driven Creation

Entity creation must be based on runtime capability discovery.

Primary source:

- `ui_control_scheme`

Secondary source:

- `ui_diagram_scheme`
- `discovery`

This avoids hardcoding one layout for all aMotion variants.

## Deferred Features

These features are intentionally documented but not required in the first implementation:

- temporary override validity window
- scenes
- calendars
- triggers
- advanced heat-source integration
- Modbus TCP transport
- Legacy board support differences
