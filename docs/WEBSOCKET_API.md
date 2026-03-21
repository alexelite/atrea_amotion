# Atrea aMotion WebSocket Notes

Useful websocket endpoints confirmed from captured startup traffic:

- `login`
  - supports both `{ "username", "password" }` and `{ "token" }`
- `discovery`
  - returns model, firmware version, board number and cloud metadata
- `ui_info`
  - returns requested values, live unit values and active states
- `ui_diagram_data`
  - returns live diagram values such as:
    - `bypass_estim`
    - `damper_io_state`
    - `fan_eta_operating_time`
    - `fan_sup_operating_time`
- `control_admin/config/moments/get`
  - returns maintenance and filter-related data:
    - `filters`
    - `lastFilterReset`
    - `m1_register`
    - `m2_register`
    - `uv_lamp_register`
    - `uv_lamp_service_life`
- `modbus`
  - returns Modbus TCP status such as `active`, `enable`, `port`, `clients`
- `update`
  - returns firmware update metadata

Behavior notes:

- `ui_info.requests` and live `unit` values can be briefly out of sync right after a control command.
- `control_panel.stored` may show pending values before `ui_info.requests` catches up.
- the integration also flattens `control_panel.stored` into internal `stored_*` values plus
  `control_panel_visible` and `control_panel_remaining`
- `mode_current` can move through transient states like `STARTUP` before settling on `NORMAL`.
