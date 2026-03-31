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

### Active-State Notification Modeling

Do not leave websocket active states as a raw backend-only structure when a UI consumer needs human-readable alerts.

Current strategy:

- the integration is the source of truth for active-state message construction
- `ui_info.states.active` provides the currently active ids and semantic names
- `ui_diagram_scheme.baseStates` provides classification metadata such as `purpose`, `severity`, and `type`
- translation text is stored in Home Assistant-friendly JSON under `custom_components/atrea_amotion/translations/en.json`
- the coordinator normalizes all of that into a stable notification payload

Notification payload fields:

- `id`
- `code`
- `purpose`
- `severity`
- `kind`
- `prefix`
- `translation_key`
- `message`
- `message_code`
- `full_message`
- `active`

Aggregate notification fields:

- `notifications`
- `notification_count`
- `warning_count`
- `fault_count`
- `highest_severity`
- `primary_message`
- `has_warning`
- `has_fault`

Entity exposure rules:

- `climate` should expose the aggregate notification payload as attributes because the dedicated card already reads the climate entity first
- `sensor.active_notifications` should expose the same payload for diagnostics, templates, and dashboards that do not want to depend on the climate entity
- keep legacy `warning` and `fault` booleans for backward compatibility

Card contract rules:

- the dedicated Lovelace card should consume the normalized payload from the integration
- the card should not ship its own websocket-state translation table
- if the payload is missing, the card may fall back to legacy `warning` / `fault` booleans with generic text

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
