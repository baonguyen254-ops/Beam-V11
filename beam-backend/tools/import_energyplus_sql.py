from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

J_PER_KWH = 3_600_000.0
KWH_PER_GJ = 277.7777777778


def columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def tabular_value(conn: sqlite3.Connection, report_like: str, table_like: str, row_like: str, column_like: str) -> Optional[Tuple[float, str]]:
    if not table_exists(conn, "TabularDataWithStrings"):
        return None
    cols = set(columns(conn, "TabularDataWithStrings"))
    required = {"ReportName", "TableName", "RowName", "ColumnName", "Value", "Units"}
    if not required.issubset(cols):
        return None
    query = """
        SELECT Value, Units
        FROM TabularDataWithStrings
        WHERE lower(ReportName) LIKE lower(?)
          AND lower(TableName) LIKE lower(?)
          AND lower(RowName) LIKE lower(?)
          AND lower(ColumnName) LIKE lower(?)
        LIMIT 1
    """
    row = conn.execute(query, (report_like, table_like, row_like, column_like)).fetchone()
    if not row:
        return None
    try:
        return float(str(row[0]).replace(",", "")), str(row[1] or "")
    except ValueError:
        return None


def convert_energy_to_kwh(value: float, units: str) -> Optional[float]:
    u = units.strip().lower().replace(" ", "")
    if u in {"gj", "gigajoule", "gigajoules"}:
        return value * KWH_PER_GJ
    if u in {"mj"}:
        return value / 3.6
    if u in {"kwh", "kw-hr", "kwhr"}:
        return value
    if u in {"j", "joule", "joules"}:
        return value / J_PER_KWH
    return None


def extract_annual_site_energy_kwh(conn: sqlite3.Connection) -> Optional[float]:
    candidates = [
        ("%AnnualBuildingUtilityPerformanceSummary%", "%Site and Source Energy%", "%Total Site Energy%", "%Total Energy%"),
        ("%AnnualBuildingUtilityPerformanceSummary%", "%Site and Source Energy%", "%Total Site Energy%", "%Energy Per Total Building Area%"),
    ]
    for args in candidates:
        found = tabular_value(conn, *args)
        if found:
            value, units = found
            converted = convert_energy_to_kwh(value, units)
            if converted is not None:
                return converted
    # Generic fallback: locate the Total Site Energy row and prefer an absolute-energy column.
    if table_exists(conn, "TabularDataWithStrings"):
        rows = conn.execute("""
            SELECT Value, Units, ColumnName
            FROM TabularDataWithStrings
            WHERE lower(ReportName) LIKE '%annualbuildingutilityperformancesummary%'
              AND lower(TableName) LIKE '%site and source energy%'
              AND lower(RowName) = 'total site energy'
        """).fetchall()
        for value, units, column in rows:
            if "area" in str(column).lower():
                continue
            try:
                converted = convert_energy_to_kwh(float(str(value).replace(",", "")), str(units or ""))
            except ValueError:
                continue
            if converted is not None:
                return converted
    return None


def extract_floor_area_m2(conn: sqlite3.Connection) -> Optional[float]:
    if not table_exists(conn, "TabularDataWithStrings"):
        return None
    rows = conn.execute("""
        SELECT Value, Units
        FROM TabularDataWithStrings
        WHERE lower(ReportName) LIKE '%annualbuildingutilityperformancesummary%'
          AND lower(TableName) LIKE '%building area%'
          AND lower(RowName) LIKE '%total building area%'
        LIMIT 5
    """).fetchall()
    for value, units in rows:
        try:
            v = float(str(value).replace(",", ""))
        except ValueError:
            continue
        u = str(units or "").strip().lower()
        if "m2" in u or "m^2" in u or "m²" in u:
            return v
        if "ft2" in u or "ft^2" in u or "ft²" in u:
            return v * 0.09290304
    return None


def find_electricity_dictionary_index(conn: sqlite3.Connection) -> Optional[Tuple[int, str]]:
    if not table_exists(conn, "ReportDataDictionary"):
        return None
    cols = set(columns(conn, "ReportDataDictionary"))
    if not {"ReportDataDictionaryIndex", "Name", "ReportingFrequency", "Units"}.issubset(cols):
        return None
    rows = conn.execute("""
        SELECT ReportDataDictionaryIndex, Units, ReportingFrequency
        FROM ReportDataDictionary
        WHERE lower(Name) = 'electricity:facility'
        ORDER BY CASE lower(ReportingFrequency)
            WHEN 'hourly' THEN 0
            WHEN 'timestep' THEN 1
            WHEN 'zone timestep' THEN 2
            ELSE 3 END
    """).fetchall()
    for idx, units, freq in rows:
        if str(freq).lower() == "hourly":
            return int(idx), str(units or "")
    if rows:
        raise ValueError('Electricity:Facility must be Hourly. Aggregate timestep data explicitly before importing.')
    return None


