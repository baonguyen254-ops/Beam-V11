from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from floorplan_model import CONDITIONED_CATEGORIES, FloorplanModel, load_floorplan
from his_engine import HISEngine
from energy_model import EnergyBaseline
from storage import Store
from runtime import RuntimeMixin


BEAM_VERSION = "11.1.0"
TICK_SECONDS = 1.0
TARIFF_VND_PER_KWH = 2_200.0
EMISSION_KG_PER_KWH = 0.7221
HISTORY_POINTS = 180
ROOM_TREND_POINTS = 36
ROOM_TREND_SAMPLE_SECONDS = 4.0


class RoomStatus:
    SETBACK = "SETBACK"
    PRECOOLING = "PRECOOLING"
    ACTIVE = "ACTIVE"
    ALARM = "ALARM"


class IncidentStatus:
    INFO = "INFO"
    ACTION = "ACTION"
    ALARM = "ALARM"


VALID_ROOM_MODES = {"MAXIMUM_RUNNING", "BALANCE", "MINIMUM_RUNNING", "SHUTDOWN"}
VALID_EMERGENCY_MODES = {
    "Immediate Smoke/Purge Mode",
    "Post-Op Sterilization Mode",
    "Negative Pressure Isolation Mode",
}

VALID_CONTROL_PROFILES = {
    "CLINICAL_STANDARD": {"temp_setpoint": 20.0, "rh_setpoint": 50.0, "fan_speed": 75.0, "lighting": 70},
    "SURGERY_READY": {"temp_setpoint": 20.0, "rh_setpoint": 50.0, "fan_speed": 90.0, "lighting": 100},
    "ENERGY_BALANCED": {"temp_setpoint": 21.0, "rh_setpoint": 50.0, "fan_speed": 60.0, "lighting": 45},
    "NIGHT_SETBACK": {"temp_setpoint": 23.0, "rh_setpoint": 50.0, "fan_speed": 40.0, "lighting": 15},
}
VALID_PRESSURE_POLICIES = {"STANDARD", "ENHANCED"}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def first_order(current: float, target: float, dt_seconds: float, tau_seconds: float) -> float:
    tau_seconds = max(0.001, tau_seconds)
    alpha = 1.0 - math.exp(-max(0.0, dt_seconds) / tau_seconds)
    return current + alpha * (target - current)


CATEGORY_ACH = {
    "OPERATING_ROOM": 24.0,
    "PREP": 12.0,
    "RECOVERY": 10.0,
    "PREOP": 9.0,
    "CORRIDOR": 6.0,
    "SCRUB": 15.0,
    "STERILIZATION": 12.0,
    "EQUIPMENT": 8.0,
    "DOCTORS": 6.0,
    "STAFF": 6.0,
    "NURSE_STATION": 7.0,
    "STORAGE": 4.0,
    "TOILET": 8.0,
    "CONTROL": 6.0,
    "MEETING": 6.0,
    "OFFICE": 6.0,
    "SUPPORT": 6.0,
}

CATEGORY_EQUIPMENT_W_M2 = {
    "OPERATING_ROOM": 70.0,
    "PREP": 28.0,
    "RECOVERY": 24.0,
    "PREOP": 18.0,
    "CORRIDOR": 5.0,
    "SCRUB": 15.0,
    "STERILIZATION": 45.0,
    "EQUIPMENT": 55.0,
    "DOCTORS": 10.0,
    "STAFF": 10.0,
    "NURSE_STATION": 18.0,
    "STORAGE": 4.0,
    "TOILET": 5.0,
    "CONTROL": 30.0,
    "MEETING": 10.0,
    "OFFICE": 12.0,
    "SUPPORT": 12.0,
}

CATEGORY_LIGHTING_W_M2 = {
    "OPERATING_ROOM": 18.0,
    "PREP": 14.0,
    "RECOVERY": 12.0,
    "PREOP": 12.0,
    "CORRIDOR": 8.0,
}


