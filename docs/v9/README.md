# B.E.A.M. v9 PRO FINAL

**Building Energy & Airflow Management — Surgical Digital Twin / HIS / Energy Supervisory Platform**

B.E.A.M. v9 is the consolidation release. It deliberately combines the strongest operational controls from v8.1 with the OpenStudio/EnergyPlus calibration work introduced in v8.2, then replaces the older annual-result baseline with the supplied **EnergyPlus 25.2 full 8760-hour annual tabular run**.

The project is a **digital-twin prototype / engineering demonstrator**, not a certified medical-device, BMS, infection-control, or life-safety controller. Safety interlocks in this project are software model guardrails and must not be presented as commissioned hospital control logic.

---

## 1. What v9 preserves and adds

### Preserved from v8.1 — operational control surface

- Light/Dark themes; **Light is the default**.
- Interactive OpenStudio floorplan with semantic zoom, pan, hard room/corridor boundaries, door and clinical-flow overlays.
- Click/tap a room to open its **Room Control** modal.
- Room telemetry: temperature, RH, airflow, power, occupancy, utilization, alarms and live trends.
- **Room Manual Setup**: per-room temperature, RH and airflow targets.
- **Room Operating Mode override**: Maximum / Auto-Balance / Minimum / Shutdown-Maintenance, with backend safety rejection where required.
- Full **Clinical HVAC & Lighting Control Plane** with global supervisory setpoints and atomic profiles.
- Full **Sterility, Pressure & Safety Interlock** with positive-pressure policy, pressure trend, simulated pressure fault/recovery and emergency ventilation policies.
- HIS infinite stochastic case intake, validated OR assignment, external case insertion and manual OR scheduling.
- Separate **HIS Scheduler AI** and **Energy AI Supervisor**.
- Fullscreen Command Center and responsive desktop/tablet/mobile layout.

### Added / strengthened in v9

- Advanced HVAC + Sterility panels are available in the **normal dashboard and Command Center**, so Command Center no longer hides the mature v8.1 controls.
- EnergyPlus room-design data is exposed in the room modal.
- Each floorplan space is linked to the EnergyPlus Space Summary where possible; the bundled v9 calibration currently matches **62/62 floorplan spaces**.
- Calibrated room design values include lighting W/m², plug/process W/m², zone-derived airflow allocation and proportional fan-design share.
- Energy/ROI uses the new **FULL_ANNUAL_TABULAR** calibration tier.
- Annual EUI, total energy, source energy, monthly electricity, monthly peaks, annual peak, electrical end uses, HVAC design and comfort/unmet-hours metadata come from the supplied EnergyPlus output.
- Whole-building ROI preserves system boundaries: B.E.A.M. does **not** subtract raw room-model kW directly from total building demand.

---

## 2. EnergyPlus calibration bundled with v9

Source file:

`beam-backend/data/openstudio_results/eplustbl.htm`

Imported baseline:

`beam-backend/data/energy_baseline.json`

The supplied EnergyPlus run reports a full **8760-hour non-leap annual simulation**. B.E.A.M. v9 imports the tabular result as:

- Calibration tier: `FULL_ANNUAL_TABULAR`
- Live reference resolution: `MONTHLY_MEAN`
- Total Site Energy: about **604.13 MWh/year**
- Site EUI: about **163.41 kWh/m²·year**
- Total Building Area: **3697 m²**
- Conditioned Area: **3554 m²**
- Annual electric peak: about **115.61 kW**
- Annual electrical end uses: Cooling, Interior Lighting, Interior Equipment, Fans, plus zero-valued reported categories
- Occupied heating/cooling setpoint unmet hours: **0 h / 0 h**

### Important: 8760-hour run != 8760-point hourly time series

`eplustbl.htm` proves that EnergyPlus simulated 8760 hours, but tabular output does **not** contain an hourly `Electricity:Facility` meter series. Therefore v9 does **not fabricate** an hourly curve.

For live facility comparison, v9 uses the calibrated **current-month mean kW**. If a true hourly facility trace is required later, import `eplusout.sql`; the existing SQL importer can upgrade the baseline to `HOURLY` while keeping the annual/tabular metadata.

---

## 3. Fresh local installation — Windows

Do not copy v9 over an older v8 folder. Extract v9 to a **new directory**.

### Prerequisites

Install:

