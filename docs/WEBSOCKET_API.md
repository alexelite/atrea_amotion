# Atrea aMotion WebSocket API Notes

This document captures observed behavior from a local websocket session against an aMotion unit.
It is intended as a working reference for integration design and future protocol work.

## Scope

These notes are based on direct local communication with an Atrea aMotion unit over:

- `ws://<host>/api/ws`
- no cloud relay in the observed session

Observed unit:

- board type: `CE`
- product: `DUPLEX 370 EC5.aM`
- version: `aMCE-v2.4.5`
- family: Elementary aM-CE

The protocol should still be treated as capability-driven. Future units may expose different requests, states, or control schemes.

## Session Flow

Observed websocket startup flow:

1. Open websocket to `ws://<host>/api/ws`
2. Request `time`
3. Request `discovery`
4. Send `login` with username and password
5. Request `user`
6. Send `login` again with returned token
7. Request `user` again
8. Request `ui_diagram_scheme`
9. Request `ui_control_scheme`
10. Request `ui_info`
11. Request `control_panel`

The browser UI also requests scenes, calendars, trigger configuration, and other admin/config data. Those are useful for future work but are not required for the first Home Assistant integration pass.

## Authentication

Login is a 2-step process.

Password login:

```json
{"endpoint":"login","args":{"username":"ha","password":"haos"},"id":3}
```

Response:

```json
{"code":"OK","error":null,"id":3,"response":"ATCdm70g1jjswzo","type":"response"}
```

Token login:

```json
{"endpoint":"login","args":{"token":"ATCdm70g1jjswzo"},"id":5}
```

Response:

```json
{"code":"OK","error":null,"id":5,"response":"ATCdm70g1jjswzo","type":"response"}
```

Notes:

- The token returned by the first login can be reused immediately in the websocket session.
- The UI queries `user` both before and after token login.

## Core Endpoints

These are the most important endpoints for the Home Assistant integration.

### `discovery`

Provides unit identity and board metadata.

Observed response fields:

- `board_number`
- `board_type`
- `brand`
- `name`
- `production_number`
- `type`
- `version`
- `activation_status`
- `initialized`
- `commissioned`

Observed example:

```json
{
  "activation_status": "READY",
  "board_number": "70:b8:f6:44:50:89",
  "board_type": "CE",
  "brand": "atrea.cz",
  "name": "DUPLEX 370 EC5.aM",
  "production_number": "353232322",
  "type": "DUPLEX 370 EC5.aM",
  "version": "aMCE-v2.4.5"
}
```

Integration use:

- device identity
- software version
- board family hint
- future feature heuristics if needed

### `ui_control_scheme`

This is the main capability descriptor and should be treated as the source of truth for entity creation.

Observed top-level sections:

- `config`
- `requests`
- `scene_items`
- `states`
- `types`
- `unit`

Observed control requests on the test unit:

- `work_regime`
- `temp_request`
- `bypass_control_req`
- `fan_power_req_sup`
- `fan_power_req_eta`

Observed type metadata:

- ranges include `min`, `max`, `step`, `unit`
- enums include `values`

Observed important enum types:

- `work_regime`: `OFF`, `AUTO`, `VENTILATION`, `NIGHT_PRECOOLING`, `DISBALANCE`
- `bypass_control_req`: `AUTO`, `CLOSED`, `OPEN`
- `season_current`
- `mode_current`

Integration rule:

- create entities from `requests` and `types`
- expose sensors from `unit`
- expose state/alarm data from `states`

### `ui_info`

Returns current unit state and is also pushed later as an event.

Observed shape:

```json
{
  "requests": {
    "bypass_control_req": "AUTO",
    "fan_power_req_eta": 57,
    "fan_power_req_sup": 63,
    "temp_request": 24.5,
    "work_regime": "DISBALANCE"
  },
  "states": {
    "active": {
      "105": {
        "active": true,
        "name": "FILTER_INTERVAL"
      }
    }
  },
  "unit": {
    "fan_eta_factor": 0,
    "fan_sup_factor": 0,
    "mode_current": "STARTUP",
    "season_current": "HEATING",
    "temp_eha": 17.764,
    "temp_eta": 19.276001,
    "temp_ida": 19.276001,
    "temp_oda": 18.411999,
    "temp_oda_mean": null,
    "temp_sup": 22.623999
  }
}
```

Integration rule:

- `requests` are the requested setpoints or requested operating values
- `unit` is measured or effective runtime data
- `states.active` is a structured list of currently active conditions

### `ui_diagram_scheme`

Provides schematic and semantic hints about the unit.

Observed useful sections:

- `components.fans`
- `components.recuperation.bypass`
- `components.io_dampers`
- `baseStates`

This endpoint is useful for:

- detecting presence of bypass-related visualization
- identifying separate fan paths
- mapping alarm and warning names to user-facing sensors later

It should be treated as supplemental capability data, not as the main control source.

### `control`

Writes requested values.

Observed examples:

```json
{"endpoint":"control","args":{"variables":{"fan_power_req_sup":63}},"id":24}
{"endpoint":"control","args":{"variables":{"fan_power_req_eta":57}},"id":25}
{"endpoint":"control","args":{"variables":{"bypass_control_req":"CLOSED"}},"id":34}
{"endpoint":"control","args":{"variables":{"temp_request":24.5}},"id":37}
{"endpoint":"control","args":{"variables":{"work_regime":"AUTO"}},"id":40}
```

