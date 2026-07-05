# Priority HRV Controller Blueprint

This example provides a Home Assistant blueprint that controls one HRV/ERV unit with explicit mode priority:

1. `night_cooling`
2. `day`
3. `standby`

The goal is to keep the existing daytime CO2 control logic mostly intact while adding a higher-priority night cooling window that can overlap with the work schedule.

## Design

The blueprint computes one active mode at a time:

- `night_cooling` when `night_cooling_schedule` is `on`
- `day` when `night_cooling_schedule` is `off` and `work_schedule` is `on`
- `standby` otherwise

Each mode defines a full desired state:

- `preset_mode`
- `fan_mode`
- `bypass` select option

That makes transitions predictable. For example, if night cooling ends at `07:00` and the work schedule has already been `on` since `04:00`, the next evaluation switches the unit directly from:

- `Ventilation` + fixed cooling fan + `Open`

to:

- `Ventilation` + CO2-based fan + `Auto`

## Why A Select For Bypass

In this integration, bypass control is exposed as a `select` entity, not as a `climate` service.

Expected select options:

- `Auto`
- `Open`
- `Closed`

## Why A Blueprint

In a regular Home Assistant automation, trigger entity ids usually need to be repeated separately from the variables used later in the actions. A blueprint avoids most of that duplication by promoting those values to inputs.

This makes it easier to reuse the same controller across multiple units without copying and editing the same entity ids in several places.

## Blueprint Inputs

The blueprint exposes these inputs per unit:

- `unit_climate`
- `bypass_select`
- `work_schedule`
- `night_cooling_schedule`
- `co2_sensor`
- `day_fan_min`
- `day_fan_max`
- `day_co2_low`
- `day_co2_high`
- `night_cooling_fan`
- `day_preset`
- `standby_preset`
- `day_bypass`
- `night_bypass`
- `standby_bypass`
- `standby_fan`
- `poll_minutes`

## Files

- Blueprint: [blueprint.yaml](/Users/alex/Workspace/atrea-amotion/docs/home_assistant_examples/priority_hrv_controller/blueprint.yaml)
- This guide: [README.md](/Users/alex/Workspace/atrea-amotion/docs/home_assistant_examples/priority_hrv_controller/README.md)

## Notes

- The blueprint uses both schedule state triggers and a periodic trigger so it reacts quickly to transitions and also self-corrects if a command is missed.
- `day` fan control uses linear interpolation between `day_fan_min` and `day_fan_max` over the CO2 range `day_co2_low` to `day_co2_high`.
- `standby` still sets `fan_mode: "0"` even if the preset already stops the unit. This is intentional and keeps the desired state explicit.
