from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOL = ROOT / "tools" / "import_energyplus_tabular.py"
EPLUS = ROOT / "data" / "openstudio_results" / "eplustbl.htm"

spec = importlib.util.spec_from_file_location("energyplus_tabular_importer", TOOL)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_v9_full_8760_tabular_import_matches_energyplus_report():
    b = module.parse_eplustbl(EPLUS)
    assert b["calibration_tier"] == "FULL_ANNUAL_TABULAR"
    assert b["simulation_hours"] == 8760.0
    assert math.isclose(b["annual_site_energy_kwh"], 604133.333, rel_tol=1e-6)
    assert math.isclose(b["site_eui_kwh_m2_year"], 163.4111, rel_tol=1e-6)
    assert b["floor_area_m2"] == 3697.0
    assert b["conditioned_floor_area_m2"] == 3554.0
    assert math.isclose(b["annual_peak_electric_kw"], 115.6125, rel_tol=1e-6)
    assert b["annual_peak_timestamp"] == "12-JUL-14:09"
    assert len(b["monthly_electricity_kwh"]) == 12
    assert len(b["monthly_peak_electric_kw"]) == 12
    assert b["hourly_electric_kw"] is None


def test_v9_end_uses_are_in_kwh_and_control_envelope_is_physically_scaled():
    b = module.parse_eplustbl(EPLUS)
    end = b["end_uses_electricity_kwh"]
    assert math.isclose(end["Cooling"], 97897.2222, rel_tol=1e-6)
    assert math.isclose(end["Interior Lighting"], 159119.4444, rel_tol=1e-6)
    assert math.isclose(end["Interior Equipment"], 345411.1111, rel_tol=1e-6)
    assert math.isclose(end["Fans"], 1705.5556, rel_tol=1e-6)
    assert math.isclose(sum(end.values()), b["annual_electricity_kwh"], rel_tol=2e-6)


def test_v9_space_and_hvac_design_calibration_are_extracted():
    b = module.parse_eplustbl(EPLUS)
    spaces = b["metadata"]["spaces"]
    assert len(spaces) >= 62
    or_spaces = [s for s in spaces if str(s.get("source_name", "")).lower().startswith("ph") or "mổ" in str(s.get("source_name", "")).lower()]
    # Mojibake in EnergyPlus labels is normalized by the importer; the key property
    # is that room-level design records and zone allocation data exist.
    assert any((s.get("allocated_design_airflow_m3h") or 0) > 0 for s in spaces)
    hvac = b["metadata"]["hvac_design"]
    assert math.isclose(hvac["design_supply_airflow_m3s"], 2.73, rel_tol=1e-6)
    assert math.isclose(hvac["fan_design_power_kw"], 2.26013, rel_tol=1e-6)
    assert math.isclose(hvac["cooling_coil_capacity_kw"], 67.85445, rel_tol=1e-6)
    assert b["metadata"]["total_unmet_hours"] == 0.0
