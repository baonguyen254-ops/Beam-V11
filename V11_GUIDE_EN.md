# BEAM v11.1 English Demo — User and Developer Guide

## 1. Start a working hospital demonstration

Extract the full distribution, install Python 3.12 or later, and run `INSTALL_BEAM.bat` once. Start `START_BEAM.bat`. At `http://127.0.0.1:8000`, select **Open demo dashboard**. Initial preparation takes a few seconds. No bootstrap key or shared password is required for the local demo presenter.

The frontend is already compiled. Node.js 22 is needed only for frontend development. After Python dependencies are installed, the demo runs locally without an external model API, patient database or physical BMS. The original supplied floorplan is the only required real input. The shipped OpenStudio and EnergyPlus assets are retained for existing engineering views; when those optional reference assets are absent, the demo derives modeled loads from room geometry and category defaults.

The interface, forms, alerts, authentication messages and number/date formatting use English (`en-US`). VND remains the explicit financial currency. Reporting uses the configured timezone, initially `Asia/Ho_Chi_Minh`. Original source labels inside the floorplan remain unchanged and map to English room names in the interface.

## 2. What is ready immediately

| Data or model | Prepared content |
|---|---|
| Layout | Eight operating rooms in the supplied hospital floorplan |
| Opening workflow | 16 cases and linked fictional patients, including scheduled, active, completed and unscheduled examples |
| Team | 24 fictional staff with roles and specialty availability |
| Equipment | 32 devices: 24 core operating-room devices and eight auxiliary insufflators |
| Asset engineering | Installation/service dates, runtime, eight inspection samples per device and calculated degradation trends |
| Clinical demonstration | Three artificial logistic models with synthetic evaluation datasets |
| Historical cases | 1,024 synthetic completed cases and outcomes across 32 procedure types |
| Smart traits | Seeded duration traits and temperature/humidity response samples, updated as the simulation runs |
| Energy history | 370 days hourly, 24 hours minute-level and 15 minutes second-level, plus live observations |
| Finance | Demo tariff, CAPEX/OPEX, per-room allocation and an example BMS cost |

All of these records are generated or marked as simulation data. Numerical benchmark scores describe synthetic teaching samples generated from the demonstration formula. They are not independent clinical validation results.

## 3. A practical walkthrough

Open the room workspace and select an operating room. The room detail connects its live conditions, next case, patient, team, devices, readiness, automation targets, thermal forecast and finance. Use an upcoming scheduled case to edit preoperative inputs; an active or completed case intentionally does not permit a new preoperative prediction.

Change a permitted input such as ASA class, save the inputs, then run and save a prediction. The displayed percentage is computed from the selected model and case inputs, so it changes when inputs change. The recorded prediction retains its model version, inputs, time and provenance. Repeated delivery of the same command does not create a duplicate prediction.

Open scheduling to preview an allocation for pending cases and apply the proposed plan. Eight pending cases are staged at startup so there is something to schedule manually before automatic planning resumes for that opening queue after approximately five minutes. New stochastic intake starts after approximately 45 seconds; subsequent arrival intervals vary. Automatic scheduling and the virtual case lifecycle continue in the background when enabled. Preview and apply both check capabilities, staff, devices, preparation/recovery capacity and conflicts on the backend.

Adjust a room temperature target to observe the virtual BMS response. Release room automation to return to automatic targets. The controller considers the next case and predicted preparation time; active clinical, emergency, pressure and manual policies remain higher-priority constraints. A virtual response is labeled separately from a physical gateway receipt.

Review a device's age, runtime, service record, inspections and estimated remaining life. Remaining life depends on the configured design limit and observed trend; it is an estimate tied to those assumptions. The prepared data includes an auxiliary device in maintenance while keeping required opening-case equipment usable.

Open energy/ROI, select a room or facility, and switch between second, minute, hour, day, month and year resolutions. Select SIMULATION to inspect demo totals. A CONNECTED filter has no demo samples. Fine-grained history covers a shorter window than hourly history; selecting a date outside that stored window can correctly return no fine-grained points.

## 4. Demonstration model pack

The following declarative JSON models are bundled in `examples/demo/models/`, together with 400 synthetic evaluation rows per model:

| Model ID | Demonstration population |
|---|---|
| `demo-general-1.0` | General, gastrointestinal and urology cases |
| `demo-complex-1.0` | Cardiac, vascular, neurosurgery and trauma cases |
| `demo-specialty-1.0` | Orthopedics, ENT, minor, endoscopy and gynecology cases |

