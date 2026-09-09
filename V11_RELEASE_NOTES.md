# BEAM v11.1 English Demo — Release Notes

This release makes the v11 hospital dashboard usable immediately for demonstrations while preserving the earlier control and digital-twin features.

## English throughout the active application

Translated the room, hospital and clinical workspaces, login/setup, forms, alerts and backend user messages. Dates and numbers use English formatting. English quick-start and operating documentation replace the current entry documents; older documents are archived. Original floorplan data, room IDs, VND currency and the reporting timezone remain explicit.

## Prepared simulation with connected workflows

- Three bundled artificial logistic models, computed case probabilities and editable preoperative inputs.
- Eight operating rooms, 16 opening cases/patients, 24 staff and 32 devices with inspection trends.
- 1,024 historical synthetic cases, 32 duration traits and warmed thermal/humidity forecasting.
- Live simulated intake, case lifecycle, resource-aware scheduling and virtual BMS response.
- 370 days of hourly energy, 24 hours of minute history and 15 minutes of second history; all six report resolutions, per-room allocation and ROI are populated.
- Local presenter entry, persistent isolated sessions and a fresh-demo launcher.

Demo models are `DEMO_READY`, carry synthetic benchmark labels and have no fabricated clinical review. Standard-mode review gates and clinical privacy remain. Demo integration writes and in-place CONNECTED switching are blocked. Opening a demo cannot overwrite standard data.

## Integration fixes

Frontend and backend both report `11.1.0`; the compatible telemetry schema remains `beam-final-v11`. Demo startup initializes legacy charts as well as the new APIs. Pending intake receives linked patient/input data even when automatic scheduling is paused. Simulated case transitions record timestamps for duration learning. Reevaluation of a bundled demo model preserves its demo-only eligibility. Failed initialization closes its database transaction. Overlapping seeded energy resolutions conserve integrated totals, and restarting does not reseed accumulated history.

## Preserved features

Digital Twin geometry and semantic zoom, fullscreen Command Center, Light/Dark themes, heatmaps, room trends, alarms, pressure/emergency simulation, HVAC and lighting controls, HIS Scheduler, Energy AI, v10 registries/auth/persistence, v11 room forecasting, schedule preview/apply, engineering RUL, source-specific finance, clinical registry and Modbus gateway tooling remain. See `FEATURE_LINEAGE.md` and `VALIDATION.md` for scope and verification.

Start with `START_BEAM.bat`; use `START_STANDARD.bat` for the prior setup workflow. No model or patient upload is needed for the demo. Artificial probabilities are demonstrations, not validated medical predictions.