Observed success response:

```json
{"code":"OK","error":null,"id":24,"response":"OK","type":"response"}
```

The websocket also accepted a timed override form:

```json
{"endpoint":"control","args":{"duration":3600},"id":38}
```

Observed result:

- `control_panel.finishTime` became a future timestamp
- `control_panel.remaining` became `3600`
- current temporary values remained active

This suggests the UI treats duration as a temporary validity window for already-staged changes.

## Observed Event Model

The unit pushes events after login and after control actions.

Observed important event types:

- `ui_info`
- `control_panel`
- `control_invoked`
- `disposable_plan`
- `scene_activity_change`

### `control_panel`

This event appears to represent staged or temporary override state.

Observed fields:

- `current`
- `stored`
- `origin`
- `visible`
- `remaining`
- `finishTime`
- `currentCalendarId`
- `outOfCalendar`

Observed behavior:

- after a `control` write, `stored` changes first
- `current` may still show the previous effective value
- after some seconds, `control_invoked` arrives
- later `ui_info` updates the effective `requests`
- when no temporary control is active, `visible` becomes `false`

Working interpretation:

- `origin` is the baseline before temporary override
- `stored` is the target staged override
- `current` is the currently effective override panel state
- `remaining` and `finishTime` track temporary validity

This is important for future support of temporary overrides, but it does not need to be implemented in the first version of the Home Assistant integration.

### `control_invoked`

Observed example:

```json
{
  "args": {
    "variables": {
      "bypass_control_req": "AUTO",
      "fan_power_req_eta": "57",
      "fan_power_req_sup": "63",
      "temp_request": "24.5",
      "work_regime": "DISBALANCE"
    }
  },
  "event": "control_invoked",
  "type": "event"
}
```

Working interpretation:

- indicates the staged control values have been applied by the unit
- acts as a transition signal between request submission and effective runtime update

### `ui_info` event

Observed after controls settle.

This should be treated as the authoritative runtime update for entity state in Home Assistant.

## Capability Deductions From The Test Unit

Observed test-unit capabilities:

- independent fan control: yes
- supply fan request: yes
- extract fan request: yes
- unified fan request: not observed
- bypass control: yes
- temperature setpoint control: yes
- work regime control: yes
- temporary override duration: yes

Observed Home Assistant-facing implications:

- create a `fan` entity for supply
- create a `fan` entity for extract
- create a `climate` entity for work regime and temperature request
- create a `select` for bypass control
- create sensors for temperatures, season, mode, and runtime factors

Do not assume every aMotion unit has the same capabilities. Entity creation should be based on runtime capability discovery.

## Entity Modeling Notes

Recommended first-pass mapping:

- `fan_power_req_sup` -> supply fan percentage entity
- `fan_power_req_eta` -> extract fan percentage entity
- `bypass_control_req` -> bypass select entity
- `temp_request` + `work_regime` -> climate entity
- `fan_sup_factor` and `fan_eta_factor` -> measured fan activity sensors
- `temp_*` values -> temperature sensors
- `season_current` -> sensor
- `mode_current` -> sensor
- `states.active` -> future alarm/status entities

Important distinction:

- `requests` are not the same as measured runtime data
- `mode_current` is not the same as `work_regime`

Observed example:

- `work_regime` became `VENTILATION`
- `mode_current` still reported `STARTUP`

The integration should preserve that distinction.

## Temporary Override Behavior

The browser UI supports a concept described in the interface as the validity of performed changes.

Observed behavior:

- values are written using `control`
- optional validity is applied with `control` and `args.duration`
- the unit tracks baseline, stored override, active override, and remaining time in `control_panel`
- after expiry, the unit is expected to return toward the original state

Current integration decision:

- document this behavior now
- do not expose it in the first Home Assistant version
- keep the protocol model ready for a future feature such as temporary overrides

Possible future HA representations:

- service call with optional duration
- button or script-driven temporary override
- helper-backed automation layer rather than a first-class entity

## Open Questions

These are the most important unknowns to investigate later.

- Do some units expose a unified `fan_power_req` request instead of separate supply and extract requests?
- How does the protocol signal units where bypass is automatic-only and not user-controllable?
- Are there units where `temp_request` is present but does not imply meaningful `climate` behavior?
- What additional fields appear when heat-source control is available on advanced units?
- What are the event semantics on Legacy boards?
- Is temporary override duration always a separate `control` call, or can it be combined with variable updates in one call?

## Implementation Guidance

For the integration codebase:

- use `ui_control_scheme` as the primary capability descriptor
- use `ui_info` as the primary state payload
- treat `ui_diagram_scheme` as supplemental metadata
- keep `control_panel` modeled internally for future features
- avoid assuming one fixed entity layout across all units
- separate requested values from measured values in the internal state model

## Example Minimal Initialization Set

Recommended minimum websocket sequence for the integration:

1. `login` with username and password
2. `login` with token
3. `discovery`
4. `ui_control_scheme`
5. `ui_diagram_scheme`
6. `ui_info`
7. optionally `control_panel`

Recommended steady-state behavior:

- listen for pushed `ui_info` events
- optionally send keepalive `ping`
- refresh with explicit `ui_info` only as fallback
