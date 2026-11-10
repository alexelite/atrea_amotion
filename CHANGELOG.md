# Changelog

## 1.2.3 — 2026-11-10

### Fixed

- Prevent websocket debug logs from exposing login credentials and session tokens.
  Log only message endpoints and IDs, and omit raw undecodable or non-object
  payloads so fragmented authentication replies are safe to log as well.
- Stop logging raw UDP discovery packets, MAC addresses and production
  numbers in discovery debug logs.

## 1.2.2 — 2026-11-07

### Added

- Add a requested ventilation airflow number entity for units controlled in m³/h.
- Add Czech translations and translation keys for entity names.

### Maintenance

- Add the GPL-3.0 license, retaining attribution to the original project.
- Add HACS and hassfest validation on pushes, pull requests, and a daily schedule.
- Add the issue tracker URL and correct the code owner handle in the manifest.
- Remove the unsupported `iot_class` setting from `hacs.json`; the integration
  manifest continues to declare local polling.
- Keep protocol notification translations in separate resource files so Home
  Assistant translation validation accepts the integration without changing
  notification messages or language fallback.

### Changed

- Document Marketplace installation and add direct Marketplace and HACS install
  buttons, retaining instructions for older Home Assistant versions.
- Use the official aMotion branding for the integration instead of the general
  Atrea branding, making the supported control system easier to identify.
- Provide local brand icons at 256 × 256 and 512 × 512 pixels for Home Assistant
  2026.3 and newer. The square aMotion icon also serves as the integration logo.

Existing configuration is preserved. The branding and validation changes do not
change existing entity identifiers or device control behavior.