def extract_hourly_electric_kw(conn: sqlite3.Connection) -> Tuple[List[float], Dict[str, Any]]:
    found = find_electricity_dictionary_index(conn)
    if not found or not table_exists(conn, "ReportData") or not table_exists(conn, "Time"):
        return [], {"warning": "Hourly Electricity:Facility time series not found"}
    dict_index, units = found
    # Pick the environment period with the largest number of records. In a normal
    # annual run this selects the Weather Run Period rather than design days.
    groups = conn.execute("""
        SELECT Time.EnvironmentPeriodIndex, COUNT(*)
        FROM ReportData
        JOIN Time ON Time.TimeIndex = ReportData.TimeIndex
        WHERE ReportData.ReportDataDictionaryIndex = ?
        GROUP BY Time.EnvironmentPeriodIndex
        ORDER BY COUNT(*) DESC
    """, (dict_index,)).fetchall()
    if not groups:
        return [], {"warning": "Electricity:Facility dictionary exists but contains no time series"}
    environment_index = int(groups[0][0])
    if not {'Month','Day','Hour','Interval'}.issubset(columns(conn,'Time')):
        raise ValueError('Hourly import requires calendar Month, Day, Hour and Interval columns')
    rows = conn.execute("""
        SELECT ReportData.Value, Time.Interval, Time.Month, Time.Day, Time.Hour
        FROM ReportData
        JOIN Time ON Time.TimeIndex = ReportData.TimeIndex
        WHERE ReportData.ReportDataDictionaryIndex = ?
          AND Time.EnvironmentPeriodIndex = ?
          AND COALESCE(Time.WarmupFlag, 0) = 0
        ORDER BY ReportData.TimeIndex
    """, (dict_index, environment_index)).fetchall()
    if len(rows) not in {8760,8784}:
        raise ValueError('Hourly baseline must contain a complete year: 8760 or 8784 records')
    reference = datetime(2024 if len(rows)==8784 else 2023,1,1)
    values: List[float] = []
    u = units.strip().lower()
    for i,(value, interval_minutes, month, day, hour) in enumerate(rows):
        v = float(value)
        minutes = float(interval_minutes)
        expected = reference+timedelta(hours=i)
        if (month,day,hour)!=(expected.month,expected.day,expected.hour+1) or minutes!=60:
            raise ValueError('Hourly calendar is incomplete, duplicated, out of order or not 60-minute intervals')
        if not math.isfinite(v) or v<0:
            raise ValueError('Electricity series must contain finite nonnegative values')
        if u in {"j", "joules", "joule"}:
            kwh = v / J_PER_KWH
            kw = kwh / max(minutes / 60.0, 1e-9)
        elif u in {"w", "watts", "watt"}:
            kw = v / 1000.0
        elif u in {"kw"}:
            kw = v
        else:
            # EnergyPlus facility meters are normally J. Unknown units are not
            # guessed because doing so would silently corrupt ROI.
            raise ValueError(f'Unsupported Electricity:Facility units: {units}')
        values.append(max(0.0, kw))
    return values, {"environment_period_index": environment_index, "dictionary_units": units, "records": len(values)}


