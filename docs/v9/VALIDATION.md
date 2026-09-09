# B.E.A.M. v9 PRO FINAL — Validation Report

## Release contract

- Frontend version: `9.0.0`
- Backend version: `9.0.0`
- Telemetry contract: `beam-final-v9`
- EnergyPlus calibration tier: `FULL_ANNUAL_TABULAR`
- Live facility reference resolution: `MONTHLY_MEAN`
- Floorplan spaces: `62`
- Operating rooms: `8`

## EnergyPlus baseline bundled with v9

The bundled `beam-backend/data/openstudio_results/eplustbl.htm` is the supplied EnergyPlus 25.2 annual tabular result and reports a full 8760-hour run. v9 imports it into `beam-backend/data/energy_baseline.json`.

Imported headline values:

- Total site energy: ~604.133 MWh/year
- Site EUI: ~163.411 kWh/m²-year
- Total building area: 3697 m²
- Conditioned building area: 3554 m²
- Annual electric peak: ~115.6125 kW
- Annual end uses include Cooling, Interior Lighting, Interior Equipment and Fans
- 62/62 floorplan spaces mapped to EnergyPlus Space Summary records

The tabular HTML proves a full annual run but does not contain an hourly 8760-point `Electricity:Facility` meter series. Therefore the live calibrated facility anchor remains `MONTHLY_MEAN`. The included SQL importer can upgrade the model to `HOURLY` if `eplusout.sql` is supplied later.

## Automated backend regression

Command:

`python -m pytest -q`

Result:

**35 / 35 PASS**

This covers digital-twin room dynamics, advanced HVAC/lighting control, Sterility/ΔP safety arbitration, HIS scheduling, Energy AI, room manual targets/modes, EnergyPlus tabular import, OpenStudio report import and frontend/backend command contract checks.

## Real WebSocket transport

A fresh Uvicorn v9 process was started on `127.0.0.1:8011`. `/health` returned:

- `version = 9.0.0`
- `floorplan_spaces = 62`
- `operating_rooms = 8`
- `energy_baseline_calibrated = true`
- `energy_calibration_tier = FULL_ANNUAL_TABULAR`
- `energy_reference_resolution = MONTHLY_MEAN`

Then `test_transport_contract.py` exercised the real `/ws` endpoint.

**26 WebSocket command scenarios PASS.**

Covered command families include global HVAC setpoints/profiles, pressure policy, Energy AI, HIS Scheduler AI, room modes, per-room manual targets/release-to-auto, external case insertion, manual OR scheduling, pressure fault/recovery and emergency ventilation modes.

## TypeScript / JSX syntax validation

`beam-frontend/src/App.tsx` was transpiled with TypeScript 5.8.3 using dependency-independent syntax diagnostics.

**0 TypeScript / JSX syntax diagnostics.**

## Python compile

`main.py`, `beam_state.py`, `energy_model.py`, `floorplan_model.py`, `his_engine.py` and all three calibration import tools compile successfully with `py_compile`.

## Production-build limitation

The validation environment does not include the complete project-local npm dependency tree. Run `INSTALL_BEAM.bat` and then `npm run build` or `RUN_TESTS.bat` on the target machine for dependency-resolved Vite/Tailwind production validation.
