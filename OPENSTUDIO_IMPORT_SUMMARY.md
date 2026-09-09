# EnergyPlus / OpenStudio Import Summary — v9

Source: `beam-backend/data/openstudio_results/eplustbl.htm`

Importer: `beam-backend/tools/import_energyplus_tabular.py`

Output: `beam-backend/data/energy_baseline.json`

## Imported facility metrics

| Metric | Value |
|---|---:|
| Simulation duration | 8760 h |
| Total site energy | 604,133.3 kWh/y |
| Total source energy | 1,913,291.7 kWh/y |
| Site EUI | 163.4111 kWh/m²-y |
| Source EUI | 517.525 kWh/m²-y |
| Total building area | 3697 m² |
| Conditioned building area | 3554 m² |
| Annual electric peak | 115.6125 kW |
| Annual peak timestamp | 12-JUL-14:09 |
| Occupied heating unmet | 0.0 h |
| Occupied cooling unmet | 0.0 h |

## Annual electrical end uses

| End use | kWh/y |
|---|---:|
| Cooling | 97,897.2 |
| Interior Lighting | 159,119.4 |
| Interior Equipment | 345,411.1 |
| Fans | 1,705.6 |

The sum is consistent with the annual facility electricity within output rounding.

## HVAC design fields used by the digital twin

- Packaged rooftop VAV with reheat
- Design supply airflow: 2.73 m³/s
- Cooling coil design capacity: 67.85445 kW
- Variable fan design airflow: 2.73 m³/s
- Variable fan design power: 2.26013 kW
- System cooling outdoor airflow: 1.0114 m³/s

## Room design mapping

EnergyPlus reports Space Summary values and zone airflow. B.E.A.M. matches source-space names after accent/mojibake normalization. Zone airflow is allocated to member spaces by area, and the UI explicitly exposes the method as `ENERGYPLUS_ZONE_FLOW_AREA_ALLOCATION`.

This is not equivalent to an independent EnergyPlus terminal-flow result for every room.

## Time-series limitation

The report represents an annual 8760-hour simulation but does not carry an hourly `Electricity:Facility` meter array. B.E.A.M. therefore uses monthly mean kW as its live calibrated anchor. `eplusout.sql` can be imported later for true hourly resolution.
