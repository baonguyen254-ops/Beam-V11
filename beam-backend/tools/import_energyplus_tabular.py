from __future__ import annotations

import argparse
import calendar
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

MONTHS_FULL = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _num(value: str | None) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _norm(text: str) -> str:
    # EnergyPlus HTML may contain legacy mojibake such as TH° GIãN / D°ỡNG.
    # Normalize those labels into an accent-insensitive alphanumeric key so they
    # can be matched back to the authoritative FloorSpace source names.
    text = str(text).replace("°", "u").replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _rows(table) -> List[List[str]]:
    result: List[List[str]] = []
    for tr in table.find_all("tr"):
        cells = [" ".join(c.get_text(" ", strip=True).split()) for c in tr.find_all(["th", "td"])]
        if cells:
            result.append(cells)
    return result


def _title(table) -> str:
    prev = table.find_previous("b")
    return " ".join(prev.get_text(" ", strip=True).split()) if prev else ""


def _table_map(soup: BeautifulSoup) -> Dict[str, List[List[str]]]:
    result: Dict[str, List[List[str]]] = {}
    for table in soup.find_all("table"):
        title = _title(table)
        if not title:
            continue
        rows = _rows(table)
        # Keep the first occurrence for uniquely named tables. Custom Monthly Report
        # is intentionally collected separately below because it appears multiple times.
        result.setdefault(title, rows)
    return result


def _all_tables(soup: BeautifulSoup, title: str) -> List[List[List[str]]]:
    out: List[List[List[str]]] = []
    for table in soup.find_all("table"):
        if _title(table) == title:
            out.append(_rows(table))
    return out


def _records(rows: List[List[str]]) -> List[Dict[str, str]]:
    if not rows:
        return []
    headers = rows[0]
    out: List[Dict[str, str]] = []
    for row in rows[1:]:
        if not any(str(x).strip() for x in row):
            continue
        padded = row + [""] * max(0, len(headers) - len(row))
        rec: Dict[str, str] = {"name": padded[0] if padded else ""}
        for i, header in enumerate(headers[1:], start=1):
            key = header or f"column_{i}"
            rec[key] = padded[i] if i < len(padded) else ""
        out.append(rec)
    return out


def _kv(rows: List[List[str]]) -> Dict[str, str]:
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2 and row[0]}


