from __future__ import annotations

import calendar
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CONTROL_ELIGIBLE_END_USES = {"Heating", "Cooling", "Interior Lighting", "Fans", "Pumps", "Heat Rejection", "Humidification", "Heat Recovery"}


@dataclass(frozen=True)
class EnergyBaseline:
    """OpenStudio/EnergyPlus baseline provenance for B.E.A.M.

    Calibration is intentionally tiered:
      * HOURLY: 8760/8784 facility-electric profile is available (typically from eplusout.sql).
      * FULL_ANNUAL_TABULAR: full 8760/8784 EnergyPlus annual tabular run with annual, monthly, peak, end-use and design metadata, but no hourly meter stream.
      * ANNUAL_MONTHLY: annual + monthly OpenStudio Results data is available, but no hourly profile.
      * ANNUAL: annual totals/EUI are available, but no monthly or hourly reference profile.
      * NONE: prototype-only counterfactual model.

    B.E.A.M. never fabricates an hourly OpenStudio baseline when report.html only
    contains annual/monthly results. For FULL_ANNUAL_TABULAR or ANNUAL_MONTHLY calibration, live facility
    reference is explicitly a *monthly mean* reference, not an hourly meter value.
    """

    calibrated: bool
    source: str
    calibration_tier: str = "NONE"
    floor_area_m2: Optional[float] = None
    conditioned_floor_area_m2: Optional[float] = None
    annual_site_energy_kwh: Optional[float] = None
    annual_electricity_kwh: Optional[float] = None
    annual_source_energy_kwh: Optional[float] = None
    site_eui_kwh_m2_year: Optional[float] = None
    source_eui_kwh_m2_year: Optional[float] = None
    conditioned_site_eui_kwh_m2_year: Optional[float] = None
    conditioned_source_eui_kwh_m2_year: Optional[float] = None
    annual_peak_electric_kw: Optional[float] = None
    simulation_hours: Optional[float] = None
    annual_peak_timestamp: Optional[str] = None
    hourly_electric_kw: Optional[List[float]] = None
    monthly_electricity_kwh: Optional[List[float]] = None
    monthly_mean_electric_kw: Optional[List[float]] = None
    monthly_peak_electric_kw: Optional[List[float]] = None
    monthly_peak_timestamps: Optional[List[str]] = None
    monthly_cooling_load_mbtu: Optional[List[float]] = None
    monthly_outdoor_temp_c: Optional[List[float]] = None
    end_uses_electricity_kwh: Optional[Dict[str, float]] = None
    end_use_peak_kw: Optional[Dict[str, float]] = None
    monthly_end_use_electricity_kwh: Optional[Dict[str, List[float]]] = None
    monthly_peak_end_use_kw: Optional[Dict[str, List[float]]] = None
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def uncalibrated(cls) -> "EnergyBaseline":
        return cls(calibrated=False, source="COUNTERFACTUAL_STANDARD_OPS_MODEL", calibration_tier="NONE")

    @classmethod
    def load(cls, path: str | Path) -> "EnergyBaseline":
        p = Path(path)
        if not p.exists():
            return cls.uncalibrated()
        raw = json.loads(p.read_text(encoding="utf-8"))

        profile = _profile(raw.get("hourly_electric_kw"), allowed_lengths={8760, 8784}, field="hourly_electric_kw")
        monthly_energy = _profile(raw.get("monthly_electricity_kwh"), allowed_lengths={12}, field="monthly_electricity_kwh")
        monthly_mean = _profile(raw.get("monthly_mean_electric_kw"), allowed_lengths={12}, field="monthly_mean_electric_kw")
        monthly_peak = _profile(raw.get("monthly_peak_electric_kw"), allowed_lengths={12}, field="monthly_peak_electric_kw")
        monthly_cooling = _profile(raw.get("monthly_cooling_load_mbtu"), allowed_lengths={12}, field="monthly_cooling_load_mbtu")
        monthly_outdoor = _profile(raw.get("monthly_outdoor_temp_c"), allowed_lengths={12}, field="monthly_outdoor_temp_c", clamp_nonnegative=False)

        floor_area = _positive_or_none(raw.get("floor_area_m2"))
        conditioned_area = _positive_or_none(raw.get("conditioned_floor_area_m2"))
        annual_site = _positive_or_none(raw.get("annual_site_energy_kwh"))
        annual_electricity = _positive_or_none(raw.get("annual_electricity_kwh"))
        annual_source = _positive_or_none(raw.get("annual_source_energy_kwh"))
        eui = _positive_or_none(raw.get("site_eui_kwh_m2_year"))
        source_eui = _positive_or_none(raw.get("source_eui_kwh_m2_year"))
        conditioned_site_eui = _positive_or_none(raw.get("conditioned_site_eui_kwh_m2_year"))
        conditioned_source_eui = _positive_or_none(raw.get("conditioned_source_eui_kwh_m2_year"))
        annual_peak = _positive_or_none(raw.get("annual_peak_electric_kw"))
        simulation_hours = _positive_or_none(raw.get("simulation_hours"))
        annual_peak_timestamp = str(raw.get("annual_peak_timestamp") or "") or None
        if eui is None and floor_area and annual_site:
            eui = annual_site / floor_area

        if monthly_energy and not monthly_mean:
            monthly_mean = []
            for month_idx, kwh in enumerate(monthly_energy, start=1):
                hours = calendar.monthrange(2023, month_idx)[1] * 24
                monthly_mean.append(kwh / hours)

        declared_tier = str(raw.get("calibration_tier") or "").upper().strip()
        if profile:
            tier = "HOURLY"
        elif declared_tier == "FULL_ANNUAL_TABULAR" and monthly_energy and (annual_site or annual_electricity):
            tier = "FULL_ANNUAL_TABULAR"
        elif monthly_energy and (annual_site or annual_electricity):
            tier = "ANNUAL_MONTHLY"
        elif annual_site and floor_area:
            tier = "ANNUAL"
        else:
            tier = "NONE"

        calibrated = bool(raw.get("calibrated", True)) and tier != "NONE"
        end_uses_raw = raw.get("end_uses_electricity_kwh")
        end_uses = {str(k): max(0.0, float(v)) for k, v in end_uses_raw.items()} if isinstance(end_uses_raw, dict) else {}
        end_use_peak_raw = raw.get("end_use_peak_kw")
        end_use_peak = {str(k): max(0.0, float(v)) for k, v in end_use_peak_raw.items()} if isinstance(end_use_peak_raw, dict) else {}
        monthly_end_use_raw = raw.get("monthly_end_use_electricity_kwh")
        monthly_end_use = {str(k): [max(0.0, float(x)) for x in v] for k, v in monthly_end_use_raw.items() if isinstance(v, list) and len(v) == 12} if isinstance(monthly_end_use_raw, dict) else {}
        monthly_peak_end_use_raw = raw.get("monthly_peak_end_use_kw")
        monthly_peak_end_use = {str(k): [max(0.0, float(x)) for x in v] for k, v in monthly_peak_end_use_raw.items() if isinstance(v, list) and len(v) == 12} if isinstance(monthly_peak_end_use_raw, dict) else {}
        monthly_peak_timestamps_raw = raw.get("monthly_peak_timestamps")
        monthly_peak_timestamps = [str(x) for x in monthly_peak_timestamps_raw] if isinstance(monthly_peak_timestamps_raw, list) and len(monthly_peak_timestamps_raw) == 12 else None

        return cls(
            calibrated=calibrated,
            source=str(raw.get("source") or "OPENSTUDIO_ENERGYPLUS_ANNUAL"),
            calibration_tier=tier,
            floor_area_m2=floor_area,
            conditioned_floor_area_m2=conditioned_area,
            annual_site_energy_kwh=annual_site,
            annual_electricity_kwh=annual_electricity,
            annual_source_energy_kwh=annual_source,
            site_eui_kwh_m2_year=eui,
            source_eui_kwh_m2_year=source_eui,
            conditioned_site_eui_kwh_m2_year=conditioned_site_eui,
            conditioned_source_eui_kwh_m2_year=conditioned_source_eui,
            annual_peak_electric_kw=annual_peak,
            simulation_hours=simulation_hours,
            annual_peak_timestamp=annual_peak_timestamp,
            hourly_electric_kw=profile,
            monthly_electricity_kwh=monthly_energy,
            monthly_mean_electric_kw=monthly_mean,
            monthly_peak_electric_kw=monthly_peak,
            monthly_peak_timestamps=monthly_peak_timestamps,
            monthly_cooling_load_mbtu=monthly_cooling,
            monthly_outdoor_temp_c=monthly_outdoor,
            end_uses_electricity_kwh=end_uses,
            end_use_peak_kw=end_use_peak,
            monthly_end_use_electricity_kwh=monthly_end_use,
            monthly_peak_end_use_kw=monthly_peak_end_use,
            metadata=dict(raw.get("metadata") or {}),
        )

    @property
    def reference_resolution(self) -> str:
        if self.hourly_electric_kw:
            return "HOURLY"
        if self.monthly_mean_electric_kw:
            return "MONTHLY_MEAN"
        if self.calibrated:
            return "ANNUAL_ONLY"
        return "MODELED_ONLY"

    def profile_timezone(self):
        value=(self.metadata or {}).get('timezone','Asia/Ho_Chi_Minh')
        return timezone(timedelta(hours=float(value))) if isinstance(value,(int,float)) else ZoneInfo(str(value or 'Asia/Ho_Chi_Minh'))

    def hourly_reference_kw(self, now: datetime) -> Optional[float]:
        profile = self.hourly_electric_kw
        if not profile:
            return None
        local=now.astimezone(self.profile_timezone()) if now.tzinfo else now
        year=2024 if len(profile)==8784 else 2023
        day=28 if len(profile)==8760 and local.month==2 and local.day==29 else local.day
        mapped=datetime(year,local.month,day,local.hour)
        index=int((mapped-datetime(year,1,1)).total_seconds()//3600)
        return float(profile[index])

    def monthly_mean_reference_kw(self, now: datetime) -> Optional[float]:
        profile = self.monthly_mean_electric_kw
        if not profile or len(profile) != 12:
            return None
        local=now.astimezone(self.profile_timezone()) if now.tzinfo else now
        return float(profile[local.month - 1])

    def facility_reference_kw(self, now: datetime) -> Tuple[Optional[float], str]:
        hourly = self.hourly_reference_kw(now)
        if hourly is not None:
            return hourly, "HOURLY_FACILITY_REFERENCE"
        monthly = self.monthly_mean_reference_kw(now)
        if monthly is not None:
            return monthly, "MONTHLY_MEAN_FACILITY_REFERENCE"
        return None, "COUNTERFACTUAL_STANDARD_OPS_MODEL"

    @property
    def control_eligible_end_use_fraction(self) -> Optional[float]:
        """Share of annual facility electricity represented by end uses B.E.A.M. can plausibly influence.

        This prevents a room-level control model from applying its raw kW delta to
        unrelated facility loads such as clinical equipment. It is still an
        engineering attribution boundary, not measurement & verification.
        """
        data = self.end_uses_electricity_kwh or {}
        denominator = self.annual_electricity_kwh
        if not denominator or denominator <= 0 or not data:
            return None
        eligible = sum(float(v) for k, v in data.items() if k in CONTROL_ELIGIBLE_END_USES)
        if eligible <= 0:
            return None
        return min(1.0, max(0.0, eligible / denominator))

    def apply_modeled_control_delta(
        self,
        now: datetime,
        modeled_reference_kw: float,
        modeled_controlled_kw: float,
    ) -> Tuple[Optional[float], Optional[float], Dict[str, Any]]:
        """Map a B.E.A.M. control effect onto the calibrated facility baseline.

        The raw modeled kW difference is *not* subtracted directly from a whole-
        facility OpenStudio reference. Instead the modeled fractional control
        effect is applied only to the OpenStudio end-use envelope that B.E.A.M.
        can influence (HVAC + interior lighting). This preserves system boundary.
        """
        facility_reference, base_method = self.facility_reference_kw(now)
        if facility_reference is None:
            return None, None, {
                "method": "COUNTERFACTUAL_STANDARD_OPS_MODEL",
                "eligible_fraction": None,
                "modeled_control_fraction": None,
                "applied_delta_kw": None,
            }

        raw_fraction = (float(modeled_reference_kw) - float(modeled_controlled_kw)) / max(abs(float(modeled_reference_kw)), 1e-6)
        # An optimizer may increase load during safety/emergency operation. Keep
        # the sign, but bound numerical excursions from the simplified room model.
        modeled_fraction = max(-1.0, min(1.0, raw_fraction))
        eligible_fraction = self.control_eligible_end_use_fraction

        if eligible_fraction is not None:
            eligible_reference_kw = facility_reference * eligible_fraction
            applied_delta_kw = eligible_reference_kw * modeled_fraction
            method = f"{base_method}_END_USE_SCALED_CONTROL_RATIO"
        else:
            # Legacy calibrated files without an end-use breakdown cannot support
            # end-use scaling. Bound the raw delta to the facility reference and
            # make the fallback explicit in provenance.
            raw_delta = float(modeled_reference_kw) - float(modeled_controlled_kw)
            applied_delta_kw = max(-facility_reference, min(facility_reference, raw_delta))
            eligible_reference_kw = None
            method = f"{base_method}_BOUNDED_RAW_CONTROL_DELTA"

        facility_estimate = max(0.0, facility_reference - applied_delta_kw)
        return facility_reference, facility_estimate, {
            "method": method,
            "eligible_fraction": eligible_fraction,
            "eligible_reference_kw": eligible_reference_kw,
            "modeled_control_fraction": modeled_fraction,
            "applied_delta_kw": applied_delta_kw,
            "raw_modeled_delta_kw": float(modeled_reference_kw) - float(modeled_controlled_kw),
        }

    def monthly_series(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for i, month in enumerate(MONTHS):
            rows.append({
                "month": month,
                "electricity_kwh": _at(self.monthly_electricity_kwh, i),
                "mean_kw": _at(self.monthly_mean_electric_kw, i),
                "peak_kw": _at(self.monthly_peak_electric_kw, i),
                "peak_timestamp": self.monthly_peak_timestamps[i] if self.monthly_peak_timestamps and i < len(self.monthly_peak_timestamps) else None,
                "cooling_mbtu": _at(self.monthly_cooling_load_mbtu, i),
                "outdoor_temp_c": _at(self.monthly_outdoor_temp_c, i),
            })
        return rows

    def end_use_series(self) -> List[Dict[str, Any]]:
        data = self.end_uses_electricity_kwh or {}
        peaks = self.end_use_peak_kw or {}
        return [{"end_use": k, "kwh": float(v), "peak_kw": float(peaks.get(k, 0.0))} for k, v in data.items() if float(v) > 0.0]

    def space_calibration(self, source_name: str) -> Optional[Dict[str, Any]]:
        spaces = (self.metadata or {}).get("spaces")
        if not isinstance(spaces, list):
            return None
        target = _normalize_name(source_name)
        if target == "void":
            target = "void1"
        for row in spaces:
            if not isinstance(row, dict):
                continue
            candidate = str(row.get("normalized_source_name") or _normalize_name(str(row.get("source_name") or "")))
            if candidate == target:
                return dict(row)
        return None

    @property
    def hvac_design(self) -> Dict[str, Any]:
        value = (self.metadata or {}).get("hvac_design")
        return dict(value) if isinstance(value, dict) else {}

    @property
    def calibration_quality_flags(self) -> List[Dict[str, Any]]:
        value = (self.metadata or {}).get("quality_flags")
        return [dict(x) for x in value if isinstance(x, dict)] if isinstance(value, list) else []

    def public_dict(self) -> Dict[str, Any]:
        return {
            "calibrated": self.calibrated,
            "source": self.source,
            "calibration_tier": self.calibration_tier,
            "reference_resolution": self.reference_resolution,
            "floor_area_m2": self.floor_area_m2,
            "conditioned_floor_area_m2": self.conditioned_floor_area_m2,
            "annual_site_energy_kwh": self.annual_site_energy_kwh,
            "annual_electricity_kwh": self.annual_electricity_kwh,
            "annual_source_energy_kwh": self.annual_source_energy_kwh,
            "site_eui_kwh_m2_year": self.site_eui_kwh_m2_year,
            "source_eui_kwh_m2_year": self.source_eui_kwh_m2_year,
            "conditioned_site_eui_kwh_m2_year": self.conditioned_site_eui_kwh_m2_year,
            "conditioned_source_eui_kwh_m2_year": self.conditioned_source_eui_kwh_m2_year,
            "annual_peak_electric_kw": self.annual_peak_electric_kw,
            "annual_peak_timestamp": self.annual_peak_timestamp,
            "simulation_hours": self.simulation_hours,
            "has_hourly_profile": bool(self.hourly_electric_kw),
            "has_monthly_profile": bool(self.monthly_electricity_kwh),
            "control_eligible_end_use_fraction": self.control_eligible_end_use_fraction,
            "control_eligible_end_uses": sorted(CONTROL_ELIGIBLE_END_USES),
            "monthly": self.monthly_series(),
            "end_uses_electricity": self.end_use_series(),
            "monthly_end_use_electricity_kwh": self.monthly_end_use_electricity_kwh or {},
            "monthly_peak_end_use_kw": self.monthly_peak_end_use_kw or {},
            "hvac_design": self.hvac_design,
            "metadata": self.metadata or {},
        }


def _normalize_name(value: str) -> str:
    text = str(value).replace("°", "u").replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _profile(value: Any, *, allowed_lengths: set[int], field: str, clamp_nonnegative: bool = True) -> Optional[List[float]]:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) not in allowed_lengths:
        expected = " or ".join(str(v) for v in sorted(allowed_lengths))
        raise ValueError(f"energy_baseline.json {field} must contain {expected} values")
    converted = [float(v) for v in value]
    if any(isinstance(v,bool) for v in value) or any(not math.isfinite(v) or (clamp_nonnegative and v<0) for v in converted):
        raise ValueError(f'energy_baseline.json {field} contains invalid numeric values')
    return [max(0.0, v) for v in converted] if clamp_nonnegative else converted


def _at(values: Optional[List[float]], index: int) -> Optional[float]:
    if values is None or index >= len(values):
        return None
    return float(values[index])


def _positive_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    v = float(value)
    if isinstance(value,bool) or not math.isfinite(v):raise ValueError('Invalid annual energy metric')
    return v if v > 0 else None
