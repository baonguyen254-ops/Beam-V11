from pathlib import Path
import importlib.util
import math

ROOT = Path(__file__).resolve().parent
TOOL = ROOT / "tools" / "import_openstudio_report.py"
REPORT = ROOT / "data" / "openstudio_results" / "report.html"

spec = importlib.util.spec_from_file_location("openstudio_report_importer", TOOL)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_report_html_import_matches_key_openstudio_results():
    baseline = module.parse_report(REPORT)
    assert baseline["calibration_tier"] == "ANNUAL_MONTHLY"
    assert math.isclose(baseline["annual_site_energy_kwh"], 604133.187, rel_tol=1e-6)
    assert math.isclose(baseline["annual_electricity_kwh"], 604134.19, rel_tol=1e-6)
    assert math.isclose(baseline["floor_area_m2"], 3696.984, rel_tol=1e-6)
    assert math.isclose(baseline["site_eui_kwh_m2_year"], 163.408, rel_tol=1e-6)
    assert baseline["annual_peak_electric_kw"] == 115.61
    assert baseline["metadata"]["total_unmet_hours"] == 0.0
    assert len(baseline["monthly_electricity_kwh"]) == 12
    assert len(baseline["monthly_peak_electric_kw"]) == 12


def test_report_html_import_keeps_hourly_calibration_explicitly_unavailable():
    baseline = module.parse_report(REPORT)
    assert baseline["hourly_electric_kw"] is None
    assert baseline["metadata"]["hourly_profile_available"] is False
    assert "eplusout.sql" in baseline["metadata"]["hourly_profile_requirement"]
