"""Hospital registry and shared operational constraints. Seed records are synthetic."""

import math
import secrets
from datetime import datetime, date, timedelta, timezone
from statistics import median
from his_engine import PROCEDURES

CORE_DEVICES = {"ANESTHESIA_MACHINE", "PATIENT_MONITOR", "SURGICAL_TABLE"}
DEFAULT_CONFIG = {
    "mode": "SIMULATION",
    "timezone": "Asia/Ho_Chi_Minh",
    "tariff_vnd_kwh": 2200.0,
    "emission_kg_kwh": 0.7221,
    "capex_vnd": 0.0,
    "annual_opex_vnd": 0.0,
    "sensor_timeout_seconds": 30,
    "auto_assign_team": True,
}


def number(v, label, low=0, high=1e12):
    if (
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not low <= v <= high
    ):
        raise ValueError(f"{label} must be a finite number between {low} and {high}")
    return float(v)


def text(v, label, limit=160, required=True):
    if not isinstance(v, str) or len(v.strip()) > limit or (required and not v.strip()):
        raise ValueError(f"{label}: expected text up to {limit} characters")
    return v.strip()


def aware(v):
    d = datetime.fromisoformat(v) if isinstance(v, str) else v
    if not isinstance(d, datetime) or d.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return d


class Hospital:
    def __init__(self, state):
        self.state = state
        self.store = state.store
        self.config = {**DEFAULT_CONFIG, **self.store.get("config", {})}
        for kind in ("patients", "staff", "devices", "outcomes"):
            setattr(self, kind, self.store.records(kind))
        self.thermal = self.store.get("thermal", {})
        self.meters = {}
        self.actuation = {}
        if not self.store.get("seeded"):
            for i, r in enumerate(state.floorplan.operating_rooms(), 1):
                for role in ("SURGEON", "ANESTHESIOLOGIST", "NURSE"):
                    key = f"demo-{role}-{i}"
                    self.staff[key] = {
                        "id": key,
                        "staff_code": key,
                        "name": f"Demo {role.title()} {i}",
                        "role": role,
                        "specialties": r["capabilities"],
                        "active": True,
                        "unavailable": [],
                        "is_demo": True,
                    }
                for kind in sorted(CORE_DEVICES):
                    key = f"demo-{i}-{kind}"
                    self.devices[key] = {
                        "id": key,
                        "asset_tag": key,
                        "name": "Demo " + kind.replace("_", " ").title(),
                        "type": kind,
                        "room_id": r["id"],
                        "status": "AVAILABLE",
                        "commissioned_on": date.today().isoformat(),
                        "design_life_hours": 20000.0,
                        "runtime_hours": 0.0,
                        "maintenance_interval_hours": 1000.0,
                        "last_service_hours": 0.0,
                        "inspection_efficiency_percent": None,
                        "inspection_passed": None,
                        "inspected_at": None,
                        "service_history": [],
                        "is_demo": True,
                    }
            self.store.put("seeded", True)
            self.persist()

    def persist(self):
        self.store.put("config", self.config)
        self.store.put("thermal", self.thermal)
        for kind in ("patients", "staff", "devices", "outcomes"):
            self.store.save_records(kind, getattr(self, kind))

    def upsert(self, kind, data):
        allowed = {
            "patients": {
                "id",
                "mrn",
                "name",
                "date_of_birth",
                "sex",
                "asa_class",
                "allergies",
                "conditions",
                "notes",
                "active",
            },
            "staff": {
                "id",
                "staff_code",
                "name",
                "role",
                "specialties",
                "unavailable",
                "active",
            },
            "devices": {
                "id",
                "asset_tag",
                "name",
                "room_id",
                "type",
                "status",
                "commissioned_on",
                "design_life_hours",
                "runtime_hours",
                "maintenance_interval_hours",
                "last_service_hours",
            },
        }
        if (
            not isinstance(data, dict)
            or kind not in allowed
            or set(data) - allowed[kind]
        ):
            raise ValueError("Invalid registry record or unknown field")
        records = getattr(self, kind)
        key = data.get("id") or kind[:3] + "-" + secrets.token_hex(6)
        old = records.get(key)
        if data.get("id") and not old:
            raise ValueError("Record not found")
        active = [c for c in self.state.his.cases if c["status"] == "IN_PROGRESS"]
        if (
            old
            and kind == "devices"
            and any(c.get("scheduled_room_id") == old["room_id"] for c in active)
        ):
            raise ValueError("Cannot edit device inventory during an active case")
        if (
            old
            and kind == "staff"
            and any(key in c.get("staff_ids", []) for c in active)
        ):
            raise ValueError("Cannot edit assigned staff during an active case")
        if (
            old
            and kind == "patients"
            and data.get("active") is False
            and any(c.get("patient_id") == key for c in active)
        ):
            raise ValueError("Cannot deactivate the patient of an active case")
        v = {
            **(old or {}),
            **data,
            "id": key,
            "is_demo": self.state.demo_enabled or bool(old and old.get("is_demo")),
        }
        v["name"] = text(v.get("name"), "Name")
        unique = {"patients": "mrn", "staff": "staff_code", "devices": "asset_tag"}[
            kind
        ]
        v[unique] = text(v.get(unique), unique, 80)
        if any(
            r["id"] != key and r.get(unique, "").casefold() == v[unique].casefold()
            for r in records.values()
        ):
            raise ValueError(unique + " already exists")
        if kind == "patients":
            dob = date.fromisoformat(v.get("date_of_birth", ""))
            if not date(1900, 1, 1) <= dob <= date.today():
                raise ValueError("Invalid birth date")
            if v.get("sex") not in {"UNKNOWN", "FEMALE", "MALE", "OTHER"}:
                raise ValueError("Invalid sex")
            for f in ("allergies", "conditions", "notes"):
                v[f] = text(v.get(f, ""), f, 1000, False)
            if v.get("asa_class") is not None:
                if type(v["asa_class"]) is not int or not 1 <= v["asa_class"] <= 6:
                    raise ValueError("ASA class must be an integer 1 to 6")
        if kind == "staff":
            if v.get("role") not in {"SURGEON", "ANESTHESIOLOGIST", "NURSE"}:
                raise ValueError("Invalid role")
            if not isinstance(v.get("specialties"), list) or any(
                s not in PROCEDURES for s in v["specialties"]
            ):
                raise ValueError("Invalid specialties")
            windows = v.get("unavailable", [])
            if not isinstance(windows, list) or len(windows) > 100:
                raise ValueError("Invalid unavailable windows")
            for w in windows:
                if not isinstance(w, dict) or aware(w.get("end")) <= aware(
                    w.get("start")
                ):
                    raise ValueError("Invalid unavailable interval")
            v["unavailable"] = windows
        if kind != "devices":
            v.setdefault("active", True)
            if type(v["active"]) is not bool:
                raise ValueError("Active must be boolean")
        else:
            if v.get("room_id") not in self.state.rooms:
                raise ValueError("Unknown room")
            if v.get("status") not in {
                "AVAILABLE",
                "MAINTENANCE",
                "OFFLINE",
                "RETIRED",
            }:
                raise ValueError("Invalid asset status")
            v["type"] = text(v.get("type"), "Device type", 80).upper()
            if date.fromisoformat(v.get("commissioned_on", "")) > date.today():
                raise ValueError("Future commissioning date")
            for f, lo, hi in (
                ("design_life_hours", 1, 1e7),
                ("runtime_hours", 0, 1e7),
                ("maintenance_interval_hours", 1, 1e6),
                ("last_service_hours", 0, 1e7),
            ):
                v[f] = number(v.get(f, 0), f, lo, hi)
            if v["last_service_hours"] > v["runtime_hours"]:
                raise ValueError("Service reading exceeds runtime")
            if old and v["runtime_hours"] < old["runtime_hours"]:
                raise ValueError("Runtime cannot decrease")
            if old and v["last_service_hours"] != old["last_service_hours"]:
                raise ValueError(
                    "Use SERVICE_DEVICE to advance the maintenance reading"
                )
            for f, default in (
                ("service_history", []),
                ("inspection_efficiency_percent", None),
                ("inspection_passed", None),
                ("inspected_at", None),
            ):
                v[f] = (old or {}).get(f, default)
        records[key] = v
        return key

    def prepare_case(self, c, now):
        if self.state.demo_enabled:
            c["is_demo"] = True
        if c["source"] == "HIS_RANDOM" and not c.get("patient_id"):
            key = "demo-patient-" + c["id"]
            self.patients[key] = {
                "id": key,
                "name": "Demo patient " + c["case_label"],
                "mrn": key,
                "date_of_birth": "1980-01-01",
                "sex": "UNKNOWN",
                "allergies": "Synthetic record",
                "conditions": "",
                "notes": "No real patient data",
                "active": True,
                "is_demo": True,
            }
            c.update(patient_id=key, consent_confirmed=True, preop_complete=True)
        c.setdefault("staff_ids", [])
        c.setdefault("required_device_types", sorted(CORE_DEVICES))
        if not CORE_DEVICES.issubset(set(c["required_device_types"])):
            raise ValueError("Core OR device requirements cannot be removed")
        c.setdefault("consent_confirmed", False)
        c.setdefault("preop_complete", False)
        c.setdefault("clinical_estimate", None)
        if self.state.demo_enabled:
            from demo_pack import enrich_case

            enrich_case(self.state, c, now)

    def device_public(self, d):
        remaining = max(0, d["design_life_hours"] - d["runtime_hours"])
        maintenance = d["maintenance_interval_hours"] - (
            d["runtime_hours"] - d["last_service_hours"]
        )
        ready = (
            d["status"] == "AVAILABLE"
            and remaining > 0
            and maintenance > 0
            and (
                self.config["mode"] == "SIMULATION"
                or (
                    d.get("inspection_passed") is True
                    and d.get("inspection_source") == "CONNECTED"
                )
            )
        )
        engineering = self.state.v11.device(d) if hasattr(self.state, "v11") else {}
        ready = (
            ready
            and not engineering.get("performance_below_limit", False)
            and not engineering.get("calendar_expired", False)
        )
        return {
            **d,
            "remaining_life_hours": remaining,
            "remaining_life_percent": 100 * remaining / d["design_life_hours"],
            "maintenance_in_hours": maintenance,
            "maintenance_due": maintenance <= 0,
            "ready": ready,
            "engineering": engineering,
            "lifecycle_method": "Declared design-life minus runtime; not failure probability",
        }

    def block_end(self, c):
        end = c["scheduled_end"] + timedelta(minutes=18)
        if (
            c["status"] in {"SCHEDULED", "IN_PROGRESS"}
            and c["source"] != "HIS_RANDOM"
            and c["scheduled_start"] <= datetime.now(timezone.utc)
        ):
            end = max(
                end,
                datetime.now(timezone.utc)
                + timedelta(minutes=c["estimated_duration_min"] + 18),
            )
        return end

    def staff_free(self, p, c, start, end):
        if any(
            start < aware(w["end"]) and end > aware(w["start"])
            for w in p.get("unavailable", [])
        ):
            return False
        for other in self.state.his.cases:
            if (
                other["id"] == c["id"]
                or other["status"] in {"UNSCHEDULED", "CANCELLED"}
                or not other.get("scheduled_start")
            ):
                continue
            if (
                p["id"] in other.get("staff_ids", [])
                and start < self.block_end(other)
                and end
                > other["scheduled_start"] - timedelta(minutes=other["prep_minutes"])
            ):
                return False
        return True

    def team(self, c, start, end):
        chosen = list(c.get("staff_ids", []))
        if self.config["auto_assign_team"]:
            for role in ("SURGEON", "ANESTHESIOLOGIST", "NURSE"):
                if any(self.staff.get(i, {}).get("role") == role for i in chosen):
                    continue
                available = [
                    p
                    for p in self.staff.values()
                    if p.get("active")
                    and p["role"] == role
                    and (role != "SURGEON" or c["specialty"] in p["specialties"])
                    and (self.config["mode"] != "CONNECTED" or not p.get("is_demo"))
                    and self.staff_free(p, c, start, end)
                ]
                if not available:
                    return None, "No available " + role.lower()
                chosen.append(sorted(available, key=lambda p: p["id"])[0]["id"])
        people = [self.staff.get(i) for i in chosen]
        if len(set(chosen)) != len(chosen) or any(
            not p or not p.get("active") for p in people
        ):
            return None, "Unknown, duplicate or inactive staff"
        if not {"SURGEON", "ANESTHESIOLOGIST", "NURSE"}.issubset(
            {p["role"] for p in people}
        ):
            return None, "Assign complete clinical team"
        if not any(
            p["role"] == "SURGEON" and c["specialty"] in p["specialties"]
            for p in people
        ):
            return None, "Surgeon specialty mismatch"
        if self.config["mode"] == "CONNECTED" and any(p.get("is_demo") for p in people):
            return None, "Synthetic staff in connected mode"
        for p in people:
            if not self.staff_free(p, c, start, end):
                return None, "Staff conflict: " + p["name"]
        return chosen, None

    def slot_check(self, c, room_id, start, end, commit=False):
        r = self.state.rooms[room_id]
        if r["manual_mode"] in {"SHUTDOWN", "MINIMUM_RUNNING"}:
            return False, "Room unavailable: manual maintenance/minimum mode"
        if self.state._pressure_fault_active:
            return False, "Physical pressure fault"
        for a, b in self.state.his._scheduled_intervals(room_id, c["id"]):
            if not (
                end + timedelta(minutes=18) <= a or start >= b + timedelta(minutes=18)
            ):
                return False, "OR conflict or turnover window"
        patient = self.patients.get(c.get("patient_id"))
        if not patient or not patient.get("active"):
            return False, "Assign an active patient"
        if self.config["mode"] == "CONNECTED" and (
            patient.get("is_demo") or c["source"] == "HIS_RANDOM"
        ):
            return False, "Synthetic case/patient in connected mode"
        prep = start - timedelta(minutes=c["prep_minutes"])
        discharge = end + timedelta(minutes=c["recovery_minutes"])
        for other in self.state.his.cases:
            if (
                other["id"] == c["id"]
                or other["status"] in {"UNSCHEDULED", "CANCELLED"}
                or not other.get("scheduled_start")
            ):
                continue
            other_end = max(
                other["scheduled_end"], self.block_end(other) - timedelta(minutes=18)
            )
            if (
                other.get("patient_id") == c.get("patient_id")
                and prep < other_end + timedelta(minutes=other["recovery_minutes"])
                and discharge
                > other["scheduled_start"] - timedelta(minutes=other["prep_minutes"])
            ):
                return False, "Patient already booked in prep, OR or recovery"
        team, reason = self.team(c, prep, end + timedelta(minutes=18))
        if reason:
            return False, reason
        assets = [
            self.device_public(d)
            for d in self.devices.values()
            if d["room_id"] == room_id
            and (self.config["mode"] != "CONNECTED" or not d.get("is_demo"))
        ]
        for kind in c.get("required_device_types", CORE_DEVICES):
            if not any(
                d["type"] == kind
                and d["ready"]
                and min(d["remaining_life_hours"], d["maintenance_in_hours"])
                >= (end - start).total_seconds() / 3600
                for d in assets
            ):
                return False, "Required device unavailable or due service: " + kind
        support = {}
        for field, categories, a, b in (
            ("prep_room_id", {"PREP", "PREOP"}, prep, start),
            ("recovery_room_id", {"RECOVERY"}, end, discharge),
        ):
            candidates = sorted(
                [
                    r
                    for r in self.state.floorplan.rooms
                    if r["category"] in categories
                    and self.state.rooms[r["id"]]["manual_mode"]
                    not in {"SHUTDOWN", "MINIMUM_RUNNING"}
                ],
                key=lambda r: self.state.floorplan.graph_distance(room_id, r["id"]),
            )
            for room in candidates:
                busy = False
                for other in self.state.his.cases:
                    if (
                        other["id"] == c["id"]
                        or other["status"] in {"UNSCHEDULED", "CANCELLED"}
                        or other.get(field) != room["id"]
                        or not other.get("scheduled_start")
                    ):
                        continue
                    oa, ob = (
                        (
                            other["scheduled_start"]
                            - timedelta(minutes=other["prep_minutes"]),
                            other["scheduled_start"],
                        )
                        if field == "prep_room_id"
                        else (
                            other["scheduled_end"],
                            other["scheduled_end"]
                            + timedelta(minutes=other["recovery_minutes"]),
                        )
                    )
                    if a < ob and b > oa:
                        busy = True
                        break
                if not busy:
                    support[field] = room["id"]
                    break
            if field not in support:
                return False, "No free " + field.replace("_id", "") + " capacity"
        if commit:
            c.update(staff_ids=team, **support)
        return True, "Room, patient, team, devices and support capacity validated"

    def fresh(self, scope, now):
        sample = self.meters.get(scope)
        return bool(
            sample
            and 0
            <= (now - aware(sample["timestamp"])).total_seconds()
            <= self.config["sensor_timeout_seconds"]
        )

    def readiness(self, c, now):
        room = self.state.rooms.get(c.get("scheduled_room_id"))
        checks = [
            {"label": "Patient assigned", "ok": c.get("patient_id") in self.patients},
            {"label": "Consent confirmed", "ok": bool(c.get("consent_confirmed"))},
            {"label": "Preoperative checklist", "ok": bool(c.get("preop_complete"))},
            {"label": "OR assigned", "ok": bool(room)},
        ]
        if room:
            checks.extend(
                [
                    {
                        "label": "Temperature within 1.5°C of target",
                        "ok": abs(room["temp_c"] - room["target_temp_c"]) <= 1.5,
                    },
                    {
                        "label": "RH within 5% of target",
                        "ok": abs(room["humidity"] - room["target_humidity"]) <= 5,
                    },
                    {
                        "label": "Airflow at least 82% of design",
                        "ok": room["airflow_m3h"] >= 0.82 * room["max_airflow_m3h"],
                    },
                    {
                        "label": "Pressure alarm clear",
                        "ok": not self.state.sterility["pressure_alarm"]
                        and not self.state._pressure_fault_active,
                    },
                ]
            )
            start = max(now, c.get("scheduled_start") or now)
            ok, reason = self.slot_check(
                c,
                room["id"],
                start,
                start + timedelta(minutes=c["estimated_duration_min"]),
            )
            checks.append({"label": reason, "ok": ok})
            if self.config["mode"] == "CONNECTED":
                checks.append(
                    {"label": "Fresh BMS telemetry", "ok": self.fresh(room["id"], now)}
                )
        count = sum(bool(x["ok"]) for x in checks)
        return {
            "score": round(100 * count / len(checks)),
            "ready": count == len(checks),
            "checks": checks,
            "method": "Operational checklist; not clinical success probability",
        }

    def clinical(self, c):
        demo = self.state.demo_enabled and self.config["mode"] == "SIMULATION"
        cohort = [
            o
            for o in self.outcomes.values()
            if o["procedure"] == c["procedure"] and bool(o.get("is_demo")) == demo
        ]
        n = len(cohort)
        stats = None
        if n >= 30:
            p = sum(o["success"] for o in cohort) / n
            z = 1.96
            den = 1 + z * z / n
            center = (p + z * z / (2 * n)) / den
            spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
            stats = {
                "source": "SIMULATION" if demo else "CLINICAL_FOLLOWUP",
                "cases": n,
                "observed_rate_percent": round(100 * p, 1),
                "interval_95_percent": [
                    round(100 * (center - spread), 1),
                    round(100 * (center + spread), 1),
                ],
            }
        prediction = (
            self.state.v11.models.assessment(c, datetime.now(timezone.utc))
            if hasattr(self.state, "v11")
            else {}
        )
        return {
            "prediction_status": "VALIDATED_MODEL_REQUIRED",
            "predicted_success_percent": None,
            "cohort_count": n,
            "cohort": stats,
            "clinician_estimate": c.get("clinical_estimate"),
            "recorded_predictions": self.state.v11.data.get("predictions", {}).get(
                c["id"], []
            )[-20:],
            "endpoint": "No major complication within 30 days",
            "reference_url": "https://riskcalculator.facs.org/RiskCalculator/",
            "reason": "No validated procedure-specific clinical model is installed. Unadjusted cohort statistics are not individual predictions.",
            **prediction,
        }

    def observe(self, now, dt):
        for d in self.devices.values():
            if (
                self.config["mode"] == "SIMULATION"
                and d["status"] == "AVAILABLE"
                and self.state.his.active_case_for_room(d["room_id"], now)
            ):
                d["runtime_hours"] += dt / 3600
                d["runtime_source"] = "SIMULATED_CASE_OCCUPANCY"
        for r in self.state.rooms.values():
            if self.config["mode"] == "CONNECTED" and not self.fresh(r["id"], now):
                continue
            prior = self.thermal.get(r["id"], {"samples": 0, "cooling_c_per_min": 0.0})
            if prior.get("at"):
                elapsed = (now - aware(prior["at"])).total_seconds()
                if 0 < elapsed <= 10 and r["airflow_m3h"] > 0.5 * r["max_airflow_m3h"]:
                    rate = (prior["temp_c"] - r["temp_c"]) * 60 / elapsed
                    if 0.001 < rate < 2:
                        prior["cooling_c_per_min"] = (
                            0.9 * prior.get("cooling_c_per_min", rate) + 0.1 * rate
                        )
                        prior["samples"] += 1
            prior.update(at=now.isoformat(), temp_c=r["temp_c"])
            self.thermal[r["id"]] = prior

    def insights(self, now):
        traits = []
        for r in self.state.rooms.values():
            if r["category"] != "OPERATING_ROOM":
                continue
            t = self.thermal.get(r["id"], {})
            rate = t.get("cooling_c_per_min", 0)
            eta = (
                max(0, r["temp_c"] - self.state.controls["temp_setpoint"]) / rate
                if rate > 0.001 and t.get("samples", 0) >= 10
                else None
            )
            next_case = self.state.his.next_case_for_room(r["id"], now)
            traits.append(
                {
                    "room_id": r["id"],
                    "room_name": r["name"],
                    "samples": t.get("samples", 0),
                    "cooling_c_per_min": rate,
                    "ready_eta_minutes": eta,
                    "next_case_id": next_case["id"] if next_case else None,
                    "source": self.config["mode"],
                    "sensor_fresh": self.fresh(r["id"], now),
                    "method": "EWMA cooldown; similar-load extrapolation",
                }
            )
        completed = {
            **self.store.records("case_archive"),
            **{c["id"]: c for c in self.state.his.cases},
        }
        groups = {}
        for c in completed.values():
            if (
                c.get("actual_start")
                and c.get("actual_end")
                and (
                    self.state.demo_enabled
                    and bool(c.get("is_demo"))
                    or c["source"] != "HIS_RANDOM"
                    and not c.get("is_demo")
                )
            ):
                minutes = (
                    aware(c["actual_end"]) - aware(c["actual_start"])
                ).total_seconds() / 60
                if minutes > 0:
                    groups.setdefault(c["procedure"], []).append(minutes)
        durations = [
            {
                "procedure": p,
                "source": (
                    "SIMULATION" if self.state.demo_enabled else "CONFIRMED_CASES"
                ),
                "cases": len(v),
                "median_minutes": median(v),
                "suggested_buffered_minutes": math.ceil(
                    sorted(v)[min(len(v) - 1, math.ceil(0.8 * len(v)) - 1)]
                ),
                "eligible": len(v) >= 5,
            }
            for p, v in groups.items()
        ]
        return {
            "room_traits": traits,
            "duration_traits": durations,
            "case_assessments": [
                {
                    "case_id": c["id"],
                    "readiness": self.readiness(c, now),
                    "clinical": self.clinical(c),
                }
                for c in self.state.his.cases
                if c["status"] not in {"CANCELLED", "COMPLETED"}
            ],
            "model_status": "EXPLAINABLE_RULES_AND_ONLINE_STATISTICS",
            "clinical_model_status": (
                "REGISTRY_CONFIGURED"
                if self.state.v11.models.models
                else "NOT_INSTALLED"
            ),
            "v11_model_count": len(self.state.v11.models.models),
        }

    def public(self):
        return {
            "demo": self.state.demo_info,
            "config": self.config,
            "patients": list(self.patients.values()),
            "staff": list(self.staff.values()),
            "devices": [self.device_public(d) for d in self.devices.values()],
            "outcome_count": len(self.outcomes),
            "required_device_types": sorted(CORE_DEVICES),
            "integration": {
                "mode": self.config["mode"],
                "actuator_receipts": list(
                    self.state.v11.data.get("receipts", {}).values()
                ),
            },
        }