def _end_use_energy(rows: List[List[str]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        label = row[0].strip()
        if not label or label == "Total End Uses":
            continue
        value = _num(row[1])
        if value is not None:
            out[label] = value / 0.0036  # GJ -> kWh
    return out


def _end_use_peak(rows: List[List[str]]) -> Tuple[Optional[str], Dict[str, float], Optional[float]]:
    peak_time: Optional[str] = None
    peaks: Dict[str, float] = {}
    total_kw: Optional[float] = None
    for row in rows[1:]:
        if len(row) < 2:
            continue
        label = row[0].strip()
        if label == "Time of Peak":
            peak_time = row[1] or None
            continue
        value = _num(row[1])
        if value is None:
            continue
        if label == "Total End Uses":
            total_kw = value / 1000.0
        elif label:
            peaks[label] = value / 1000.0
    return peak_time, peaks, total_kw


def _monthly_reports(soup: BeautifulSoup) -> Tuple[List[float], List[float], List[str], Dict[str, List[float]], Dict[str, List[float]]]:
    monthly_energy_kwh = [0.0] * 12
    monthly_peak_kw = [0.0] * 12
    monthly_peak_ts = [""] * 12
    monthly_end_uses: Dict[str, List[float]] = {}
    monthly_peak_end_uses: Dict[str, List[float]] = {}

    for rows in _all_tables(soup, "Custom Monthly Report"):
        if not rows:
            continue
        headers = rows[0]
        h_upper = [h.upper() for h in headers]
        is_energy = any("INTERIORLIGHTS:ELECTRICITY [J]" in h for h in h_upper)
        is_peak = any("ELECTRICITY:FACILITY {MAXIMUM} [W]" in h for h in h_upper)
        if not (is_energy or is_peak):
            continue
        for row in rows[1:13]:
            if not row or row[0] not in MONTHS_FULL:
                continue
            idx = MONTHS_FULL.index(row[0])
            padded = row + [""] * max(0, len(headers) - len(row))
            if is_energy:
                total = 0.0
                for j, header in enumerate(headers[1:], start=1):
                    if not header or "ELECTRICITY" not in header.upper() or "[J]" not in header.upper():
                        continue
                    value = _num(padded[j]) or 0.0
                    kwh = value / 3.6e6
                    label = header.split(":", 1)[0].title().replace("Interiorequipment", "Interior Equipment").replace("Interiorlights", "Interior Lighting").replace("HeatRejection", "Heat Rejection").replace("WaterSystems", "Water Systems")
                    monthly_end_uses.setdefault(label, [0.0] * 12)[idx] += kwh
                    total += kwh
                monthly_energy_kwh[idx] = total
            elif is_peak:
                for j, header in enumerate(headers[1:], start=1):
                    up = header.upper()
                    if "ELECTRICITY:FACILITY {MAXIMUM} [W]" in up:
                        monthly_peak_kw[idx] = (_num(padded[j]) or 0.0) / 1000.0
                    elif "ELECTRICITY:FACILITY {TIMESTAMP}" in up:
                        monthly_peak_ts[idx] = padded[j]
                    elif "ELECTRICITY" in up and "{AT MAX/MIN} [W]" in up:
                        value = (_num(padded[j]) or 0.0) / 1000.0
                        label = header.split(":", 1)[0].title().replace("Interiorequipment", "Interior Equipment").replace("Interiorlights", "Interior Lighting").replace("HeatRejection", "Heat Rejection").replace("WaterSystems", "Water Systems")
                        monthly_peak_end_uses.setdefault(label, [0.0] * 12)[idx] = value
    return monthly_energy_kwh, monthly_peak_kw, monthly_peak_ts, monthly_end_uses, monthly_peak_end_uses


def _space_profiles(space_rows: List[List[str]], zone_rows: List[List[str]], vent_rows: List[List[str]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    zones_raw = _records(zone_rows)
    zone_info: Dict[str, Dict[str, Any]] = {}
    for rec in zones_raw:
        name = rec.get("name", "")
        zone_info[_norm(name)] = {
            "name": name,
            "area_m2": _num(rec.get("Area [m2]")),
            "conditioned": str(rec.get("Conditioned (Y/N)", "")).strip().lower() == "yes",
            "volume_m3": _num(rec.get("Volume [m3]")),
            "lighting_w_m2": _num(rec.get("Lighting [W/m2]")),
            "people_m2_per_person": _num(rec.get("People [m2 per person]")),
            "plug_w_m2": _num(rec.get("Plug and Process [W/m2]")),
        }

    vent_info: Dict[str, Dict[str, Any]] = {}
    for rec in _records(vent_rows):
        name = rec.get("name", "")
        vent_info[_norm(name)] = {
            "zone_primary_airflow_m3s": _num(rec.get("Zone Primary Airflow - Vpz [m3/s]")),
            "zone_discharge_airflow_m3s": _num(rec.get("Zone Discharge Airflow - Vdz [m3/s]")),
            "zone_min_primary_airflow_m3s": _num(rec.get("Minimum Zone Primary Airflow - Vpz-min [m3/s]")),
            "zone_outdoor_airflow_m3s": _num(rec.get("Zone Outdoor Airflow Cooling - Voz-clg [m3/s]")),
            "ventilation_efficiency": _num(rec.get("Zone Ventilation Efficiency - Evz")),
        }

    spaces: List[Dict[str, Any]] = []
    for rec in _records(space_rows):
        name = rec.get("name", "")
        zone_name = rec.get("Zone Name", "")
        zone = zone_info.get(_norm(zone_name), {})
        vent = vent_info.get(_norm(zone_name), {})
        area = _num(rec.get("Area [m2]")) or 0.0
        zone_area = float(zone.get("area_m2") or 0.0)
        zone_flow = vent.get("zone_primary_airflow_m3s")
        zone_min = vent.get("zone_min_primary_airflow_m3s")
        allocated_flow = None
        allocated_min = None
        if zone_flow is not None and zone_area > 0 and area > 0:
            allocated_flow = float(zone_flow) * (area / zone_area) * 3600.0
        if zone_min is not None and zone_area > 0 and area > 0:
            allocated_min = float(zone_min) * (area / zone_area) * 3600.0
        spaces.append({
            "source_name": name,
            "normalized_source_name": _norm(name),
            "area_m2": area,
            "conditioned": str(rec.get("Conditioned (Y/N)", "")).strip().lower() == "yes",
            "zone_name": zone_name,
            "space_type": rec.get("Space Type", ""),
            "lighting_w_m2": _num(rec.get("Lighting [W/m2]")),
            "people_m2_per_person": _num(rec.get("People [m2 per person]")),
            "plug_w_m2": _num(rec.get("Plug and Process [W/m2]")),
            "zone_area_m2": zone_area or None,
            "zone_design_airflow_m3s": zone_flow,
            "zone_min_airflow_m3s": zone_min,
            "allocated_design_airflow_m3h": allocated_flow,
            "allocated_min_airflow_m3h": allocated_min,
            "calibration_method": "ENERGYPLUS_ZONE_FLOW_AREA_ALLOCATION" if allocated_flow is not None else "NO_ZONE_FLOW_AVAILABLE",
        })
    return spaces, list(zone_info.values())


def parse_eplustbl(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")
    table_map = _table_map(soup)

    site_source = table_map.get("Site and Source Energy", [])
    area_rows = table_map.get("Building Area", [])
    end_uses = table_map.get("End Uses", [])
    # The first End Uses table is annual energy. The second is annual peak; locate it by header units.
    end_use_tables = [rows for rows in (_rows(t) for t in soup.find_all("table") if _title(t) == "End Uses") if rows]
    annual_energy_rows = next((r for r in end_use_tables if r and any("Electricity [GJ]" == h for h in r[0])), [])
    peak_rows = next((r for r in end_use_tables if r and any("Electricity [W]" == h for h in r[0])), [])

    general = _kv(table_map.get("General", []))
    comfort = _kv(table_map.get("Comfort and Setpoint Not Met Summary", []))
    timestep = _records(table_map.get("Timesteps per Hour", []))
    zone_rows = table_map.get("Zone Summary", [])
    space_rows = table_map.get("Space Summary", [])
    vent_cooling = table_map.get("Zone Ventilation Calculations for Cooling Design", [])
    spaces, zones = _space_profiles(space_rows, zone_rows, vent_cooling)

    annual_site_gj = annual_source_gj = site_eui_mj_m2 = conditioned_site_eui_mj_m2 = source_eui_mj_m2 = conditioned_source_eui_mj_m2 = None
    for row in site_source[1:]:
        if len(row) < 4:
            continue
        if row[0] == "Total Site Energy":
            annual_site_gj = _num(row[1]); site_eui_mj_m2 = _num(row[2]); conditioned_site_eui_mj_m2 = _num(row[3])
        elif row[0] == "Total Source Energy":
            annual_source_gj = _num(row[1]); source_eui_mj_m2 = _num(row[2]); conditioned_source_eui_mj_m2 = _num(row[3])

    area_map = _kv(area_rows)
    floor_area = _num(area_map.get("Total Building Area"))
    conditioned_area = _num(area_map.get("Net Conditioned Building Area"))

    monthly_energy, monthly_peak, monthly_peak_ts, monthly_end_uses, monthly_peak_end_uses = _monthly_reports(soup)
    monthly_mean = []
    for idx, kwh in enumerate(monthly_energy, start=1):
        hours = calendar.monthrange(2023, idx)[1] * 24
        monthly_mean.append(kwh / hours if hours else 0.0)

    annual_end_use = _end_use_energy(annual_energy_rows)
    peak_time, peak_end_uses, total_peak = _end_use_peak(peak_rows)

    airloop = _records(table_map.get("AirLoopHVAC", []))
    outdoor_air = _records(table_map.get("Controller:OutdoorAir", []))
    cooling_coil = _records(table_map.get("Coil:Cooling:DX:TwoSpeed", []))
    fan = _records(table_map.get("Fan:VariableVolume", []))
    system_vent = _records(table_map.get("System Ventilation Calculations for Cooling Design", []))

    def first_num(records: List[Dict[str, str]], field: str) -> Optional[float]:
        if not records:
            return None
        return _num(records[0].get(field))

    design_supply = first_num(airloop, "Design Supply Air Flow Rate [m3/s]")
    fan_flow = first_num(fan, "Design Size Maximum Flow Rate [m3/s]")
    fan_power_w = first_num(fan, "Design Electric Power Consumption [W]")
    oa_flow = first_num(outdoor_air, "Maximum Outdoor Air Flow Rate [m3/s]")
    cooling_capacity_w = first_num(cooling_coil, "Design Size High Speed Gross Rated Total Cooling Capacity [W]")
    cooling_airflow = first_num(cooling_coil, "Design Size High Speed Rated Air Flow Rate [m3/s]")
    system_oa = first_num(system_vent, "Zone Outdoor Airflow Cooling - Voz-clg [m3/s]")

    simulated_hours = _num(general.get("Hours Simulated [hrs]"))
    if simulated_hours is None:
        m = re.search(r"Values gathered over\s+([0-9.]+)\s+hours", text)
        simulated_hours = _num(m.group(1)) if m else None

    heating_unmet = _num(comfort.get("Time Setpoint Not Met During Occupied Heating")) or 0.0
    cooling_unmet = _num(comfort.get("Time Setpoint Not Met During Occupied Cooling")) or 0.0
    ashrae55_simple = _num(comfort.get("Time Not Comfortable Based on Simple ASHRAE 55-2004"))

    quality_flags: List[Dict[str, str]] = []
    quality_flags.append({"severity": "PASS" if heating_unmet == 0 and cooling_unmet == 0 else "CHECK", "message": f"Occupied setpoint unmet hours: heating {heating_unmet:.1f} h, cooling {cooling_unmet:.1f} h."})
    if simulated_hours and abs(simulated_hours - 8760.0) < 1:
        quality_flags.append({"severity": "PASS", "message": "Full non-leap annual run completed: 8760 simulated hours."})
    else:
        quality_flags.append({"severity": "CHECK", "message": f"Simulation length reported as {simulated_hours or 0:.1f} h; verify annual coverage."})
    quality_flags.append({"severity": "INFO", "message": "eplustbl.htm is full annual tabular output; it does not contain an hourly meter time-series. Live reference therefore uses the calibrated monthly mean unless eplusout.sql is imported."})
    if ashrae55_simple is not None and ashrae55_simple > 0:
        quality_flags.append({"severity": "INFO", "message": f"Simple ASHRAE 55-2004 discomfort report: {ashrae55_simple:.1f} h. This metric is not used as a surgical-suite control limit in B.E.A.M."})

    annual_site_kwh = annual_site_gj / 0.0036 if annual_site_gj is not None else sum(monthly_energy)
    annual_source_kwh = annual_source_gj / 0.0036 if annual_source_gj is not None else None
    annual_electricity = sum(monthly_energy) if any(monthly_energy) else sum(annual_end_use.values())

    baseline = {
        "schema_version": "3.0",
        "calibrated": True,
        "calibration_tier": "FULL_ANNUAL_TABULAR",
        "source": "ENERGYPLUS_EPLUSTBL_8760_TABULAR",
        "source_file": path.name,
        "simulation_hours": simulated_hours,
        "floor_area_m2": floor_area,
        "conditioned_floor_area_m2": conditioned_area,
        "annual_site_energy_kwh": round(annual_site_kwh, 3) if annual_site_kwh is not None else None,
        "annual_electricity_kwh": round(annual_electricity, 3) if annual_electricity else None,
        "annual_source_energy_kwh": round(annual_source_kwh, 3) if annual_source_kwh is not None else None,
        "site_eui_kwh_m2_year": round(site_eui_mj_m2 / 3.6, 4) if site_eui_mj_m2 is not None else None,
        "source_eui_kwh_m2_year": round(source_eui_mj_m2 / 3.6, 4) if source_eui_mj_m2 is not None else None,
        "conditioned_site_eui_kwh_m2_year": round(conditioned_site_eui_mj_m2 / 3.6, 4) if conditioned_site_eui_mj_m2 is not None else None,
        "conditioned_source_eui_kwh_m2_year": round(conditioned_source_eui_mj_m2 / 3.6, 4) if conditioned_source_eui_mj_m2 is not None else None,
        "annual_peak_electric_kw": round(total_peak or max(monthly_peak or [0.0]), 4),
        "annual_peak_timestamp": peak_time,
        "monthly_electricity_kwh": [round(v, 4) for v in monthly_energy],
        "monthly_mean_electric_kw": [round(v, 5) for v in monthly_mean],
        "monthly_peak_electric_kw": [round(v, 4) for v in monthly_peak],
        "monthly_peak_timestamps": monthly_peak_ts,
        "end_uses_electricity_kwh": {k: round(v, 4) for k, v in annual_end_use.items()},
        "end_use_peak_kw": {k: round(v, 4) for k, v in peak_end_uses.items()},
        "monthly_end_use_electricity_kwh": {k: [round(v, 4) for v in vals] for k, vals in monthly_end_uses.items()},
        "monthly_peak_end_use_kw": {k: [round(v, 4) for v in vals] for k, vals in monthly_peak_end_uses.items()},
        "hourly_electric_kw": None,
        "metadata": {
            "energyplus_version": general.get("Program Version and Build"),
            "run_period": general.get("RunPeriod"),
            "weather_file": general.get("Weather File"),
            "latitude": _num(general.get("Latitude [deg]")),
            "longitude": _num(general.get("Longitude [deg]")),
            "elevation_m": _num(general.get("Elevation [m]")),
            "timezone": _num(general.get("Time Zone")),
            "north_axis_deg": _num(general.get("North Axis Angle [deg]")),
            "simulation_hours": simulated_hours,
            "timestep_minutes": (60.0 / (_num(timestep[0].get("#TimeSteps")) or 1.0)) if timestep else None,
            "total_unmet_hours": heating_unmet + cooling_unmet,
            "comfort": {
                "occupied_heating_unmet_hours": heating_unmet,
                "occupied_cooling_unmet_hours": cooling_unmet,
                "simple_ashrae55_not_comfortable_hours": ashrae55_simple,
            },
            "hvac_design": {
                "airloop_name": airloop[0].get("name") if airloop else None,
                "design_supply_airflow_m3s": design_supply,
                "outdoor_air_max_m3s": oa_flow,
                "cooling_coil_airflow_m3s": cooling_airflow,
                "cooling_coil_capacity_kw": cooling_capacity_w / 1000.0 if cooling_capacity_w is not None else None,
                "fan_design_airflow_m3s": fan_flow,
                "fan_design_power_kw": fan_power_w / 1000.0 if fan_power_w is not None else None,
                "system_outdoor_airflow_m3s": system_oa,
            },
            "spaces": spaces,
            "zones": zones,
            "zone_ventilation_cooling": _records(vent_cooling),
            "quality_flags": quality_flags,
            "hourly_profile_available": False,
            "hourly_profile_requirement": "Import eplusout.sql to replace the monthly-mean live anchor with a true 8760/8784 hourly facility electricity series.",
            "tabular_scope_note": "This file is an 8760-hour annual EnergyPlus tabular report. Annual, monthly, peak, end-use, zone/space and design-size data are calibrated; sub-hourly/hourly time-series are not present in eplustbl.htm.",
        },
    }
    return baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="Import EnergyPlus eplustbl.htm into B.E.A.M. v9 energy_baseline.json")
    parser.add_argument("eplustbl", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "energy_baseline.json")
    args = parser.parse_args()
    baseline = parse_eplustbl(args.eplustbl)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {args.eplustbl} -> {args.output}")
    print(f"Calibration tier: {baseline['calibration_tier']}")
    print(f"Simulation hours: {baseline['simulation_hours']:.0f}")
    print(f"Annual site energy: {baseline['annual_site_energy_kwh']:.1f} kWh")
    print(f"Site EUI: {baseline['site_eui_kwh_m2_year']:.2f} kWh/m²·yr")
    print(f"Annual peak: {baseline['annual_peak_electric_kw']:.2f} kW at {baseline.get('annual_peak_timestamp')}")
    print("Hourly meter profile: not present in eplustbl.htm; monthly mean remains the live facility anchor until eplusout.sql is imported.")


if __name__ == "__main__":
    main()
