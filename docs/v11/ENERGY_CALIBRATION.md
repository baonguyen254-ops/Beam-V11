> Tài liệu gốc v9 được giữ để đối chiếu. Với hành vi v10, dùng [hướng dẫn v10](V10_GUIDE_VI.md) và [kết quả kiểm thử hiện tại](VALIDATION.md).

# B.E.A.M. v9 — Energy Calibration

## Current bundled calibration

Source: EnergyPlus `eplustbl.htm`, generated from a **full 8760-hour annual run**.

Tier: `FULL_ANNUAL_TABULAR`

Reference resolution used during live dashboard operation: `MONTHLY_MEAN`.

Why those are different: the annual tabular report confirms and summarizes all 8760 simulated hours, but it does not contain a 8760-element facility meter time series.

## Imported metrics

- Annual Site Energy: ~604.133 MWh
- Annual Source Energy: ~1,913.292 MWh
- Site EUI: 163.411 kWh/m²-y
- Source EUI: 517.525 kWh/m²-y
- Total area: 3697 m²
- Conditioned area: 3554 m²
- Annual electric peak: 115.6125 kW @ 12-JUL-14:09
- 12 monthly facility-electric totals
- 12 monthly electric peaks + timestamps
- Annual electrical end-use breakdown
- Peak end-use breakdown
- EnergyPlus space, zone and HVAC design metadata
- Occupied heating/cooling unmet hours

## Live ROI boundary

B.E.A.M. calculates a standard-control vs optimized-control fractional response inside the surgical-suite digital twin. That fraction is applied only to the EnergyPlus annual control-eligible end-use envelope. Raw room-model kW is not subtracted directly from whole-building facility demand.

The method is still a simulation attribution model, not formal M&V.

## Optional hourly upgrade

If you later provide `eplusout.sql` with an hourly `Electricity:Facility` meter, import it with `tools/import_energyplus_sql.py`. The desired end state is to preserve the v9 tabular/design metadata and add the hourly facility trace.

Do not synthesize an hourly profile from annual/monthly tables.