The artificial logistic formula uses declared feature normalization and coefficients for age, ASA class, emergency status, BMI, hemoglobin, albumin and creatinine. The engine checks applicable specialty, feature bounds, units and input age. Formula evaluation happens in the backend; the browser does not invent an independent probability.

Prepared models have status `DEMO_READY`, are simulation-only and contain no clinician approval. Re-evaluating a bundled synthetic dataset preserves that distinction. They cannot become eligible in standard or connected operation merely because they passed a synthetic benchmark. The model registry still supports the original registration, evaluation, attributed review, expiry and revocation workflow for separately supplied standard-mode models. `examples/clinical/` contains the standard import template; it is not needed to run this demo.

Synthetic outcomes also populate the historical cohort view. Cohort success rates, model predictions and readiness checklists are separate quantities. None of the demonstration percentages establishes a real patient's surgical prognosis.

## 5. Smart traits and energy accounting

Temperature and humidity models start with synthetic response experiments so preparation forecasts are available immediately. Case duration traits begin with procedure history and continue to incorporate eligible observations. Their source labels distinguish simulation from connected observations; changing a label does not convert synthetic training history into real evidence.

Energy is integrated from power and elapsed seconds: `energy_kWh = power_kW × elapsed_seconds / 3600`. Savings are signed: `baseline_kWh − actual_kWh`. Negative savings remain negative. Cost savings use the applicable tariff; carbon uses the configured factor. Room and facility ledgers retain their scope and source. A modeled room sum and a whole-facility EnergyPlus reference have different boundaries and are not presented as identical measurements.

The synthetic history is deliberately generated as a simulation trace. It is not an hourly meter series extracted from a monthly report. Within overlapping seeded windows, second/minute/hour buckets integrate the same load assumptions. Day, month and year reports aggregate the durable history; real measured coverage for the demo remains zero.

The opening example uses VND 850 million CAPEX, VND 24 million annual OPEX and area-based room allocations, with an example VND 1.5 million cost. Net benefit accounts for the selected observation period, applicable operating costs and recorded costs. ROI and projected payback follow the selected scope and source; payback is conditional on positive annualized net benefit. These inputs can be changed in the dashboard. Demonstration savings do not guarantee a financial return.

## 6. Resume, create a fresh demo or keep standard data

`START_BEAM.bat` resumes `beam-backend/data/runtime/demo-v11-1`. Model versions, records, saved predictions and accumulated energy persist. Initial seed history is not duplicated on restart. Close the server before launching another session on the same port.

`START_NEW_DEMO.bat` creates a separate timestamped directory. It does not erase an earlier demo. Use it for a fresh presentation after a long idle interval: startup-relative cases and fine-grained history are then current. To reopen a particular separate session, use its printed directory:

```bash
python RUN_BEAM.py --demo --demo-data-dir /absolute/path/to/demo-directory --open
```

`START_STANDARD.bat` uses the original standard workspace and respects `BEAM_DATA_DIR`. In standard first-time setup, use that workspace's `bootstrap-key.txt` to create an administrator. Existing standard data is not imported into the demo. Explicit demo launch uses its own directory even when `BEAM_DATA_DIR` is set. A demo refuses a connected database or non-demo clinical records, blocks external HIS/BMS integration writes and cannot switch to CONNECTED in-place.

The local presenter endpoint only works for a demo on loopback with a trusted request origin. Network deployments use standard authentication. One backend worker owns each SQLite workspace. See `DEPLOY_HTTPS.md` for internal standard deployment and backup guidance.

## 7. Develop and validate

The main integration points are `demo_pack.py`, `runtime.py`, `hospital.py`, `operations_v11.py`, `clinical_models.py`, `his_engine.py`, `main.py` and the React workspaces. `RUN_BEAM.py` selects the workspace and launches the same API and production frontend together. `INTERACTION_CONTRACT.md` records version, transport, permission and command behavior.

Install development dependencies with `INSTALL_DEV.bat`; use `RUN_TESTS.bat` for regression, contracts, frontend build and HTTP/WebSocket smoke checks. On other platforms, the equivalent commands are listed in `VALIDATION.md`. Build the frontend with `python tools/build_frontend.py` to update the bundled static assets.

Check `VALIDATION.md` for executed results. Transport tests exercise actual servers and isolated databases; they do not establish browser layout, native Windows behavior, physical BMS commissioning or clinical performance. Historical release documents remain in `docs/` for feature provenance.