class BeamState(RuntimeMixin):
    def __init__(self, floorplan_path: str | Path, db_path=None, demo=False) -> None:
        self._lock = asyncio.Lock()
        self.demo_enabled = bool(demo)
        self.demo_info = {"active": False}
        self.store=Store(db_path)
        self.floorplan: FloorplanModel = load_floorplan(floorplan_path)
        self.autopilot = True
        self.emergency_mode: Optional[str] = None
        self._pressure_fault_active = False
        self._session_started_at = datetime.now().astimezone()

        self.controls: Dict[str, float] = {
            "temp_setpoint": 20.0,
            "rh_setpoint": 50.0,
            "fan_speed": 70.0,
        }
        # Load EnergyPlus/OpenStudio provenance before room initialization so the
        # digital-twin room registry can inherit real space power densities and
        # zone-proportional design airflow from the 8760-hour tabular run.
        baseline_path = Path(floorplan_path).with_name("energy_baseline.json")
        self.energy_baseline = EnergyBaseline.load(baseline_path)
        self.rooms: Dict[str, Dict[str, Any]] = self._init_rooms()
        self.his = HISEngine(self.floorplan,bootstrap=False)

        # Independent energy supervisor. It never overrides sterility/emergency
        # or explicit room manual modes; it optimizes only inside those bounds.
        self.energy_ai: Dict[str, Any] = {
            "enabled": True,
            "mode": "CONSTRAINT_AWARE_ENERGY_SUPERVISOR",
            "status": "INITIALIZING",
            "score": 100.0,
            "last_evaluation": None,
            "actions": [],
            "estimated_avoided_kw": 0.0,
            "guardrails": [
                "Sterility / pressure safety has absolute priority",
                "Emergency modes override optimization",
                "Explicit room manual modes override energy AI",
                "Active clinical ventilation is clamped to minimum policy",
                "SLA / OR capability constraints are never traded for energy",
            ],
        }

        self.lighting: Dict[str, Any] = {
            "level_percent": 70,
            "design_power_kw": round(sum(r["lighting_design_kw"] for r in self.rooms.values()), 2),
        }
        self.sterility: Dict[str, Any] = {
            "delta_p_pa": 3.2,
            "target_delta_p_pa": 3.2,
            "pressure_alarm": False,
            "safety_threshold_pa": 2.5,
            "control_source": "NORMAL",
            "positive_pressure_policy": "STANDARD",
            "trend": [],
            "trend_sample_accumulator_s": 0.0,
        }
        self.incident_log: List[Dict[str, Any]] = []

        self._conditioned_floor_area_m2 = round(sum(float(r["area_m2"]) for r in self.rooms.values() if r["conditioned"]), 2)
        self.roi: Dict[str, Any] = {
            "total_kwh_saved": 0.0,
            "financial_savings_vnd": 0.0,
            "co2_reduction_kg": 0.0,
            "beam_load_kw": 0.0,
            "baseline_kw": 0.0,
            "modeled_controlled_load_kw": 0.0,
            "modeled_reference_load_kw": 0.0,
            "calibration_method": "COUNTERFACTUAL_STANDARD_OPS_MODEL",
            "applied_control_delta_kw": 0.0,
            "raw_modeled_delta_kw": 0.0,
            "modeled_control_fraction": 0.0,
            "control_eligible_end_use_fraction": self.energy_baseline.control_eligible_end_use_fraction,
            "instant_savings_percent": 0.0,
            "peak_reduction_percent": 0.0,
            "total_beam_kwh": 0.0,
            "total_reference_kwh": 0.0,
            "session_seconds": 0.0,
            "history": [],
        }
        self._append_incident(
            f"OpenStudio/FloorSpace digital twin loaded: {len(self.rooms)} spaces, {len(self.floorplan.doors)} doors",
            "BEAM-Core",
            IncidentStatus.INFO,
        )

        try:
            self.initialize_runtime()
        except Exception:
            self.store.db.rollback()
            self.store.db.close()
            raise

    # ------------------------------------------------------------------
    # Room registry / plant model
    # ------------------------------------------------------------------

    def _init_rooms(self) -> Dict[str, Dict[str, Any]]:
        height = float(self.floorplan.story.get("floor_to_ceiling_height_m") or 2.4384)
        rooms: Dict[str, Dict[str, Any]] = {}
        for model_room in self.floorplan.rooms:
            area = max(1.0, float(model_room["area_m2"]))
            category = model_room["category"]
            conditioned = bool(model_room.get("conditioned"))
            calibration = self.energy_baseline.space_calibration(str(model_room.get("source_name") or ""))
            ach = CATEGORY_ACH.get(category, 0.0) if conditioned else 0.0
            fallback_airflow = area * height * ach
            calibrated_airflow = float(calibration.get("allocated_design_airflow_m3h") or 0.0) if calibration else 0.0
            calibrated_min_airflow = float(calibration.get("allocated_min_airflow_m3h") or 0.0) if calibration else 0.0
            if conditioned and calibrated_airflow > 0.0:
                max_airflow = clamp(calibrated_airflow, 20.0, 12_000.0)
                airflow_source = "ENERGYPLUS_ZONE_FLOW_AREA_ALLOCATION"
            elif conditioned:
                max_airflow = clamp(fallback_airflow, 450.0, 12_000.0)
                airflow_source = "BEAM_CATEGORY_ACH_FALLBACK"
            else:
                max_airflow = 0.0
                airflow_source = "UNCONDITIONED"

            calibrated_equipment_w_m2 = float(calibration.get("plug_w_m2") or 0.0) if calibration else 0.0
            calibrated_lighting_w_m2 = float(calibration.get("lighting_w_m2") or 0.0) if calibration else 0.0
            equipment_w_m2 = calibrated_equipment_w_m2 if calibrated_equipment_w_m2 > 0 else CATEGORY_EQUIPMENT_W_M2.get(category, 8.0)
            lighting_w_m2 = calibrated_lighting_w_m2 if calibrated_lighting_w_m2 > 0 else CATEGORY_LIGHTING_W_M2.get(category, 10.0)
            equipment_kw = area * equipment_w_m2 / 1000.0 if conditioned else 0.0
            lighting_kw = area * lighting_w_m2 / 1000.0 if conditioned else 0.0
            people_m2 = float(calibration.get("people_m2_per_person") or 0.0) if calibration else 0.0
            design_people = area / people_m2 if people_m2 > 0 else None

            hvac_design = self.energy_baseline.hvac_design
            system_fan_kw = float(hvac_design.get("fan_design_power_kw") or 0.0)
            system_flow_m3s = float(hvac_design.get("fan_design_airflow_m3s") or hvac_design.get("design_supply_airflow_m3s") or 0.0)
            if system_fan_kw > 0 and system_flow_m3s > 0 and airflow_source == "ENERGYPLUS_ZONE_FLOW_AREA_ALLOCATION":
                fan_design_kw = system_fan_kw * ((max_airflow / 3600.0) / system_flow_m3s)
                fan_power_source = "ENERGYPLUS_SYSTEM_FAN_PROPORTIONAL"
            else:
                design_pressure_pa = 900.0
                fan_efficiency = 0.62
                fan_design_kw = (max_airflow / 3600.0) * design_pressure_pa / fan_efficiency / 1000.0 if max_airflow else 0.0
                fan_power_source = "BEAM_PRESSURE_EFFICIENCY_FALLBACK"

            if category == "OPERATING_ROOM":
                temp, rh, flow_frac = 22.8, 52.0, 0.34
            elif category in {"PREP", "RECOVERY", "PREOP"}:
                temp, rh, flow_frac = 22.5, 52.0, 0.42
            elif category == "CORRIDOR":
                temp, rh, flow_frac = 23.0, 52.0, 0.38
            else:
                temp, rh, flow_frac = 23.0, 52.0, 0.38

            rooms[model_room["id"]] = {
                **model_room,
                "status": RoomStatus.SETBACK,
                "occupancy": 0,
                "surgeons": [],
                "power_kw": 0.0,
                "temp_c": temp,
                "humidity": rh,
                "airflow_m3h": max_airflow * flow_frac,
                "damper_position": flow_frac * 100.0 if max_airflow else 0.0,
                "equipment_design_kw": round(equipment_kw, 3),
                "lighting_design_kw": round(lighting_kw, 3),
                "equipment_design_w_m2": round(equipment_w_m2, 3),
                "lighting_design_w_m2": round(lighting_w_m2, 3),
                "fan_design_kw": round(fan_design_kw, 4),
                "fan_power_source": fan_power_source,
                "max_airflow_m3h": round(max_airflow, 1),
                "max_airflow_source": airflow_source,
                "calibrated_min_airflow_m3h": round(calibrated_min_airflow, 1) if calibrated_min_airflow > 0 else None,
                "design_people_capacity": round(design_people, 2) if design_people is not None else None,
                "openstudio_space_calibration": {
                    "matched": bool(calibration),
                    "zone_name": calibration.get("zone_name") if calibration else None,
                    "space_type": calibration.get("space_type") if calibration else None,
                    "openstudio_conditioned": calibration.get("conditioned") if calibration else None,
                    "calibration_method": calibration.get("calibration_method") if calibration else "NO_SPACE_MATCH",
                },
                "manual_mode": None,
                "manual_targets": None,
                "control_source": "INITIAL",
                "target_temp_c": temp,
                "target_humidity": rh,
                "target_airflow_m3h": round(max_airflow * flow_frac),
                "active_case_id": None,
                # Analytics are accumulated from real digital-twin ticks. There is
                # intentionally no synthetic trend seed or fabricated utilization.
                "session_utilized_seconds": 0.0,
                "session_observed_seconds": 0.0,
                "trend_sample_accumulator_s": 0.0,
                "trend": [],
                "alarm_severity": "NORMAL",
                "alarm_reasons": [],
            }
        return rooms

    def _standard_reference_room_power(self, room: Dict[str, Any], now: datetime) -> float:
        """Counterfactual standard-operation power for the same current clinical demand.

        This is not claimed to be an OpenStudio result. It is a transparent fallback
        reference used only until an annual EnergyPlus/OpenStudio profile is imported.
        """
        if not room["conditioned"]:
            return 0.0
        max_flow = max(1.0, float(room["max_airflow_m3h"]))
        category = room["category"]
        occupied = bool(room["occupancy"] or room.get("active_case_id"))
        activity = self.his.room_activity(room["id"], category, now)
        clinically_active = occupied or bool(activity)
        if category == "OPERATING_ROOM":
            flow_fraction = 0.82 if clinically_active else 0.70
            target_temp = 20.0 if clinically_active else 21.5
            light_fraction = 1.0 if clinically_active else 0.55
            equipment_factor = 1.0 if clinically_active else 0.45
        elif category in {"PREP", "RECOVERY", "PREOP", "SCRUB", "STERILIZATION"}:
            flow_fraction = 0.72 if clinically_active else 0.58
            target_temp = 21.0 if clinically_active else 22.0
            light_fraction = 0.70 if clinically_active else 0.45
            equipment_factor = 0.85 if clinically_active else 0.40
        elif category == "CORRIDOR":
            flow_fraction = 0.62 if clinically_active else 0.52
            target_temp = 22.0
            light_fraction = 0.55
            equipment_factor = 0.35
        else:
            flow_fraction = 0.55
            target_temp = 22.0
            light_fraction = 0.50
            equipment_factor = 0.45 if room["occupancy"] else 0.30
        equipment_factor=self._equipment_demand_factor(room,now)
        return self._power_from_operating_point(room, max_flow * flow_fraction, target_temp, light_fraction, equipment_factor)

    def _equipment_demand_factor(self,room,now):
        active=bool(room.get("active_case_id") or room.get("occupancy") or self.his.room_activity(room["id"],room["category"],now))
        return 1.0 if active else .30

    def _power_from_operating_point(
        self, room: Dict[str, Any], airflow_m3h: float, target_temp: float, light_fraction: float, equipment_factor: float
    ) -> float:
        max_flow = max(1.0, float(room["max_airflow_m3h"]))
        flow_fraction = clamp(float(airflow_m3h) / max_flow, 0.0, 1.0)
        lighting_kw = float(room["lighting_design_kw"]) * clamp(light_fraction, 0.0, 1.0)
        equipment_kw = float(room["equipment_design_kw"]) * clamp(equipment_factor, 0.0, 1.2)
        occupancy_kw = float(room["occupancy"]) * 0.12
        internal_heat_kw = lighting_kw * 0.85 + equipment_kw + occupancy_kw

        # v9 uses EnergyPlus design fan power when the room has a calibrated
        # zone-proportional airflow allocation. Rooms without a matching EnergyPlus
        # zone retain the transparent pressure/efficiency fallback calculated at init.
        design_fan_kw = float(room.get("fan_design_kw") or 0.0)
        fan_kw = design_fan_kw * (flow_fraction ** 3)

        # Simplified cooling electric demand. It remains a digital-twin model, not a
        # measured chiller meter; annual OpenStudio calibration is exposed separately.
        cooling_kw = max(0.0, (23.5 - target_temp) * 0.32 + internal_heat_kw * 0.28) * (0.72 + 0.28 * flow_fraction)
        return max(0.0, equipment_kw + lighting_kw + fan_kw + cooling_kw)

    def _modeled_reference_load_kw(self, now: datetime) -> float:
        return sum(self._standard_reference_room_power(room, now) for room in self.rooms.values())

    def _fan_scale(self) -> float:
        return clamp(self.controls["fan_speed"] / 70.0, 0.42, 1.35)

    def _lighting_airflow_boost(self) -> float:
        if not self.autopilot:
            return 1.0
        fraction = self.lighting["level_percent"] / 100.0
        return 1.0 if fraction <= 0.5 else 1.0 + 0.10 * ((fraction - 0.5) / 0.5)

    def _room_policy(self, room: Dict[str, Any], now: datetime) -> Tuple[str, float, float, float, str]:
        category = room["category"]
        max_flow = float(room["max_airflow_m3h"])
        if not room["conditioned"]:
            return RoomStatus.SETBACK, room["temp_c"], room["humidity"], 0.0, "UNCONDITIONED"

        active_temp = float(self.controls["temp_setpoint"])
        active_rh = float(self.controls["rh_setpoint"])
        fan_scale = self._fan_scale()
        lighting_boost = self._lighting_airflow_boost()
        manual_targets = room.get("manual_targets")
        if manual_targets:
            active_temp = float(manual_targets["temp_c"])
            active_rh = float(manual_targets["humidity"])
            # Per-room airflow is expressed as a percentage of this room's design
            # airflow. Safety/clinical minimums still clamp it below.
            fan_scale = clamp(float(manual_targets["airflow_percent"]) / 70.0, 0.42, 1.43)

        # Safety is absolute. Intentional negative isolation is only allowed when
        # no physical pressure fault is latched (enforced in command handler).
        if self._pressure_fault_active or (self.sterility["pressure_alarm"] and (self.emergency_mode != "Negative Pressure Isolation Mode" or self.hospital.config['mode']=='CONNECTED')):
            return RoomStatus.ALARM, 20.0, 45.0, max_flow, "SAFETY_LOCK"

        if self.emergency_mode == "Immediate Smoke/Purge Mode":
            return RoomStatus.ALARM, 20.0, 45.0, max_flow, "SMOKE_PURGE"
        if self.emergency_mode == "Post-Op Sterilization Mode":
            return RoomStatus.ACTIVE, 20.0, 45.0, max_flow * 0.95, "POST_OP_STERILIZATION"
        if self.emergency_mode == "Negative Pressure Isolation Mode":
            return RoomStatus.ACTIVE, 20.0, 45.0, max_flow * 0.82, "NEGATIVE_ISOLATION"

        if category=="OPERATING_ROOM" and room.get("manual_mode") in {"MINIMUM_RUNNING","SHUTDOWN"} and self.his.active_case_for_room(room["id"],now):
            return RoomStatus.ACTIVE,active_temp,active_rh,max_flow*.82,"HIS_ACTIVE_SAFETY_MINIMUM"
        if category == "OPERATING_ROOM":
            turnover = any(c.get("scheduled_room_id") == room["id"] and c["status"] == "COMPLETED"
                           and c.get("scheduled_end") and c["scheduled_end"] <= now < c["scheduled_end"] + timedelta(minutes=18)
                           for c in self.his.cases)
            if turnover:
                return RoomStatus.ACTIVE, active_temp, active_rh, max_flow * .95, "HIS_TURNOVER"
        if self.hospital.config["mode"] == "CONNECTED" and not self.hospital.fresh(room["id"], now):
            return RoomStatus.ALARM, active_temp, active_rh, max_flow, "STALE_SENSOR_HOLD"
        manual = room.get("manual_mode")
        if manual == "MAXIMUM_RUNNING":
            return RoomStatus.ACTIVE, active_temp, active_rh, max_flow, "MANUAL_MAX"
        if manual == "MINIMUM_RUNNING":
            return RoomStatus.SETBACK, max(23.0, active_temp + 3.0), max(52.0, active_rh), max_flow * 0.30, "MANUAL_MIN"
        if manual == "SHUTDOWN":
            return RoomStatus.SETBACK, 25.0, 55.0, max_flow * 0.06, "MAINTENANCE"

        # Explicit room targets are a supervisory manual override below physical
        # safety/emergency modes but above HIS/Energy-AI optimization. An active OR
        # still receives the clinical minimum airflow even if the operator requests
        # a lower percentage.
        if manual_targets:
            requested_flow = max_flow * clamp(float(manual_targets["airflow_percent"]) / 100.0, 0.30, 1.0)
            if category == "OPERATING_ROOM":
                active_case = self.his.active_case_for_room(room["id"], now) or self.his.waiting_case_for_room(room["id"],now)
                room["active_case_id"] = active_case["id"] if active_case else None
                if active_case:
                    return RoomStatus.ACTIVE, active_temp, active_rh, max(requested_flow, max_flow * 0.82), "MANUAL_TARGETS_HIS_ACTIVE"
                return RoomStatus.SETBACK, active_temp, active_rh, requested_flow, "MANUAL_TARGETS"
            activity = self.his.room_activity(room["id"], category, now)
            return (RoomStatus.ACTIVE if activity else RoomStatus.SETBACK), active_temp, active_rh, requested_flow, "MANUAL_TARGETS"

        # With Energy AI disabled, retain a conservative standard operating policy
        # rather than aggressive setbacks. HIS still determines active/pre-cool state.
        energy_ai_enabled = bool(self.energy_ai["enabled"])

        if category == "OPERATING_ROOM":
            active_case = self.his.active_case_for_room(room["id"], now) or self.his.waiting_case_for_room(room["id"],now)
            if active_case:
                room["active_case_id"] = active_case["id"]
                # Active clinical ventilation has a hard minimum; a low operator
                # AHU slider cannot silently under-ventilate an active OR.
                airflow = min(max_flow, max_flow * max(0.82, 0.82 * fan_scale * lighting_boost))
                return RoomStatus.ACTIVE, active_temp, active_rh, airflow, "HIS_ACTIVE"
            room["active_case_id"] = None
            next_case = self.his.next_case_for_room(room["id"], now)
            if next_case and next_case.get("scheduled_start"):
                if energy_ai_enabled:
                    thermal_gap = max(0.0, float(room["temp_c"]) - active_temp)
                    lead_minutes = clamp(10.0 + thermal_gap * 3.0 + float(room["area_m2"]) / 55.0, 12.0, 32.0)
                else:
                    lead_minutes = 30.0
                trait=self.hospital.thermal.get(room["id"],{})
                if energy_ai_enabled and trait.get("samples",0)>=10 and trait.get("cooling_c_per_min",0)>.001:
                    lead_minutes=clamp(max(lead_minutes,max(0,room["temp_c"]-active_temp)/trait["cooling_c_per_min"]+5),12,60)
                if energy_ai_enabled and hasattr(self, "v11"):
                    lead_minutes = max(lead_minutes, self.v11.trait(room, now)["lead_minutes"])
                precool_start = next_case["scheduled_start"] - timedelta(minutes=lead_minutes)
                if precool_start <= now < next_case["scheduled_start"]:
                    fraction = clamp(
                        (now - precool_start).total_seconds()
                        / max(1.0, (next_case["scheduled_start"] - precool_start).total_seconds()),
                        0.0,
                        1.0,
                    )
                    idle_temp = max(23.0, active_temp + 3.5)
                    target_temp = idle_temp + (active_temp - idle_temp) * fraction
                    min_fraction = 0.48 + 0.30 * fraction
                    airflow = max_flow * max(min_fraction, min_fraction * fan_scale * lighting_boost)
                    return RoomStatus.PRECOOLING, target_temp, 54.0 + (active_rh - 54.0) * fraction, min(max_flow, airflow), "ENERGY_AI_PRECONDITION" if energy_ai_enabled else "STANDARD_PRECONDITION"
            if energy_ai_enabled:
                return RoomStatus.SETBACK, max(23.0, active_temp + 3.5), max(52.0, active_rh), max_flow * 0.30 * fan_scale, "ENERGY_AI_SETBACK"
            return RoomStatus.SETBACK, 21.5, 50.0, max_flow * 0.70, "STANDARD_STANDBY"

        activity = self.his.room_activity(room["id"], category, now)
        if activity:
            if category == "CORRIDOR":
                return RoomStatus.ACTIVE, 21.5, 51.0, max_flow * max(0.60, 0.68 * fan_scale), activity
            if category == "RECOVERY":
                return RoomStatus.ACTIVE, 21.5, 50.0, max_flow * max(0.70, 0.76 * fan_scale), activity
            if category in {"PREP", "PREOP"}:
                return RoomStatus.ACTIVE, 21.0, 50.0, max_flow * max(0.72, 0.78 * fan_scale), activity

        if category in {"SCRUB", "STERILIZATION"}:
            any_active_or = any(
                self.his.active_case_for_room(or_room["id"], now)
                for or_room in self.floorplan.operating_rooms()
            )
            if any_active_or:
                return RoomStatus.ACTIVE, 21.0, 50.0, max_flow * 0.72 * fan_scale, "CLINICAL_SUPPORT"

        if not energy_ai_enabled:
            if category == "CORRIDOR":
                return RoomStatus.SETBACK, 22.0, 50.0, max_flow * 0.52, "STANDARD_STANDBY"
            return RoomStatus.SETBACK, 22.0, 50.0, max_flow * 0.55, "STANDARD_STANDBY"
        if category == "CORRIDOR":
            return RoomStatus.SETBACK, 22.5, 52.0, max_flow * 0.38 * fan_scale, "ENERGY_AI_SETBACK"
        return RoomStatus.SETBACK, 23.0, 52.0, max_flow * 0.36 * fan_scale, "ENERGY_AI_SETBACK"

    def _update_occupancy(self, room: Dict[str, Any], now: datetime) -> None:
        category = room["category"]
        room["surgeons"] = []
        if category == "OPERATING_ROOM":
            case = self.his.active_case_for_room(room["id"], now)
            if case:
                base = 5
                if case["specialty"] in {"CARDIAC", "NEUROSURGERY", "TRAUMA"}:
                    base = 7
                room["occupancy"] = base
                room["surgeons"] = [self.hospital.staff[i]["name"] for i in case.get("staff_ids",[]) if i in self.hospital.staff]
                room["active_case_id"] = case["id"]
            else:
                room["occupancy"] = 0
                room["active_case_id"] = None
            return
        activity = self.his.room_activity(room["id"], category, now)
        if category == "RECOVERY":
            room["occupancy"] = 4 if activity else 1
        elif category in {"PREP", "PREOP"}:
            room["occupancy"] = 3 if activity else 0
        elif category == "CORRIDOR":
            room["occupancy"] = 2 if activity else 0
        elif category in {"NURSE_STATION", "DOCTORS", "STAFF"}:
            room["occupancy"] = 1
        else:
            room["occupancy"] = 0

    def _update_room_analytics(self, room: Dict[str, Any], dt_seconds: float, now: datetime) -> None:
        """Accumulate room KPIs only from actual simulation ticks.

        ``session_utilization_percent`` is explicitly a session metric. For an OR,
        utilized means an active surgical case. For support spaces, utilized means
        occupied. Trend points are rolling telemetry from the same model state sent
        to clients; they are never pre-seeded.
        """
        dt = max(0.0, float(dt_seconds))
        room["session_observed_seconds"] += dt
        utilized = bool(room.get("active_case_id")) if room["category"] == "OPERATING_ROOM" else bool(room.get("occupancy", 0) > 0)
        if utilized:
            room["session_utilized_seconds"] += dt

        reasons: List[str] = []
        severity = "NORMAL"
        if room["conditioned"]:
            temp_error = abs(float(room["temp_c"]) - float(room["target_temp_c"]))
            rh_error = abs(float(room["humidity"]) - float(room["target_humidity"]))
            if self.sterility["pressure_alarm"] or room["status"] == RoomStatus.ALARM:
                severity = "CRITICAL"
                reasons.append("Sterility / differential-pressure safety override")
            else:
                if temp_error >= 2.5:
                    severity = "WARNING"
                    reasons.append(f"Temperature deviation {temp_error:.1f}°C")
                elif temp_error >= 1.5:
                    severity = "ADVISORY"
                    reasons.append(f"Temperature deviation {temp_error:.1f}°C")
                if rh_error >= 12.0:
                    if severity != "CRITICAL":
                        severity = "WARNING"
                    reasons.append(f"Humidity deviation {rh_error:.0f}% RH")
                elif rh_error >= 7.0 and severity == "NORMAL":
                    severity = "ADVISORY"
                    reasons.append(f"Humidity deviation {rh_error:.0f}% RH")
                if room["category"] == "OPERATING_ROOM" and room.get("active_case_id") and float(room["airflow_m3h"]) < 0.85 * max(1.0, float(room["target_airflow_m3h"])):
                    severity = "WARNING"
                    reasons.append("Active OR airflow has not reached 85% of target")
        room["alarm_severity"] = severity
        room["alarm_reasons"] = reasons

        room["trend_sample_accumulator_s"] += dt
        if room["trend_sample_accumulator_s"] >= ROOM_TREND_SAMPLE_SECONDS:
            room["trend_sample_accumulator_s"] %= ROOM_TREND_SAMPLE_SECONDS
            trend: List[Dict[str, Any]] = room["trend"]
            trend.append({
                "time": now.isoformat(),
                "temp_c": round(float(room["temp_c"]), 2),
                "humidity": round(float(room["humidity"]), 2),
                "airflow_m3h": round(float(room["airflow_m3h"]), 1),
                "power_kw": round(float(room["power_kw"]), 3),
            })
            del trend[:-ROOM_TREND_POINTS]

    def _apply_room_dynamics(self, room: Dict[str, Any], dt_seconds: float, now: datetime) -> None:
        self._update_occupancy(room, now)
        status, target_temp, target_rh, target_airflow, source = self._room_policy(room, now)
        room["status"] = status
        room["control_source"] = source
        room["target_temp_c"] = round(float(target_temp), 2)
        room["target_humidity"] = round(float(target_rh), 2)
        room["target_airflow_m3h"] = round(float(target_airflow))

        if self.hospital.config['mode']=='CONNECTED':
            if self.hospital.fresh(room['id'],now):
                for field in ('temp_c','humidity','airflow_m3h','power_kw'):room[field]=self.hospital.meters[room['id']][field]
                room['telemetry_source']='BMS_MEASURED'
                self._update_room_analytics(room,dt_seconds,now)
            else:
                room['telemetry_source']='BMS_STALE_OR_MISSING'
                room['alarm_severity']='CRITICAL' if room.get('active_case_id') else 'WARNING'
                room['alarm_reasons']=['Fresh BMS telemetry missing; last values retained, not simulated']
            return
        room['telemetry_source']='DIGITAL_TWIN_MODEL'
        if not room["conditioned"]:
            room["power_kw"] = 0.0
            room["airflow_m3h"] = 0.0
            room["damper_position"] = 0.0
            self._update_room_analytics(room, dt_seconds, now)
            return

        max_flow = max(1.0, float(room["max_airflow_m3h"]))
        target_airflow = clamp(float(target_airflow), 0.0, max_flow)
        room["airflow_m3h"] = first_order(float(room["airflow_m3h"]), target_airflow, dt_seconds, 26.0)
        damper_target = 100.0 * target_airflow / max_flow
        room["damper_position"] = first_order(float(room["damper_position"]), damper_target, dt_seconds, 16.0)

        lighting_fraction = self.lighting["level_percent"] / 100.0
        # Surgical lighting remains an operator demand during an active OR case.
        # Energy AI is allowed to reduce lighting only when a room is idle or in
        # non-procedural support operation; it never dims an active OR below the
        # explicit surgical-light command.
        if room["category"] == "OPERATING_ROOM":
            if status in {RoomStatus.ACTIVE,RoomStatus.ALARM} or room.get("active_case_id"):
                local_light_fraction = lighting_fraction
            elif self.energy_ai["enabled"]:
                local_light_fraction = min(0.30, max(0.12, lighting_fraction * 0.30))
            else:
                local_light_fraction = min(0.70, max(0.45, lighting_fraction * 0.70))
        else:
            if self.energy_ai["enabled"] and room["occupancy"] == 0 and status == RoomStatus.SETBACK:
                local_light_fraction = 0.15
            elif self.energy_ai["enabled"] and room["occupancy"] > 0:
                local_light_fraction = min(0.70, 0.38 + lighting_fraction * 0.28)
            else:
                local_light_fraction = min(0.75, 0.35 + lighting_fraction * 0.35)
        lighting_kw = room["lighting_design_kw"] * local_light_fraction
        equipment_factor=self._equipment_demand_factor(room,now)
        equipment_kw = room["equipment_design_kw"] * equipment_factor
        occupancy_kw = room["occupancy"] * 0.12
        internal_heat_kw = lighting_kw * 0.85 + equipment_kw + occupancy_kw

        design_need = max(300.0, min(max_flow, 0.78 * max_flow))
        capacity_ratio = clamp(room["airflow_m3h"] / design_need, 0.0, 1.2)
        temp_penalty = max(0.0, 1.0 - capacity_ratio) * internal_heat_kw * 0.08
        effective_temp_target = target_temp + temp_penalty
        room["temp_c"] = first_order(float(room["temp_c"]), effective_temp_target, dt_seconds, 165.0)
        moisture_penalty = max(0.0, 1.0 - capacity_ratio) * room["occupancy"] * 0.25
        room["humidity"] = first_order(float(room["humidity"]), target_rh + moisture_penalty, dt_seconds, 210.0)

        room["power_kw"] = self._power_from_operating_point(
            room, room["airflow_m3h"], target_temp, local_light_fraction, equipment_factor
        )
        room["temp_c"] = clamp(room["temp_c"], 16.0, 32.0)
        room["humidity"] = clamp(room["humidity"], 30.0, 70.0)
        room["airflow_m3h"] = clamp(room["airflow_m3h"], 0.0, max_flow)
        room["damper_position"] = clamp(room["damper_position"], 0.0, 100.0)
        self._update_room_analytics(room, dt_seconds, now)

    # ------------------------------------------------------------------
    # Safety and ROI
    # ------------------------------------------------------------------

    def _update_sterility(self, dt_seconds: float) -> None:
        if self.hospital.config['mode']=='CONNECTED':
            now=datetime.now().astimezone();sample=self.hospital.meters.get('facility',{})
            if self.hospital.fresh('facility',now) and 'delta_p_pa' in sample:
                pressure=sample['delta_p_pa']
                alarm=pressure>-2.5 if self.emergency_mode=='Negative Pressure Isolation Mode' else pressure<self.sterility['safety_threshold_pa']
                self.sterility.update(delta_p_pa=pressure,pressure_alarm=bool(alarm or self._pressure_fault_active),control_source='BMS_MEASURED')
            else:self.sterility.update(pressure_alarm=True,control_source='BMS_PRESSURE_STALE')
            return
        clinical = [r for r in self.rooms.values() if r["category"] in {"OPERATING_ROOM", "PREP", "RECOVERY", "PREOP", "CORRIDOR"} and r["conditioned"]]
        avg_damper = sum(float(r["damper_position"]) for r in clinical) / max(1, len(clinical))
        if self.emergency_mode == "Negative Pressure Isolation Mode" and not self._pressure_fault_active:
            self.sterility["target_delta_p_pa"] = -2.5
            self.sterility["control_source"] = "NEGATIVE_ISOLATION"
            self.sterility["pressure_alarm"] = False
            self.sterility["delta_p_pa"] = first_order(self.sterility["delta_p_pa"], -2.5, dt_seconds, 8.0)
            self.sterility["trend_sample_accumulator_s"] = float(self.sterility.get("trend_sample_accumulator_s", 0.0)) + dt_seconds
            if self.sterility["trend_sample_accumulator_s"] >= 4.0:
                self.sterility["trend_sample_accumulator_s"] %= 4.0
                trend = self.sterility.setdefault("trend", [])
                trend.append({
                    "time": datetime.now().astimezone().isoformat(),
                    "delta_p_pa": round(float(self.sterility["delta_p_pa"]), 3),
                    "target_delta_p_pa": -2.5,
                })
                del trend[:-45]
            return
        if self._pressure_fault_active:
            target = 0.8
            self.sterility["control_source"] = "PRESSURE_FAULT"
        else:
            fan_fraction = self.controls["fan_speed"] / 100.0
            target = 2.45 + 0.92 * fan_fraction + 0.28 * (avg_damper / 100.0)
            if self.sterility.get("positive_pressure_policy") == "ENHANCED":
                target += 0.35
            if self.sterility["pressure_alarm"] or self.emergency_mode == "Immediate Smoke/Purge Mode":
                target = max(3.6, target)
                self.sterility["control_source"] = "PURGE_RECOVERY"
            else:
                self.sterility["control_source"] = "ENHANCED_POSITIVE" if self.sterility.get("positive_pressure_policy") == "ENHANCED" else "NORMAL"
        self.sterility["target_delta_p_pa"] = round(target, 2)
        self.sterility["delta_p_pa"] = first_order(self.sterility["delta_p_pa"], target, dt_seconds, 16.0)
        threshold = float(self.sterility["safety_threshold_pa"])
        if self.sterility["delta_p_pa"] < threshold and not self.sterility["pressure_alarm"]:
            self.sterility["pressure_alarm"] = True
            self._append_incident(
                f"Sterility hard-lock engaged: ΔP {self.sterility['delta_p_pa']:.2f} Pa < +{threshold:.1f} Pa",
                "BEAM-AI",
                IncidentStatus.ALARM,
            )
        self.sterility["trend_sample_accumulator_s"] = float(self.sterility.get("trend_sample_accumulator_s", 0.0)) + dt_seconds
        if self.sterility["trend_sample_accumulator_s"] >= 4.0:
            self.sterility["trend_sample_accumulator_s"] %= 4.0
            trend = self.sterility.setdefault("trend", [])
            trend.append({
                "time": datetime.now().astimezone().isoformat(),
                "delta_p_pa": round(float(self.sterility["delta_p_pa"]), 3),
                "target_delta_p_pa": round(float(self.sterility["target_delta_p_pa"]), 3),
            })
            del trend[:-45]

    def _evaluate_energy_ai(self, now: datetime) -> None:
        actions: List[Dict[str, Any]] = []
        for room in self.rooms.values():
            source = str(room.get("control_source") or "")
            if source in {"ENERGY_AI_SETBACK", "ENERGY_AI_PRECONDITION"}:
                actions.append({
                    "room_id": room["id"],
                    "room": room["name"],
                    "action": "PRECONDITION" if source.endswith("PRECONDITION") else "SETBACK",
                    "reason": "Upcoming HIS demand" if source.endswith("PRECONDITION") else "No near-term clinical demand",
                })
        thermal_penalty = sum(1 for r in self.rooms.values() if r["conditioned"] and abs(float(r["temp_c"]) - float(r["target_temp_c"])) > 1.5)
        sla_risk = int(self.his.public_state(now, self.autopilot)["scheduler"]["sla_risk_count"])
        safety_penalty = 35 if self.sterility["pressure_alarm"] else 0
        score = clamp(100.0 - thermal_penalty * 2.0 - sla_risk * 8.0 - safety_penalty, 0.0, 100.0)
        self.energy_ai.update({
            "status": "SAFETY_OVERRIDE" if self.sterility["pressure_alarm"] else ("OPTIMIZING" if self.energy_ai["enabled"] else "DISABLED"),
            "score": round(score, 1),
            "last_evaluation": now.isoformat(),
            "actions": actions[:24],
            "estimated_avoided_kw": round(float(self.roi.get("baseline_kw", 0.0)) - float(self.roi.get("beam_load_kw", 0.0)), 2),
        })

    def _update_roi(self, dt_seconds: float, now: datetime) -> None:
        modeled_beam = sum(float(room["power_kw"]) for room in self.rooms.values())
        modeled_reference = self._modeled_reference_load_kw(now)
        calibrated_reference, calibrated_estimate, calibration_diag = self.energy_baseline.apply_modeled_control_delta(
            now, modeled_reference, modeled_beam
        )
        if calibrated_reference is not None and calibrated_estimate is not None:
            # Result-informed calibration: apply the modeled *fractional* control
            # effect only to OpenStudio end uses B.E.A.M. can influence. This
            # avoids subtracting a raw room-model kW delta from unrelated facility
            # equipment loads and keeps the system boundary explicit.
            baseline = calibrated_reference
            beam_load = calibrated_estimate
        else:
            baseline = modeled_reference
            beam_load = modeled_beam
            calibration_diag = {
                "method": "COUNTERFACTUAL_STANDARD_OPS_MODEL",
                "eligible_fraction": None,
                "modeled_control_fraction": (modeled_reference - modeled_beam) / max(abs(modeled_reference), 1e-6),
                "applied_delta_kw": modeled_reference - modeled_beam,
                "raw_modeled_delta_kw": modeled_reference - modeled_beam,
            }
        if self.hospital.config['mode']=='CONNECTED':
            if not self.hospital.fresh('facility',now):
                self.roi['calibration_method']='BMS_METER_MISSING_NO_NEW_ENERGY_CREDIT';return
            beam_load=self.hospital.meters['facility']['power_kw']
            calibration_diag['method']='MEASURED_FACILITY_VS_OPENSTUDIO_REFERENCE'
        delta_kw = baseline - beam_load  # signed: emergency/high-load periods can reduce prior savings
        dt_hours = dt_seconds / 3600.0
        delta_kwh = delta_kw * dt_hours
        self.roi["total_kwh_saved"] += delta_kwh
        self.roi["total_beam_kwh"] += beam_load * dt_hours
        self.roi["total_reference_kwh"] += baseline * dt_hours
        self.roi["session_seconds"] += dt_seconds
        self.roi["financial_savings_vnd"] += delta_kwh * self.hospital.config["tariff_vnd_kwh"]
        self.roi["co2_reduction_kg"] += delta_kwh * self.hospital.config["emission_kg_kwh"]
        self.roi["beam_load_kw"] = beam_load
        self.roi["baseline_kw"] = baseline
        self.roi["modeled_controlled_load_kw"] = modeled_beam
        self.roi["modeled_reference_load_kw"] = modeled_reference
        self.roi["calibration_method"] = str(calibration_diag.get("method") or "COUNTERFACTUAL_STANDARD_OPS_MODEL")
        self.roi["applied_control_delta_kw"] = float(calibration_diag.get("applied_delta_kw") or 0.0)
        self.roi["raw_modeled_delta_kw"] = float(calibration_diag.get("raw_modeled_delta_kw") or 0.0)
        self.roi["modeled_control_fraction"] = float(calibration_diag.get("modeled_control_fraction") or 0.0)
        self.roi["control_eligible_end_use_fraction"] = calibration_diag.get("eligible_fraction")
        self.roi["instant_savings_percent"] = 100.0 * delta_kw / max(0.001, baseline)
        history: List[Dict[str, Any]] = self.roi["history"]
        history.append({
            "time_label": now.strftime("%H:%M:%S"),
            "beam_load_kw": round(beam_load, 2),
            "baseline_kw": round(baseline, 2),
        })
        del history[:-HISTORY_POINTS]
        peak_beam = max((float(p["beam_load_kw"]) for p in history), default=beam_load)
        peak_reference = max((float(p["baseline_kw"]) for p in history), default=baseline)
        self.roi["peak_reduction_percent"] = 100.0 * (peak_reference - peak_beam) / max(0.001, peak_reference)

    async def tick(self, dt_seconds: float = TICK_SECONDS) -> None:
        async with self._lock:
            now = datetime.now().astimezone()
            self.his.generator_enabled=self.hospital.config["mode"]=="SIMULATION"
            self.his.simulation_enabled=self.his.generator_enabled
            self.store.save_records("case_archive",{c["id"]:c for c in self.his.cases if c["status"] in {"COMPLETED","CANCELLED"}})
            generated = self.his.tick(now, self.autopilot)
            for case in generated:
                self._append_incident(
                    f"HIS intake: {case['case_label']} · {case['urgency']} · {case['specialty']} · {case['procedure']}",
                    "HIS",
                    IncidentStatus.INFO if self.autopilot else IncidentStatus.ALARM,
                )
            if self.hospital.config["mode"]=="CONNECTED":self._update_sterility(dt_seconds)
            for room in self.rooms.values():
                self._apply_room_dynamics(room, dt_seconds, now)
            self._update_sterility(dt_seconds)
            self._update_roi(dt_seconds, now)
            self._evaluate_energy_ai(now)
            self.runtime_tick(now,dt_seconds)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _room_by_id(self, room_id: Any) -> Optional[Dict[str, Any]]:
        return self.rooms.get(str(room_id)) if room_id is not None else None

    def _result(self, ok: bool, message: str, payload: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
        return {"ok": ok, "message": message, "command_id": payload.get("command_id"), "action": payload.get("action"), **extra}

    async def _legacy_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = str(payload.get("action") or "")
        actor = str(payload.get("actor") or "Frontend-Client")
        now = datetime.now().astimezone()
        try:
            if action == "TOGGLE_AUTOPILOT":
                new_state = bool(payload.get("value"))
                self.autopilot = new_state
                scheduled = self.his.schedule_all_unscheduled(now) if new_state else 0
                self._append_incident(
                    f"AI scheduler {'enabled' if new_state else 'disabled'}" + (f"; {scheduled} queued case(s) auto-scheduled" if scheduled else ""),
                    actor,
                    IncidentStatus.ACTION if new_state else IncidentStatus.ALARM,
                )
                return self._result(True, "AI scheduler enabled" if new_state else "AI scheduler disabled; unscheduled cases require manual action", payload)

            if action == "TOGGLE_ENERGY_AI":
                new_state = bool(payload.get("value"))
                self.energy_ai["enabled"] = new_state
                self._append_incident(
                    f"Energy AI supervisor {'enabled' if new_state else 'disabled'}",
                    actor,
                    IncidentStatus.ACTION,
                )
                return self._result(True, f"Energy AI {'enabled' if new_state else 'disabled'}", payload)

            if action == "APPLY_CONTROL_PROFILE":
                profile = str(payload.get("profile") or "").upper()
                config = VALID_CONTROL_PROFILES.get(profile)
                if not config:
                    return self._result(False, "Unknown HVAC/lighting control profile", payload)
                if profile == "NIGHT_SETBACK" and any(
                    room["category"] == "OPERATING_ROOM" and (room.get("active_case_id") or room.get("status") == RoomStatus.ACTIVE)
                    for room in self.rooms.values()
                ):
                    return self._result(False, "Night setback is blocked while an operating room is clinically active", payload)
                self.controls["temp_setpoint"] = float(config["temp_setpoint"])
                self.controls["rh_setpoint"] = float(config["rh_setpoint"])
                self.controls["fan_speed"] = float(config["fan_speed"])
                self.lighting["level_percent"] = int(config["lighting"])
                self._append_incident(
                    f"Clinical control profile -> {profile} (T {config['temp_setpoint']}°C, RH {config['rh_setpoint']}%, fan {config['fan_speed']}%, light {config['lighting']}%)",
                    actor,
                    IncidentStatus.ACTION,
                )
                return self._result(True, f"Control profile applied: {profile}", payload)

            if action == "SET_PRESSURE_POLICY":
                policy = str(payload.get("policy") or "").upper()
                if policy not in VALID_PRESSURE_POLICIES:
                    return self._result(False, "Pressure policy must be STANDARD or ENHANCED", payload)
                if self._pressure_fault_active:
                    return self._result(False, "Pressure policy cannot be changed while a physical pressure fault is latched", payload)
                self.sterility["positive_pressure_policy"] = policy
                self._append_incident(f"Positive-pressure control policy -> {policy}", actor, IncidentStatus.ACTION)
                return self._result(True, f"Positive-pressure policy set to {policy}", payload)

            if action == "SET_LIGHTING":
                level = int(float(payload.get("value")))
                if not 0 <= level <= 100:
                    return self._result(False, "Lighting level must be 0–100%", payload)
                self.lighting["level_percent"] = level
                self._append_incident(f"Surgical lighting level -> {level}%", actor, IncidentStatus.ACTION)
                return self._result(True, f"Lighting set to {level}%", payload)

            if action == "SET_TEMPERATURE_SETPOINT":
                value = float(payload.get("value"))
                if not 18.0 <= value <= 26.0:
                    return self._result(False, "Temperature setpoint must be 18–26°C", payload)
                self.controls["temp_setpoint"] = value
                return self._result(True, f"Temperature setpoint accepted: {value:.1f}°C", payload)

            if action == "SET_HUMIDITY_SETPOINT":
                value = float(payload.get("value"))
                if not 45.0 <= value <= 60.0:
                    return self._result(False, "Humidity setpoint must be 45–60% RH", payload)
                self.controls["rh_setpoint"] = value
                return self._result(True, f"Humidity setpoint accepted: {value:.1f}%", payload)

            if action == "SET_FAN_SPEED":
                value = float(payload.get("value"))
                if not 30.0 <= value <= 100.0:
                    return self._result(False, "AHU fan speed must be 30–100%", payload)
                self.controls["fan_speed"] = value
                return self._result(True, f"AHU fan speed accepted: {value:.1f}%", payload)

            if action == "RENAME_ROOM":
                room = self._room_by_id(payload.get("room_id"))
                if not room:
                    return self._result(False, "Unknown room", payload)
                new_name = str(payload.get("new_name") or "").strip()
                if not 1 <= len(new_name) <= 48:
                    return self._result(False, "Room name must contain 1–48 characters", payload)
                old = room["name"]
                room["name"] = new_name
                self._append_incident(f"Room display name: {old} -> {new_name}", actor, IncidentStatus.ACTION)
                return self._result(True, f"Renamed {old} to {new_name}", payload)

            if action == "SET_ROOM_MODE":
                room = self._room_by_id(payload.get("room_id"))
                if not room:
                    return self._result(False, "Unknown room", payload)
                if not room["conditioned"]:
                    return self._result(False, "This OpenStudio space is not configured as an HVAC-controlled room", payload)
                mode = str(payload.get("mode") or "")
                if mode not in VALID_ROOM_MODES:
                    return self._result(False, "Invalid room operating mode", payload)
                if room["category"] == "OPERATING_ROOM" and mode in {"MINIMUM_RUNNING", "SHUTDOWN"} and self.his.active_case_for_room(room["id"], now):
                    return self._result(False, "Minimum/Shutdown manual modes are blocked while this OR has an active surgical case", payload)
                if mode in {"MINIMUM_RUNNING","SHUTDOWN"} and any(c["status"]=="SCHEDULED" and c.get("scheduled_room_id")==room["id"] for c in self.his.cases):
                    return self._result(False,"Reschedule pending bookings before taking room offline",payload)
                room["manual_mode"] = None if mode == "BALANCE" else mode
                self._append_incident(f"{room['name']} mode -> {mode}", actor, IncidentStatus.ACTION)
                return self._result(True, f"{room['name']} mode set to {mode}", payload)

            if action == "SET_ROOM_MANUAL_TARGETS":
                room = self._room_by_id(payload.get("room_id"))
                if not room:
                    return self._result(False, "Unknown room", payload)
                if not room["conditioned"]:
                    return self._result(False, "This OpenStudio space is not configured as an HVAC-controlled room", payload)
                temp_c = float(payload.get("temp_c"))
                humidity = float(payload.get("humidity"))
                airflow_percent = float(payload.get("airflow_percent"))
                if not 18.0 <= temp_c <= 26.0:
                    return self._result(False, "Room temperature target must be 18–26°C", payload)
                if not 45.0 <= humidity <= 60.0:
                    return self._result(False, "Room humidity target must be 45–60% RH", payload)
                if not 30.0 <= airflow_percent <= 100.0:
                    return self._result(False, "Room airflow target must be 30–100% of design airflow", payload)
                room["manual_targets"] = {
                    "temp_c": round(temp_c, 1),
                    "humidity": round(humidity, 1),
                    "airflow_percent": round(airflow_percent, 1),
                }
                room["manual_mode"] = None
                self._append_incident(
                    f"{room['name']} manual targets -> T {temp_c:.1f}°C, RH {humidity:.1f}%, airflow {airflow_percent:.0f}% design",
                    actor,
                    IncidentStatus.ACTION,
                )
                return self._result(True, f"Manual room targets applied to {room['name']}", payload)

            if action == "RESET_ROOM_MANUAL_TARGETS":
                room = self._room_by_id(payload.get("room_id"))
                if not room:
                    return self._result(False, "Unknown room", payload)
                room["manual_targets"] = None
                self._append_incident(f"{room['name']} manual targets released to automatic arbitration", actor, IncidentStatus.ACTION)
                return self._result(True, f"{room['name']} returned to automatic room targets", payload)

            if action == "ADD_EXTERNAL_CASE":
                ok, message, case = self.his.add_external_case(payload, now, self.autopilot)
                if ok and case:
                    self._append_incident(
                        f"External HIS intake: {case['case_label']} · {case['urgency']} · {case['specialty']} · {case['procedure']}",
                        actor,
                        IncidentStatus.ACTION if self.autopilot else IncidentStatus.ALARM,
                    )
                return self._result(ok, message, payload, case_id=case["id"] if case else None)

            if action == "MANUAL_SCHEDULE_CASE":
                case_id = str(payload.get("case_id") or "")
                room_id = str(payload.get("room_id") or "")
                raw_start = str(payload.get("start") or "")
                if not raw_start:
                    return self._result(False, "Manual start time is required", payload)
                start = datetime.fromisoformat(raw_start)
                if start.tzinfo is None:return self._result(False,"Manual time must include timezone",payload)
                ok, message = self.his.manual_schedule_case(case_id, room_id, start, now)
                if ok:
                    self._append_incident(message, actor, IncidentStatus.ACTION)
                return self._result(ok, message, payload)

            if action == "STRESS_TEST_PRESSURE":
                self._pressure_fault_active = True
                self.sterility.update({"delta_p_pa": 0.8, "target_delta_p_pa": 0.8, "pressure_alarm": True, "control_source": "PRESSURE_FAULT"})
                self._append_incident("Pressure fault injected; sterility hard-lock engaged", actor, IncidentStatus.ALARM)
                return self._result(True, "Pressure fault injected; safety override engaged", payload)

            if action == "RESTORE_PRESSURE":
                self._pressure_fault_active = False
                if self.emergency_mode == "Immediate Smoke/Purge Mode":
                    self.emergency_mode = None
                restore_target = 3.55 if self.sterility.get("positive_pressure_policy") == "ENHANCED" else 3.2
                self.sterility.update({"delta_p_pa": restore_target, "target_delta_p_pa": restore_target, "pressure_alarm": False, "control_source": "ENHANCED_POSITIVE" if restore_target > 3.2 else "NORMAL"})
                self._append_incident("Sterility pressure restored", actor, IncidentStatus.INFO)
                return self._result(True, "Sterility pressure restored", payload)

            if action == "EMERGENCY_MODE":
                mode = str(payload.get("mode") or "")
                if mode not in VALID_EMERGENCY_MODES:
                    return self._result(False, "Invalid emergency mode", payload)
                if mode == "Negative Pressure Isolation Mode" and self._pressure_fault_active:
                    return self._result(False, "Cannot enter negative-pressure isolation while a physical pressure fault is latched", payload)
                self.emergency_mode = mode
                if mode == "Immediate Smoke/Purge Mode":
                    self.sterility["pressure_alarm"] = True
                elif mode == "Negative Pressure Isolation Mode":
                    self.sterility["pressure_alarm"] = False
                self._append_incident(f"Emergency mode activated: {mode}", actor, IncidentStatus.ALARM)
                return self._result(True, f"Emergency mode active: {mode}", payload)

            if action == "CLEAR_EMERGENCY_MODE":
                old = self.emergency_mode
                self.emergency_mode = None
                if self._pressure_fault_active:
                    self.sterility.update({"pressure_alarm": True, "target_delta_p_pa": 0.8})
                else:
                    restore_target = 3.55 if self.sterility.get("positive_pressure_policy") == "ENHANCED" else 3.2
                    self.sterility.update({"pressure_alarm": False, "delta_p_pa": restore_target, "target_delta_p_pa": restore_target, "control_source": "ENHANCED_POSITIVE" if restore_target > 3.2 else "NORMAL"})
                self._append_incident(f"Emergency mode cleared: {old or 'none'}", actor, IncidentStatus.INFO)
                return self._result(True, "Returned to normal control hierarchy", payload)

            return self._result(False, f"Unsupported action: {action}", payload)
        except (TypeError, ValueError, OverflowError, KeyError) as exc:
            return self._result(False, f"Invalid command value: {exc}", payload)

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    def _append_incident(self, description: str, actor: str, status: str) -> None:
        now = datetime.now().astimezone()
        self.incident_log.insert(
            0,
            {"id": f"{now.isoformat()}-{len(self.incident_log)}", "timestamp": now.isoformat(), "type": description, "user": actor, "status": status},
        )
        self.incident_log = self.incident_log[:100]

    def _public_room(self, room: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": room["id"],
            "name": room["name"],
            "source_name": room["source_name"],
            "category": room["category"],
            "area_m2": room["area_m2"],
            "conditioned": room["conditioned"],
            "capabilities": room["capabilities"],
            "status": room["status"],
            "occupancy": room["occupancy"],
            "surgeons": room["surgeons"],
            "power_kw": round(room["power_kw"], 2),
            "reference_power_kw": round(self._standard_reference_room_power(room, datetime.now().astimezone()), 3),
            "temp_c": round(room["temp_c"], 1),
            "humidity": round(room["humidity"], 1),
            "airflow_m3h": round(room["airflow_m3h"]),
            "max_airflow_m3h": round(room["max_airflow_m3h"]),
            "max_airflow_source": room.get("max_airflow_source", "CATEGORY_ACH_FALLBACK"),
            "calibrated_min_airflow_m3h": round(float(room.get("calibrated_min_airflow_m3h") or 0.0)),
            "lighting_design_w_m2": round(float(room.get("lighting_design_w_m2") or 0.0), 2),
            "equipment_design_w_m2": round(float(room.get("equipment_design_w_m2") or 0.0), 2),
            "fan_design_kw": round(float(room.get("fan_design_kw") or 0.0), 4),
            "fan_power_source": room.get("fan_power_source", "DIGITAL_TWIN_FALLBACK"),
            "design_people_capacity": round(float(room.get("design_people_capacity") or 0.0), 2),
            "openstudio_space_calibration": dict(room.get("openstudio_space_calibration") or {}),
            "damper_position": round(room["damper_position"]),
            "manual_mode": room["manual_mode"],
            "manual_targets": dict(room["manual_targets"]) if room.get("manual_targets") else None,
            "control_source": room["control_source"],
            "target_temp_c": room["target_temp_c"],
            "target_humidity": room["target_humidity"],
            "target_airflow_m3h": room["target_airflow_m3h"],
            "active_case_id": room["active_case_id"],
            "telemetry_source": room.get("telemetry_source","DIGITAL_TWIN_MODEL"),
            "power_density_w_m2": round((float(room["power_kw"]) * 1000.0) / max(1.0, float(room["area_m2"])), 1),
            "session_utilization_percent": round(100.0 * float(room["session_utilized_seconds"]) / max(0.001, float(room["session_observed_seconds"])), 1),
            "session_observed_seconds": round(float(room["session_observed_seconds"]), 1),
            "alarm_severity": room["alarm_severity"],
            "alarm_reasons": list(room["alarm_reasons"]),
            "trend": list(room["trend"]),
        }

    def to_dict(self, include_floorplan: bool = False) -> Dict[str, Any]:
        now = datetime.now().astimezone()
        his_state = self.his.public_state(now, self.autopilot)
        schedule = [
            {
                "id": c["id"],
                "room_id": c["scheduled_room_id"],
                "room": self.rooms[c["scheduled_room_id"]]["name"] if c.get("scheduled_room_id") in self.rooms else None,
                "procedure": c["procedure"],
                "start": c["scheduled_start"],
                "end": c["scheduled_end"],
                "urgency": c["urgency"],
                "specialty": c["specialty"],
                "status": c["status"],
            }
            for c in his_state["cases"]
            if c.get("scheduled_start") and c["status"] in {"SCHEDULED", "IN_PROGRESS"}
        ]
        schedule.sort(key=lambda e: e["start"])
        payload: Dict[str, Any] = {
            "timestamp": now.isoformat(),
            "system": {"version": BEAM_VERSION, "telemetry_contract": "beam-final-v11", "revision":self.revision,"mode":self.hospital.config["mode"], "demo":self.demo_info},
            "autopilot": self.autopilot,
            "emergency_mode": self.emergency_mode,
            "rooms": [self._public_room(r) for r in self.rooms.values()],
            "schedule": schedule,
            "his": his_state,
            "controls": dict(self.controls),
            "lighting": dict(self.lighting),
            "sterility": {k: v for k, v in {**self.sterility, "delta_p_pa": round(float(self.sterility["delta_p_pa"]), 2)}.items() if k != "trend_sample_accumulator_s"},
            "energy_ai": dict(self.energy_ai),
            "roi": {
                "source": self.hospital.config["mode"],
                "total_kwh_saved": round(self.roi["total_kwh_saved"], 4),
                "financial_savings_vnd": round(self.roi["financial_savings_vnd"], 0),
                "co2_reduction_kg": round(self.roi["co2_reduction_kg"], 4),
                "beam_load_kw": round(self.roi["beam_load_kw"], 2),
                "baseline_kw": round(self.roi["baseline_kw"], 2),
                "modeled_controlled_load_kw": round(self.roi["modeled_controlled_load_kw"], 2),
                "modeled_reference_load_kw": round(self.roi["modeled_reference_load_kw"], 2),
                "calibration_method": self.roi["calibration_method"],
                "applied_control_delta_kw": round(self.roi["applied_control_delta_kw"], 3),
                "raw_modeled_delta_kw": round(self.roi["raw_modeled_delta_kw"], 3),
                "modeled_control_fraction": round(self.roi["modeled_control_fraction"], 5),
                "control_eligible_end_use_fraction": self.roi["control_eligible_end_use_fraction"],
                "instant_savings_percent": round(self.roi["instant_savings_percent"], 2),
                "peak_reduction_percent": round(self.roi["peak_reduction_percent"], 2),
                "total_beam_kwh": round(self.roi["total_beam_kwh"], 4),
                "total_reference_kwh": round(self.roi["total_reference_kwh"], 4),
                "session_seconds": round(self.roi["session_seconds"], 1),
                "conditioned_floor_area_m2": self._conditioned_floor_area_m2,
                "baseline_provenance": self.energy_baseline.public_dict(),
                "history": list(self.roi["history"]),
            },
            "incident_log": list(self.incident_log),
        }
        if include_floorplan:
            payload["floorplan"] = self.floorplan.public_dict()
        return payload
