from __future__ import annotations

import argparse
import calendar
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

KWH_PER_KBTU = 0.29307107
M2_PER_FT2 = 0.09290304
KWH_M2_PER_KBTU_FT2 = KWH_PER_KBTU / M2_PER_FT2
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _number(text: str) -> Optional[float]:
    # OpenStudio report cells commonly append unit exponents such as ft^2.
    # Parse only the first numeric token so the unit exponent is never folded
    # into the value (e.g. "39,794 ft^2" must become 39794, not 397942).
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _rows(soup: BeautifulSoup, table_id: str) -> List[List[str]]:
    wrap = soup.find(id=table_id)
    if not wrap:
        return []
    table = wrap.find("table")
    if not table:
        return []
    result: List[List[str]] = []
    for tr in table.find_all("tr"):
        cells = [" ".join(c.get_text(" ", strip=True).split()) for c in tr.find_all(["th", "td"])]
        if cells:
            result.append(cells)
    return result


def _key_value(rows: List[List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in rows[1:]:
        if len(row) >= 2:
            out[row[0]] = row[1]
    return out


def _monthly_table(rows: List[List[str]]) -> Dict[str, List[float]]:
    result: Dict[str, List[float]] = {}
    for row in rows[1:]:
        if not row:
            continue
        label = row[0]
        vals: List[float] = []
        for cell in row[1:13]:
            value = _number(cell)
            vals.append(float(value or 0.0))
        if vals:
            result[label] = vals
    return result


def _end_use(rows: List[List[str]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in rows[1:]:
        if len(row) >= 2:
            value = _number(row[1])
            if value is not None:
                out[row[0]] = float(value)
    return out


def _table_object_description(rows: List[List[str]]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    headers = rows[0]
    out: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        padded = row + [""] * max(0, len(headers) - len(row))
        out.append({headers[i] or f"column_{i}": padded[i] for i in range(min(len(headers), len(padded)))})
    return out


def _hvac_compact(rows: List[List[str]]) -> Dict[str, Any]:
    data = _table_object_description(rows)
    compact: Dict[str, Any] = {}
    for row in data:
        obj = str(row.get("Object", ""))
        desc = str(row.get("Description", ""))
        value = row.get("Value", "")
        if obj == "Coil:Cooling:DX:TwoSpeed" and desc == "Cooling Capacity": compact["cooling_capacity"] = value
        elif obj == "Coil:Cooling:DX:TwoSpeed" and desc == "Rated High Speed COP": compact["cooling_cop"] = value
        elif obj == "Fan:VariableVolume" and desc == "Air Flow Rate": compact["fan_design_airflow"] = value
        elif obj == "Fan:VariableVolume" and desc == "Fan Efficiency": compact["fan_efficiency"] = value
        elif obj == "Fan:VariableVolume" and desc == "Pressure Rise": compact["fan_pressure_rise"] = value
        elif obj == "Fan:VariableVolume" and desc == "Motor Efficiency": compact["fan_motor_efficiency"] = value
        elif obj == "Thermal Zones" and desc == "Total Floor Area": compact["served_floor_area"] = value
        elif obj == "HVAC Operation Schedule": compact["operation_schedule"] = value
        elif obj == "Economizer Setting": compact["economizer"] = value
        elif obj == "Demand Controlled Ventilation Status": compact["demand_controlled_ventilation"] = value
    return compact


def _outdoor_air_compact(rows: List[List[str]]) -> Dict[str, Any]:
    if not rows:
        return {}
    headers = rows[0]
    result: Dict[str, Any] = {}
    for row in rows[1:]:
        if not row:
            continue
        zone = row[0]
        if zone.upper() not in {"OPERATION ROOM", "CORRIDOR 1", "GENERAL HOSPITAL"}:
            continue
        padded = row + [""] * max(0, len(headers) - len(row))
        result[zone] = {headers[i]: padded[i] for i in range(1, min(len(headers), len(padded)))}
    return result


def parse_report(report_path: Path) -> Dict[str, Any]:
    soup = BeautifulSoup(report_path.read_text(encoding="utf-8", errors="ignore"), "html.parser")

    building = _key_value(_rows(soup, "table_0"))
    weather = _key_value(_rows(soup, "table_1"))
    unmet = _key_value(_rows(soup, "table_3"))
    end_use_kbtu = _end_use(_rows(soup, "table_5"))
    end_use_kwh = _end_use(_rows(soup, "table_7"))
    monthly_energy = _monthly_table(_rows(soup, "table_9"))
    monthly_peak = _monthly_table(_rows(soup, "table_10"))
    monthly_loads = _monthly_table(_rows(soup, "table_25"))
    site_source_rows = _rows(soup, "table_33")
    source_factors = _key_value(_rows(soup, "table_34"))
    zone_summary = _rows(soup, "table_28")
    hvac = _hvac_compact(_rows(soup, "table_30"))
    outdoor_air = _outdoor_air_compact(_rows(soup, "table_32"))

    total_site_kbtu = _number(building.get("Total Site Energy", ""))
    total_area_ft2 = _number(building.get("Total Building Area", ""))
    site_eui_kbtu_ft2 = _number(building.get("Total Site EUI", ""))

    conditioned_area_ft2: Optional[float] = None
    if zone_summary:
        for row in zone_summary[1:]:
            if row and row[0].strip().lower() == "conditioned total" and len(row) > 1:
                conditioned_area_ft2 = _number(row[1])
                break

    source_energy_kbtu: Optional[float] = None
    source_eui_kbtu_ft2: Optional[float] = None
    conditioned_site_eui_kbtu_ft2: Optional[float] = None
    conditioned_source_eui_kbtu_ft2: Optional[float] = None
    for row in site_source_rows[1:]:
        if len(row) < 4:
            continue
        if row[0] == "Total Site Energy":
            conditioned_site_eui_kbtu_ft2 = _number(row[3])
        elif row[0] == "Total Source Energy":
            source_energy_kbtu = _number(row[1])
            source_eui_kbtu_ft2 = _number(row[2])
            conditioned_source_eui_kbtu_ft2 = _number(row[3])

    monthly_total = monthly_energy.get("Total", [0.0] * 12)
    annual_electricity = float(sum(monthly_total)) if any(monthly_total) else None
    monthly_total_peak = monthly_peak.get("Total", [0.0] * 12)
    annual_peak = max(monthly_total_peak) if any(monthly_total_peak) else None

    monthly_mean_kw: List[float] = []
    for month_idx, kwh in enumerate(monthly_total, start=1):
        hours = calendar.monthrange(2023, month_idx)[1] * 24  # non-leap TMY calendar
        monthly_mean_kw.append(float(kwh) / hours if hours else 0.0)

    total_site_kwh = total_site_kbtu * KWH_PER_KBTU if total_site_kbtu is not None else annual_electricity
    floor_area_m2 = total_area_ft2 * M2_PER_FT2 if total_area_ft2 is not None else None
    conditioned_area_m2 = conditioned_area_ft2 * M2_PER_FT2 if conditioned_area_ft2 is not None else None
    site_eui_metric = site_eui_kbtu_ft2 * KWH_M2_PER_KBTU_FT2 if site_eui_kbtu_ft2 is not None else (total_site_kwh / floor_area_m2 if total_site_kwh and floor_area_m2 else None)

    monthly_cooling = monthly_loads.get("Cooling Load (MBtu)", [0.0] * 12)
    monthly_outdoor_f = monthly_loads.get("Average Outdoor Air Dry Bulb (F)", [0.0] * 12)
    monthly_outdoor_c = [(v - 32.0) * 5.0 / 9.0 for v in monthly_outdoor_f]

    weather_file = weather.get("Weather File")
    lat = _number(weather.get("Latitude", ""))
    lon = _number(weather.get("Longitude", ""))
    elevation_ft = _number(weather.get("Elevation", ""))
    tz = _number(weather.get("Time Zone", ""))

    total_unmet = 0.0
    unmet_parsed: Dict[str, float] = {}
    for k, v in unmet.items():
        n = float(_number(v) or 0.0)
        unmet_parsed[k] = n
        total_unmet += n

    quality_flags: List[Dict[str, str]] = []
    quality_flags.append({"severity": "PASS" if total_unmet == 0 else "CHECK", "message": f"Reported total unmet setpoint hours: {total_unmet:.1f} h"})
    quality_flags.append({"severity": "INFO", "message": "report.html contains annual/monthly results but no 8760/8784 hourly facility electricity series."})
    if str(building.get("OpenStudio Standards Building Type", "")).strip().lower() in {"", "n/a"}:
        quality_flags.append({"severity": "CHECK", "message": "OpenStudio Standards Building Type is n/a; interpret benchmark comparisons cautiously."})
    for row in zone_summary[1:]:
        if row and row[0].strip().upper() == "PREP ROOM" and len(row) > 2 and row[2].strip().lower() == "no":
            quality_flags.append({"severity": "CHECK", "message": "PREP ROOM is reported as unconditioned in the OpenStudio Zone Summary."})
            break

    baseline = {
        "schema_version": "2.0",
        "calibrated": True,
        "calibration_tier": "ANNUAL_MONTHLY",
        "source": "OPENSTUDIO_RESULTS_HTML_ANNUAL_MONTHLY",
        "source_file": report_path.name,
        "floor_area_m2": round(floor_area_m2, 3) if floor_area_m2 else None,
        "conditioned_floor_area_m2": round(conditioned_area_m2, 3) if conditioned_area_m2 else None,
        "annual_site_energy_kwh": round(total_site_kwh, 3) if total_site_kwh else None,
        "annual_electricity_kwh": round(annual_electricity, 3) if annual_electricity else None,
        "site_eui_kwh_m2_year": round(site_eui_metric, 3) if site_eui_metric else None,
        "source_eui_kwh_m2_year": round(source_eui_kbtu_ft2 * KWH_M2_PER_KBTU_FT2, 3) if source_eui_kbtu_ft2 else None,
        "conditioned_site_eui_kwh_m2_year": round(conditioned_site_eui_kbtu_ft2 * KWH_M2_PER_KBTU_FT2, 3) if conditioned_site_eui_kbtu_ft2 else None,
        "conditioned_source_eui_kwh_m2_year": round(conditioned_source_eui_kbtu_ft2 * KWH_M2_PER_KBTU_FT2, 3) if conditioned_source_eui_kbtu_ft2 else None,
        "annual_source_energy_kwh": round(source_energy_kbtu * KWH_PER_KBTU, 3) if source_energy_kbtu else None,
        "annual_peak_electric_kw": round(annual_peak, 3) if annual_peak is not None else None,
        "monthly_electricity_kwh": [round(v, 3) for v in monthly_total],
        "monthly_mean_electric_kw": [round(v, 4) for v in monthly_mean_kw],
        "monthly_peak_electric_kw": [round(v, 3) for v in monthly_total_peak],
        "monthly_cooling_load_mbtu": [round(v, 4) for v in monthly_cooling],
        "monthly_outdoor_temp_c": [round(v, 3) for v in monthly_outdoor_c],
        "end_uses_electricity_kwh": {k: round(v, 3) for k, v in end_use_kwh.items()},
        "end_uses_site_kbtu": {k: round(v, 3) for k, v in end_use_kbtu.items()},
        "hourly_electric_kw": None,
        "metadata": {
            "building_name": building.get("Building Name"),
            "openstudio_building_type": building.get("OpenStudio Standards Building Type"),
            "weather_file": weather_file,
            "latitude": lat,
            "longitude": lon,
            "elevation_m": round(elevation_ft * 0.3048, 3) if elevation_ft is not None else None,
            "timezone": tz,
            "unmet_hours": unmet_parsed,
            "total_unmet_hours": round(total_unmet, 3),
            "source_conversion_factors": {k: float(_number(v) or 0.0) for k, v in source_factors.items()},
            "hvac_summary": hvac,
            "outdoor_air_summary": outdoor_air,
            "quality_flags": quality_flags,
            "report_rounding_note": "Annual electricity from monthly table may differ slightly from site-energy conversion due to report rounding.",
            "hourly_profile_available": False,
            "hourly_profile_requirement": "Import eplusout.sql for 8760/8784 hourly facility electricity reference.",
        },
    }
    return baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OpenStudio Results report.html into B.E.A.M. energy_baseline.json")
    parser.add_argument("report", type=Path, help="Path to OpenStudio report.html")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "energy_baseline.json")
    args = parser.parse_args()
    baseline = parse_report(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Imported {args.report} -> {args.output}")
    print(f"Tier: {baseline['calibration_tier']}")
    print(f"Annual site energy: {baseline['annual_site_energy_kwh']:.1f} kWh")
    print(f"Site EUI: {baseline['site_eui_kwh_m2_year']:.2f} kWh/m²·yr")
    print(f"Annual peak (monthly reported max): {baseline['annual_peak_electric_kw']:.2f} kW")
    print("Hourly profile: not present in report.html; use eplusout.sql for hourly calibration.")


if __name__ == "__main__":
    main()