- Python 3.11+ recommended
- Node.js 20+ recommended
- npm

### One-time setup

Run:

`INSTALL_BEAM.bat`

It will:

1. Create `.venv`
2. Install Python requirements
3. Run `npm install` in `beam-frontend`

### Start the dashboard

Run:

`START_BEAM.bat`

Expected development endpoints:

- Backend health: `http://127.0.0.1:8000/health`
- Backend baseline: `http://127.0.0.1:8000/energy-baseline`
- Frontend: `http://localhost:5173`

Expected `/health` fields:

- `version`: `9.0.0`
- `floorplan_spaces`: `62`
- `operating_rooms`: `8`
- `energy_baseline_calibrated`: `true`
- `energy_calibration_tier`: `FULL_ANNUAL_TABULAR`
- `energy_reference_resolution`: `MONTHLY_MEAN`

If an old browser bundle is still visible, stop older Vite/Uvicorn processes and perform **Ctrl+Shift+R**.

---

## 4. First-run acceptance checklist

After loading the page:

1. Header must show **v9** and `Live model backend`.
2. No red `VERSION MISMATCH` banner should appear.
3. Floorplan should show 62 spaces and 8 ORs.
4. Click an OR. A Room Control modal must open.
5. In the modal, verify:
   - telemetry cards;
   - EnergyPlus calibrated room-design block;
   - Room Manual Setup;
   - Apply Room Targets;
   - Release to Auto;
   - Manual Override / Room Operating Mode.
6. Open Command Center. It should enter browser fullscreen when allowed.
7. In Command Center, switch the right supervisory workspace between:
   - `HVAC + Sterility`
   - `HIS + Energy`
8. In `HVAC + Sterility`, confirm the complete advanced v8.1 control panels are present.
9. Open Energy & ROI and confirm the badge shows `FULL_ANNUAL_TABULAR` / `8760h` annual calibration.

---

## 5. Room control priority / safety arbitration

The modeled priority hierarchy is:

1. Physical / Sterility safety lock
2. Emergency ventilation policy
3. Room manual targets / room manual operating mode
4. Clinical / HIS demand
5. Energy AI optimization
6. Idle / setback optimization

A lower-priority command cannot silently defeat a higher-priority state. Examples:

- Active OR airflow is clamped to the model's clinical minimum.
- Shutdown/Minimum mode can be rejected when an OR is clinically active.
- A latched pressure fault remains authoritative over Energy AI and room manual controls.
- Energy AI is supervisory optimization, not a safety controller.

---

## 6. EnergyPlus room design mapping

The EnergyPlus report groups many spaces into thermal zones. It does not necessarily provide one VAV terminal flow value per individual polygon.

For a room linked to an EnergyPlus Space Summary, v9 uses:

- EnergyPlus space lighting power density
- EnergyPlus space plug/process power density
- EnergyPlus people density where available
- EnergyPlus zone design airflow allocated by the room's share of zone area
- EnergyPlus system fan design power allocated proportionally to calibrated room design airflow

The UI labels the airflow method as:

`ENERGYPLUS_ZONE_FLOW_AREA_ALLOCATION`

This is a transparent allocation method, **not a claim that EnergyPlus reported an independent room-level terminal flow**.

Unmatched/unavailable fields fall back to the documented B.E.A.M. digital-twin assumptions.

---

## 7. Re-importing EnergyPlus tabular results

If you later run a revised annual EnergyPlus simulation and receive a new `eplustbl.htm`, copy it somewhere convenient and run:

```bat
cd beam-backend
..\.venv\Scripts\python.exe tools\import_energyplus_tabular.py "C:\path\to\eplustbl.htm" --output data\energy_baseline.json
```

Or use:

`IMPORT_ENERGYPLUS_FULL.bat`

Then restart the backend.

Do **not** edit `energy_baseline.json` by hand unless you understand the schema and provenance implications.

---

## 8. Optional true hourly calibration with eplusout.sql

If the EnergyPlus simulation folder also contains `eplusout.sql`, use the SQL importer to obtain a real 8760/8784 hourly facility-electric trace.

The tabular baseline remains valuable for annual EUI/end-use/design information. SQL should be treated as an **additional time-series source**, not a reason to throw away tabular metadata.

Before using an SQL-based result for final reporting, verify that the requested EnergyPlus output meters were enabled in the simulation.

