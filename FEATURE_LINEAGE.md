# BEAM Feature Lineage and Preservation

| Release family | Retained capabilities |
|---|---|
| v8/v9 operations | Light/Dark themes; fullscreen Command Center; floorplan semantic zoom and architectural boundaries; room selection and fullscreen modal portal; manual room modes and temperature/RH/airflow targets; global HVAC/lighting; clinical control profiles; pressure trends/policies; pressure fault and recovery simulation; three emergency ventilation modes; HIS stochastic intake and manual scheduling; HIS Scheduler AI; Energy AI; heatmaps, doors, routes, alarms, utilization and trends |
| v9 engineering references | Original FloorSpace/OpenStudio geometry and model, EnergyPlus report/importers, end-use boundaries and display mapping |
| v10 hospital operations | Patient/staff/device registries; case lifecycle; resource scheduling; clinical evidence gates; online traits; SQLite persistence; signed energy ledger and ROI; accounts/permissions; idempotent commands; BMS/HIS integration contracts |
| v11 room intelligence | Linked room workspace; thermal/RH forecasts; schedule preview/apply; asset degradation/RUL; source/room finance; clinical model registration/evaluation/review/inference; immutable prediction provenance; role-aware reads; configurable Modbus TCP gateway |
| v11.1 English Demo | English active interface and documentation; prepared models/history/records; virtual room response; six-resolution energy and finance; isolated presenter sessions; persistent and fresh-demo launchers |

`test_frontend_contract.py` checks the 17 legacy action families and flagship visualization source structure. Regression and HTTP/WebSocket smoke checks cover the backend behaviors. These checks do not replace browser interaction testing. Historical release documents remain under `docs/`.
