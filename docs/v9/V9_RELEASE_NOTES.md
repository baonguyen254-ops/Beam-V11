# B.E.A.M. v9 PRO FINAL — Release Notes

## Consolidation goal

v9 is a controlled merge, not a feature rewrite:

- **v8.1 operational lineage retained**: advanced HVAC/lighting control, Sterility & ΔP interlock, emergency ventilation policies, room click-through telemetry and manual targets/modes, HIS, Command Center, Energy AI, theme system.
- **v8.2 calibration lineage retained**: OpenStudio/EnergyPlus facility baseline, end-use-scaled ROI, monthly facility reference, analytics.
- **v9 calibration upgraded**: EnergyPlus `eplustbl.htm` from a full 8760-hour annual run replaces the older report-only annual baseline and adds design/space/HVAC metadata.

## EnergyPlus v9 baseline

- Calibration tier: `FULL_ANNUAL_TABULAR`
- Simulation duration: 8760 h
- Site energy: 604.133 MWh/y
- Site EUI: 163.411 kWh/m²-y
- Total floor area: 3697 m²
- Conditioned floor area: 3554 m²
- Annual electric peak: 115.6125 kW at `12-JUL-14:09`
- 12 monthly energy values + 12 monthly facility peaks
- Annual electrical end uses and peak end-use breakdown
- HVAC design metadata and EnergyPlus Space Summary mapping
- 62/62 floorplan spaces linked to EnergyPlus space records

## Operational UI restoration / hardening

- Advanced `Clinical HVAC & Lighting Control Plane` retained intact.
- Advanced `Sterility, Pressure & Safety Interlock` retained intact.
- Both are now exposed inside **Command Center → HVAC + Sterility**, eliminating the appearance that Command Center removed those controls.
- Normal dashboard gives HVAC and Sterility a full 6/6 row; Energy/AI move to a separate row so mature controls are not squeezed by analytics.
- Room modal now adds EnergyPlus calibrated design provenance without removing manual room control.

## Baseline integrity

`eplustbl.htm` is an annual tabular result generated from 8760 simulated hours. It is not an hourly meter stream. v9 therefore remains `MONTHLY_MEAN` for the live facility reference until an optional `eplusout.sql` hourly profile is imported.