---

## 9. Energy & ROI interpretation

B.E.A.M. tracks two different model boundaries:

- **Calibrated facility reference** from OpenStudio/EnergyPlus
- **Controllable surgical-suite digital-twin response** from B.E.A.M.

The calibrated facility reference is not directly reduced by the room-model absolute kW delta. Instead, B.E.A.M. calculates a fractional control effect and applies it to the OpenStudio/EnergyPlus end-use envelope it can plausibly influence (e.g. cooling, interior lighting, fans), preserving unrelated loads such as clinical equipment.

This is a defensible simulation attribution method, but it is still **not Measurement & Verification (M&V)**. Real financial savings require calibrated utility/BMS measurements and an accepted M&V methodology.

---

## 10. Tests

Run:

`RUN_TESTS.bat`

Backend suite includes:

- floorplan / OSM cross-check
- HIS scheduling and safety rules
- manual room targets and modes
- pressure policies / emergency modes
- Energy AI arbitration
- EnergyPlus 8760 tabular importer
- annual EUI / peak / end-use validation
- room-level EnergyPlus design mapping
- frontend↔backend action contract

A separate real-WebSocket transport test is located at:

`beam-backend/test_transport_contract.py`

To run it manually, start a backend on port 8011 and execute that script.

---

## 11. HTTPS / online deployment

Production architecture is same-origin:

`https://your-domain/` → React frontend + FastAPI API + `wss://your-domain/ws`

This avoids mixed-content and cross-origin WebSocket issues.

The project includes:

- `Dockerfile`
- `render.yaml`
- `DEPLOY_HTTPS.md`

For a public demo, use a single instance unless you add shared persistence. Current HIS and live digital-twin state are in process memory; restarting the process resets the live session.

Do not expose the public demo as if it controlled a real hospital system.

---

## 12. Troubleshooting

### UI says VERSION MISMATCH

Check:

`http://127.0.0.1:8000/health`

It must report `9.0.0`. Then hard-refresh the browser.

### Room click does not open Room Control

Make sure both frontend and backend are v9. The floorplan uses a drag-vs-click pointer contract: a stationary click/tap selects the room; a dragged gesture pans the map.

### Advanced HVAC / Sterility appears missing

In normal dashboard it is below the floorplan/HIS row. In Command Center select **HVAC + Sterility** in the right supervisory workspace.

### `npm install` fails

Check network/proxy/firewall and then, in `beam-frontend`:

```bat
rmdir /s /q node_modules
npm cache verify
npm install
```

### Floorplan loads but backend is offline

Check port 8000, Python environment and firewall. Run `CHECK_BEAM.bat`.

### Energy page says monthly mean, not hourly

Expected for `eplustbl.htm`. The simulation ran 8760 hours, but the file is tabular rather than an hourly meter stream. Import `eplusout.sql` only if true hourly calibration is needed.

---

## 13. Project structure

```text
BEAM_v9_PRO_FINAL/
├─ beam-backend/
│  ├─ main.py
│  ├─ beam_state.py
│  ├─ energy_model.py
│  ├─ his_engine.py
│  ├─ floorplan_model.py
│  ├─ data/
│  │  ├─ floorplan.json
│  │  ├─ Hospital.osm
│  │  ├─ or_capabilities.json
│  │  ├─ energy_baseline.json
│  │  └─ openstudio_results/
│  │     ├─ report.html
│  │     └─ eplustbl.htm
│  └─ tools/
│     ├─ import_energyplus_tabular.py
│     ├─ import_openstudio_report.py
│     └─ import_energyplus_sql.py
├─ beam-frontend/
│  └─ src/
│     ├─ App.tsx
│     └─ index.css
├─ Dockerfile
├─ render.yaml
├─ INSTALL_BEAM.bat
├─ START_BEAM.bat
├─ RUN_TESTS.bat
└─ README.md
```

---

## 14. Provenance rule for v9

The UI intentionally distinguishes:

- **EnergyPlus calibrated data**
- **OpenStudio/FloorSpace geometry**
- **B.E.A.M. configuration** (for example OR specialty capability)
- **B.E.A.M. digital-twin modeled telemetry**
- **Live-session counters / estimates**

Do not relabel B.E.A.M. configuration or digital-twin estimates as values directly measured or reported by EnergyPlus.
