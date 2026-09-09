# BEAM v11.1 — Data and Modeling Assumptions

## Prepared English demo

Only the supplied floorplan is required as a real input for the demo. Patient/staff/device/case records, probabilities, outcomes, learned-trait seeds, energy history and financial inputs are explicitly synthetic. Geometry/category defaults support operation without optional EnergyPlus references. Original imported model assets remain bundled for the legacy engineering views.

Clinical models are artificial teaching formulas with synthetic benchmark scores and no clinical approval. SIMULATION and CONNECTED ledgers, model eligibility and workspaces remain separate. See `V11_GUIDE_EN.md` for the prepared data and `VALIDATION.md` for the floorplan-only regression.

## Original imported reference sources

- Floorplan geometry: OpenStudio/FloorSpace JSON
- OpenStudio model cross-check: `Hospital.osm`
- Energy baseline/design: EnergyPlus `eplustbl.htm`, full annual 8760-hour tabular run
- OR specialty capabilities: B.E.A.M. configuration file, **not** OpenStudio/EnergyPlus clinical metadata

## Calibrated vs modeled

**EnergyPlus calibrated:** annual/site/source energy, EUI, monthly electricity, monthly peaks, annual peak, electrical end uses, reported space lighting/plug/people design data, zone/system airflow design metadata, system fan/cooling design metadata, occupied setpoint unmet hours.

**B.E.A.M. modeled:** live room temperature/RH response, occupancy/case state, real-time room power estimate, digital-twin pressure response, Energy AI counterfactual optimization, live session savings.

**Derived allocation:** room design airflow when EnergyPlus provides zone airflow but not one room terminal value. Allocation is proportional to floor area within the EnergyPlus zone and is labeled accordingly.

## ROI boundary

B.E.A.M. applies its modeled control fraction only to control-eligible EnergyPlus end uses. It does not claim that clinical plug/process equipment savings are caused by HVAC control.

ROI and carbon numbers remain simulation estimates until verified against real utility/BMS measurements and an accepted M&V procedure.

## Safety

This software is a prototype. Pressure locks, emergency modes, positive-pressure targets and clinical airflow clamps are model guardrails, not certified hospital safety limits or real actuator commands.

The UI must not be used to imply regulatory compliance, infection-control certification, or medical-device status.