def hourly_to_annual_kwh(profile_kw: Sequence[float]) -> Optional[float]:
    if len(profile_kw) in {8760, 8784}:
        return sum(profile_kw)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Create B.E.A.M. energy_baseline.json from an EnergyPlus/OpenStudio eplusout.sql file")
    parser.add_argument("sql", type=Path, help="Path to eplusout.sql")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "energy_baseline.json")
    parser.add_argument("--weather-file", default="")
    parser.add_argument("--openstudio-version", default="")
    parser.add_argument("--energyplus-version", default="")
    parser.add_argument('--replace-run',action='store_true',help='Explicitly replace provenance when importing a different simulation run')
    args = parser.parse_args()
    if not args.sql.exists():
        raise SystemExit(f"SQL file not found: {args.sql}")
    conn = sqlite3.connect(args.sql.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        floor_area = extract_floor_area_m2(conn)
        annual_site = extract_annual_site_energy_kwh(conn)
        hourly_kw, ts_meta = extract_hourly_electric_kw(conn)
    finally:
        conn.close()
    annual_electricity = hourly_to_annual_kwh(hourly_kw)
    eui = annual_site / floor_area if annual_site and floor_area else None
    calibrated = bool(hourly_kw or (annual_site and floor_area))
    if not calibrated:
        raise SystemExit('No usable annual/tabular or full-year hourly outputs. Existing baseline was not changed.')
    if any(v is not None and (not math.isfinite(v) or v<=0) for v in (floor_area,annual_site,annual_electricity)):
        raise ValueError('Annual calibration metrics must be finite and positive')
    # If an annual/monthly HTML baseline has already been imported, merge the
    # SQL time-series into it instead of discarding richer monthly/end-use
    # provenance. SQL wins for fields it can resolve directly; report.html
    # remains the source for metadata not present in the SQL extraction.
    existing: Dict[str, Any] = {}
    if args.out.exists() and not args.replace_run:
        try:
            loaded = json.loads(args.out.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (ValueError,OSError) as exc:
            raise SystemExit('Existing baseline cannot be read; use another --out path.') from exc
    if existing.get('calibrated'):
        anchors=[(existing.get(k),v) for k,v in (('floor_area_m2',floor_area),('annual_site_energy_kwh',annual_site),('annual_electricity_kwh',annual_electricity)) if existing.get(k) and v]
        if len(anchors)<2 or any(abs(float(a)-b)/max(float(a),b)>.02 for a,b in anchors):
            raise SystemExit('Cannot verify same simulation run within 2% using two anchors. Use a new --out or explicit --replace-run. Existing baseline was not changed.')

    payload: Dict[str, Any] = dict(existing)
    existing_meta = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else {}
    merged_meta: Dict[str, Any] = dict(existing_meta)
    merged_meta.update({
        "source_sql": str(args.sql.resolve()),
        "weather_file": args.weather_file or existing_meta.get("weather_file", ""),
        "openstudio_version": args.openstudio_version or existing_meta.get("openstudio_version", ""),
        "energyplus_version": args.energyplus_version or existing_meta.get("energyplus_version", ""),
        "time_series": ts_meta,
    })

    payload.update({
        "schema_version": "2.0",
        "calibrated": calibrated or bool(existing.get("calibrated")),
        "calibration_tier": "HOURLY" if hourly_kw else (existing.get("calibration_tier") if existing.get("calibrated") else ("ANNUAL" if calibrated else "NONE")),
        "source": "OPENSTUDIO_RESULTS_HTML_PLUS_ENERGYPLUS_SQL" if existing.get("calibrated") else "OPENSTUDIO_ENERGYPLUS_ANNUAL_SQL",
        "floor_area_m2": floor_area if floor_area is not None else existing.get("floor_area_m2"),
        "annual_site_energy_kwh": annual_site if annual_site is not None else existing.get("annual_site_energy_kwh"),
        "annual_electricity_kwh": annual_electricity if annual_electricity is not None else existing.get("annual_electricity_kwh"),
        "site_eui_kwh_m2_year": eui if eui is not None else existing.get("site_eui_kwh_m2_year"),
        "hourly_electric_kw": hourly_kw if hourly_kw else existing.get("hourly_electric_kw"),
        "metadata": merged_meta,
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    serialized=json.dumps(payload,indent=2,allow_nan=False)
    fd,temp_path=tempfile.mkstemp(prefix='.beam-baseline-',dir=args.out.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as handle:
            handle.write(serialized);handle.flush();os.fsync(handle.fileno())
        os.replace(temp_path,args.out)
    finally:
        if os.path.exists(temp_path):os.unlink(temp_path)
    print(json.dumps({
        "out": str(args.out),
        "calibrated": calibrated,
        "floor_area_m2": floor_area,
        "annual_site_energy_kwh": annual_site,
        "site_eui_kwh_m2_year": eui,
        "hourly_points": len(hourly_kw),
        "annual_electricity_kwh": annual_electricity,
        "time_series_meta": ts_meta,
    }, indent=2))
    if not calibrated:
        raise SystemExit("No usable annual/tabular or hourly energy outputs were found. Ensure Output:SQLite SimpleAndTabular and hourly Electricity:Facility are requested.")


if __name__ == "__main__":
    main()
