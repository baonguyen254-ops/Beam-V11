"""v10 persistence, command arbitration, lifecycle and integrations."""

import copy
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from hospital import Hospital, number, text, aware, CORE_DEVICES
from storage import encode
from operations_v11 import OperationsV11, ADMIN_ACTIONS, CLINICAL_ACTIONS

DATES = {
    "created_at",
    "latest_start_at",
    "scheduled_start",
    "scheduled_end",
    "actual_start",
    "actual_end",
}
ADMIN = {"SET_HOSPITAL_CONFIG", "UPSERT_STAFF", "UPSERT_DEVICE", "SERVICE_DEVICE"}
ADMIN |= ADMIN_ACTIONS
CLINICAL = {
    "UPSERT_PATIENT",
    "ASSIGN_CASE",
    "UPDATE_CASE",
    "ADD_EXTERNAL_CASE",
    "MANUAL_SCHEDULE_CASE",
    "CANCEL_CASE",
    "START_CASE",
    "COMPLETE_CASE",
    "RECORD_OUTCOME",
    "RECORD_CLINICAL_ESTIMATE",
}
CLINICAL |= CLINICAL_ACTIONS


def validate(p):
    if not isinstance(p, dict):
        raise ValueError("Command must be an object")

    def visit(v, depth=0):
        if depth > 7:
            raise ValueError("Command nesting limit")
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("Non-finite numbers are forbidden")
        if isinstance(v, str) and len(v) > 5000:
            raise ValueError("Text too long")
        if isinstance(v, list):
            if len(v) > 500:
                raise ValueError("List too long")
            for x in v:
                visit(x, depth + 1)
        if isinstance(v, dict):
            if len(v) > 100:
                raise ValueError("Too many fields")
            for x in v.values():
                visit(x, depth + 1)

    visit(p)
    action = text(p.get("action"), "Action", 80)
    for f in (
        "command_id",
        "actor",
        "room_id",
        "case_id",
        "patient_id",
        "mode",
        "profile",
        "policy",
        "start",
        "procedure",
        "specialty",
        "urgency",
        "case_label",
        "notes",
    ):
        if f in p:
            text(p[f], f, 1000, False)
    for f in ("staff_ids", "required_device_types"):
        if f in p and (
            not isinstance(p[f], list) or any(not isinstance(x, str) for x in p[f])
        ):
            raise ValueError(f + " must be an identifier list")
    for f in ("consent_confirmed", "preop_complete"):
        if f in p and type(p[f]) is not bool:
            raise ValueError(f + " must be boolean")
    if (
        action in {"TOGGLE_AUTOPILOT", "TOGGLE_ENERGY_AI"}
        and type(p.get("value")) is not bool
    ):
        raise ValueError("Toggle value must be boolean")
    if action.startswith("SET_") and "value" in p:
        number(p["value"], "value", -1e6, 1e6)
    for f in ("temp_c", "humidity", "airflow_percent"):
        if f in p:
            number(p[f], f, -1e6, 1e6)
    for f, lo, hi in (
        ("estimated_duration_min", 15, 480),
        ("prep_minutes", 5, 90),
        ("recovery_minutes", 15, 240),
    ):
        if f in p and (type(p[f]) is not int or not lo <= p[f] <= hi):
            raise ValueError(f"{f} must be integer {lo} to {hi}")


class RuntimeMixin:
    def initialize_runtime(self):
        self.revision = 0
        self.last_checkpoint = 0
        if self.demo_enabled and self.store.get("config", {}).get("mode", "SIMULATION") != "SIMULATION":
            raise ValueError("Demo requires its own simulation workspace; use --standard for connected data")
        self.hospital = Hospital(self)
        self.v11 = OperationsV11(self)
        self.his.prepare_case_hook = self.hospital.prepare_case
        self.his.slot_check_hook = self.hospital.slot_check
        saved = self.store.get("snapshot")
        if saved:
            self.restore_snapshot(saved)
            # Gateway receipts may be committed between full snapshots.
            self.v11.data = self.store.get("v11", self.v11.data)
        elif self.hospital.config["mode"] == "SIMULATION" and not self.demo_enabled:
            self.his._bootstrap()
        if self.demo_enabled:
            from demo_pack import activate

            activate(self, datetime.now(timezone.utc))
        self.restore_source_roi()
        if self.demo_enabled:
            from demo_pack import warm_charts

            warm_charts(self, datetime.now(timezone.utc))
        if self.hospital.config["mode"] == "CONNECTED":
            self.archive_simulated_cases()
        self.checkpoint()
        self.store.db.commit()

    def restore_source_roi(self):
        source = self.hospital.config["mode"]
        row = self.store.db.execute(
            "SELECT SUM(actual) a,SUM(baseline) b,SUM(cost) cost,SUM(carbon) carbon,SUM(seconds) seconds FROM energy_by_source WHERE tier=3600 AND scope=? AND source=?",
            ("facility", source),
        ).fetchone()
        if self.roi.get("ledger_source") != source:
            self.roi["history"] = []
            self.roi["beam_load_kw"] = 0.0
            self.roi["instant_savings_percent"] = 0.0
            self.roi["peak_reduction_percent"] = 0.0
        self.roi.update(
            ledger_source=source,
            total_beam_kwh=float(row["a"] or 0),
            total_reference_kwh=float(row["b"] or 0),
            total_kwh_saved=float(row["b"] or 0) - float(row["a"] or 0),
            financial_savings_vnd=float(row["cost"] or 0),
            co2_reduction_kg=float(row["carbon"] or 0),
            session_seconds=float(row["seconds"] or 0),
        )

    def archive_simulated_cases(self):
        demos = {c["id"]: c for c in self.his.cases if c["source"] == "HIS_RANDOM"}
        for c in demos.values():
            if c["status"] not in {"COMPLETED", "CANCELLED"}:
                c.update(
                    status="CANCELLED",
                    notes="Simulation ended before connected operation",
                )
        self.store.save_records("case_archive", demos)
        self.his.cases = [c for c in self.his.cases if c["source"] != "HIS_RANDOM"]

    def snapshot(self):
        return {
            "v11": self.v11.data,
            "controls": self.controls,
            "autopilot": self.autopilot,
            "emergency_mode": self.emergency_mode,
            "pressure_fault": self._pressure_fault_active,
            "sterility": self.sterility,
            "roi": self.roi,
            "lighting": self.lighting["level_percent"],
            "energy_ai_enabled": self.energy_ai["enabled"],
            "cases": self.his.cases,
            "incidents": self.incident_log,
            "revision": self.revision,
            "total_generated": self.his.total_generated,
            "total_external": self.his.total_external,
            "rooms": {
                k: {f: r[f] for f in ("name", "manual_mode", "manual_targets")}
                for k, r in self.rooms.items()
            },
        }

    def restore_snapshot(self, s):
        if "v11" in s:
            self.v11.data = s["v11"]
        for f in (
            "controls",
            "autopilot",
            "emergency_mode",
            "sterility",
            "roi",
            "revision",
        ):
            if f in s:
                setattr(self, f, s[f])
        self._pressure_fault_active = s.get("pressure_fault", False)
        self.lighting["level_percent"] = s.get("lighting", 70)
        self.energy_ai["enabled"] = s.get("energy_ai_enabled", True)
        self.his.cases = s.get("cases", [])
        for c in self.his.cases:
            for f in DATES:
                if c.get(f):
                    c[f] = aware(c[f])
        self.his.total_generated = s.get("total_generated", 0)
        self.his.total_external = s.get("total_external", 0)
        self.incident_log = s.get("incidents", [])
        for key, config in s.get("rooms", {}).items():
            if key in self.rooms:
                self.rooms[key].update(config)

    def checkpoint(self):
        self.store.put("v11", self.v11.data)
        self.store.put("snapshot", self.snapshot())
        self.store.save_records(
            "case_archive",
            {
                c["id"]: c
                for c in self.his.cases
                if c["status"] in {"COMPLETED", "CANCELLED"}
            },
        )
        self.hospital.persist()

    def runtime_tick(self, now, dt):
        self.hospital.observe(now, dt)
        self.v11.observe(now)
        connected = self.hospital.config["mode"] == "CONNECTED"
        samples = []
        if not connected or self.hospital.fresh("facility", now):
            samples.append(
                (
                    "facility",
                    self.roi["beam_load_kw"],
                    self.roi["baseline_kw"],
                    connected,
                )
            )
        for r in self.rooms.values():
            if not connected or self.hospital.fresh(r["id"], now):
                samples.append(
                    (
                        r["id"],
                        r["power_kw"],
                        self._standard_reference_room_power(r, now),
                        connected,
                    )
                )
        self.store.record_energy(
            now,
            dt,
            samples,
            self.hospital.config["tariff_vnd_kwh"],
            self.hospital.config["emission_kg_kwh"],
        )
        self.revision += 1
        if now.timestamp() - self.last_checkpoint >= 10:
            self.checkpoint()
            self.last_checkpoint = now.timestamp()
        self.store.db.commit()

    async def handle_command(self, p):
        async with self._lock:
            actor = (
                str(p.get("actor", "LOCAL_TEST")) if isinstance(p, dict) else "UNKNOWN"
            )
            before = None
            registries = None
            try:
                validate(p)
                action = p["action"]
                role = p.get("_role", "ADMIN")
                cid = p.get("command_id")
                if (
                    role == "VIEWER"
                    or action in ADMIN
                    and role != "ADMIN"
                    or action in CLINICAL
                    and role not in {"ADMIN", "CLINICIAN"}
                ):
                    raise ValueError("Your role does not permit this operation")
                fingerprint = hashlib.sha256(
                    encode(
                        {
                            k: v
                            for k, v in p.items()
                            if k not in {"command_id", "actor", "_role"}
                        }
                    ).encode()
                ).hexdigest()
                if cid:
                    row = self.store.db.execute(
                        "SELECT fingerprint,result FROM commands WHERE actor=? AND id=?",
                        (actor, cid),
                    ).fetchone()
                    if row:
                        if row["fingerprint"] != fingerprint:
                            raise ValueError(
                                "Command ID already used with different content"
                            )
                        return {**json.loads(row["result"]), "replayed": True}
                before = copy.deepcopy(self.snapshot())
                registries = {
                    k: copy.deepcopy(getattr(self.hospital, k))
                    for k in (
                        "config",
                        "patients",
                        "staff",
                        "devices",
                        "outcomes",
                        "thermal",
                    )
                }
                result = self.hospital_command(p)
                if result is None:
                    result = await self._legacy_command(p)
                self.revision += 1
                self.store.audit(
                    actor,
                    action,
                    result["ok"],
                    encode(
                        {
                            "message": result["message"],
                            "case_id": result.get("case_id") or p.get("case_id"),
                            "record_id": result.get("record_id"),
                            "room_id": p.get("room_id"),
                        }
                    ),
                )
                if cid:
                    self.store.db.execute(
                        "INSERT INTO commands VALUES(?,?,?,?)",
                        (actor, cid, fingerprint, encode(result)),
                    )
                self.checkpoint()
                self.store.db.commit()
                return result
            except (
                TypeError,
                ValueError,
                KeyError,
                OverflowError,
                sqlite3.Error,
            ) as exc:
                self.store.db.rollback()
                if before:
                    self.restore_snapshot(before)
                    for k, v in registries.items():
                        setattr(self.hospital, k, v)
                result = self._result(False, str(exc), p if isinstance(p, dict) else {})
                try:
                    self.store.audit(
                        actor,
                        (
                            str(p.get("action", "INVALID"))
                            if isinstance(p, dict)
                            else "INVALID"
                        ),
                        False,
                        str(exc),
                    )
                    self.store.db.commit()
                except sqlite3.Error:
                    self.store.db.rollback()
                return result

    def hospital_command(self, p):
        action = p["action"]
        h = self.hospital
        now = datetime.now(timezone.utc)
        upgraded = self.v11.command(p, now)
        if upgraded is not None:
            message = upgraded.pop("message")
            return self._result(True, message, p, **upgraded)
        if (
            action in {"STRESS_TEST_PRESSURE", "RESTORE_PRESSURE"}
            and h.config["mode"] == "CONNECTED"
        ):
            raise ValueError(
                "Synthetic pressure injection/reset is disabled in connected mode"
            )
        kind = {
            "UPSERT_PATIENT": "patients",
            "UPSERT_STAFF": "staff",
            "UPSERT_DEVICE": "devices",
        }.get(action)
        if kind:
            key = h.upsert(kind, p.get("record"))
            return self._result(True, kind.title() + " record saved", p, record_id=key)
        if action == "SET_HOSPITAL_CONFIG":
            config = p.get("config")
            if not isinstance(config, dict) or set(config) - set(h.config):
                raise ValueError("Unknown configuration field")
            v = {**h.config, **config}
            if self.demo_enabled and v["mode"] != "SIMULATION":
                raise ValueError(
                    "The demo workspace is simulation-only. Launch --standard with a separate data directory for connected operation."
                )
            if v["mode"] not in {"SIMULATION", "CONNECTED"}:
                raise ValueError("Invalid mode")
            ZoneInfo(v["timezone"])
            for f, lo, hi in (
                ("tariff_vnd_kwh", 0, 1e6),
                ("emission_kg_kwh", 0, 100),
                ("capex_vnd", 0, 1e15),
                ("annual_opex_vnd", 0, 1e15),
                ("sensor_timeout_seconds", 1, 300),
            ):
                v[f] = number(v[f], f, lo, hi)
            if type(v["auto_assign_team"]) is not bool:
                raise ValueError("Auto team selection must be boolean")
            mode_changed = v["mode"] != h.config["mode"]
            if mode_changed:
                if any(c["status"] == "IN_PROGRESS" for c in self.his.cases):
                    raise ValueError("Finish active cases before changing mode")
                for c in self.his.cases:
                    if c["source"] == "HIS_RANDOM" and c["status"] in {
                        "UNSCHEDULED",
                        "SCHEDULED",
                    }:
                        c.update(
                            status="CANCELLED", notes="Cancelled during mode change"
                        )
                h.meters.clear()
                h.thermal.clear()
            h.config = v
            if mode_changed:
                self.restore_source_roi()
                if v["mode"] == "CONNECTED":
                    self.archive_simulated_cases()
            self.his.generator_enabled = v["mode"] == "SIMULATION"
            self.his.simulation_enabled = self.his.generator_enabled
            return self._result(
                True, "Configuration saved; tariff applies to future samples", p
            )
        if action == "SERVICE_DEVICE":
            d = h.devices.get(p.get("device_id"))
            if not d:
                raise ValueError("Unknown device")
            if self.his.active_case_for_room(d["room_id"], now):
                raise ValueError("Cannot service device during an active case")
            performance = number(
                p.get("efficiency_percent"), "Measured performance", 0, 100
            )
            notes = text(p.get("notes"), "Service evidence", 1000)
            cost = number(p.get("cost_vnd", 0), "Service cost")
            if type(p.get("inspection_passed")) is not bool:
                raise ValueError("Technician pass/fail decision required")
            d.update(
                last_service_hours=d["runtime_hours"],
                inspection_efficiency_percent=performance,
                inspection_passed=p["inspection_passed"],
                inspected_at=now.isoformat(),
                inspection_source=h.config["mode"],
                status="AVAILABLE" if p["inspection_passed"] else "OFFLINE",
            )
            d["service_history"].append(
                {
                    "at": now.isoformat(),
                    "runtime_hours": d["runtime_hours"],
                    "efficiency_percent": performance,
                    "inspection_passed": p["inspection_passed"],
                    "cost_vnd": cost,
                    "notes": notes,
                    "actor": p.get("actor"),
                    "source": h.config["mode"],
                }
            )
            return self._result(True, "Service and performance inspection recorded", p)
        if action not in {
            "ASSIGN_CASE",
            "UPDATE_CASE",
            "CANCEL_CASE",
            "START_CASE",
            "COMPLETE_CASE",
            "RECORD_OUTCOME",
            "RECORD_CLINICAL_ESTIMATE",
        }:
            return None
        c = self.his.case_by_id(p.get("case_id"))
        archived = False
        if not c and action in {"RECORD_OUTCOME", "RECORD_CLINICAL_ESTIMATE"}:
            c = self.store.records("case_archive").get(p.get("case_id"))
            archived = bool(c)
            if c:
                for f in DATES:
                    if c.get(f):
                        c[f] = aware(c[f])
        if not c:
            raise ValueError("Unknown case")
        if action in {"ASSIGN_CASE", "UPDATE_CASE"}:
            if c["status"] not in {"UNSCHEDULED", "SCHEDULED"}:
                raise ValueError("Only pending cases can be edited")
            v = {**c}
            for f in (
                "patient_id",
                "staff_ids",
                "required_device_types",
                "consent_confirmed",
                "preop_complete",
            ):
                if f in p:
                    v[f] = p[f]
            if v.get("patient_id") not in h.patients:
                raise ValueError("Select a registered patient")
            if any(i not in h.staff for i in v.get("staff_ids", [])):
                raise ValueError("Unknown staff member")
            if not CORE_DEVICES.issubset(set(v.get("required_device_types", []))):
                raise ValueError("Core OR device requirements cannot be removed")
            if action == "UPDATE_CASE":
                if "estimated_duration_min" in p:
                    v["estimated_duration_min"] = p["estimated_duration_min"]
                if "notes" in p:
                    v["notes"] = text(p["notes"], "Notes", 300, False)
            if v["status"] == "SCHEDULED":
                end = v["scheduled_start"] + timedelta(
                    minutes=v["estimated_duration_min"]
                )
                ok, reason = h.slot_check(
                    v, v["scheduled_room_id"], v["scheduled_start"], end, commit=True
                )
                if not ok:
                    raise ValueError(reason)
                v["scheduled_end"] = end
            c.update(v)
            if c["status"] == "UNSCHEDULED" and self.autopilot:
                self.his.schedule_case(c, now)
            return self._result(True, "Case and assignments saved", p)
        if action == "CANCEL_CASE":
            if c["status"] not in {"UNSCHEDULED", "SCHEDULED"}:
                raise ValueError("Only pending cases can be cancelled")
            c.update(
                status="CANCELLED",
                cancellation_reason=text(p.get("reason"), "Cancellation reason", 300),
            )
            return self._result(True, "Case cancelled; reservations released", p)
        if action == "START_CASE":
            if c["status"] != "SCHEDULED":
                raise ValueError("Only scheduled cases can start")
            if now < c["scheduled_start"]:
                raise ValueError("Scheduled preparation is not complete")
            assessment = h.readiness(c, now)
            if not assessment["ready"]:
                raise ValueError(
                    "Not ready: "
                    + "; ".join(x["label"] for x in assessment["checks"] if not x["ok"])
                )
            ok, reason = h.slot_check(
                c,
                c["scheduled_room_id"],
                now,
                now + timedelta(minutes=c["estimated_duration_min"]),
                commit=True,
            )
            if not ok:
                raise ValueError(reason)
            c.update(
                status="IN_PROGRESS",
                actual_start=now,
                scheduled_end=now + timedelta(minutes=c["estimated_duration_min"]),
            )
            return self._result(True, "Actual case start recorded", p)
        if action == "COMPLETE_CASE":
            if c["status"] != "IN_PROGRESS":
                raise ValueError("Only active cases can complete")
            c.update(status="COMPLETED", actual_end=now, scheduled_end=now)
            return self._result(
                True, "Case completed; turnover and recovery remain reserved", p
            )
        if action == "RECORD_CLINICAL_ESTIMATE":
            estimate = {
                "percent": number(p.get("percent"), "Clinician estimate", 0, 100),
                "source": text(p.get("source"), "Source/model/version", 300),
                "endpoint": text(
                    p.get("endpoint"), "Endpoint and follow-up horizon", 160
                ),
                "recorded_at": now.isoformat(),
                "recorded_by": p.get("actor"),
                "status": "CLINICIAN_RECORDED_NOT_LOCALLY_VALIDATED",
            }
            c["clinical_estimate"] = estimate
            if archived:
                self.store.save_records("case_archive", {c["id"]: c})
            return self._result(True, "Clinician estimate recorded with provenance", p)
        if c["status"] != "COMPLETED" or not c.get("actual_end"):
            raise ValueError("Actual completed case required")
        if now < c["actual_end"] + timedelta(days=30):
            raise ValueError("30-day follow-up has not matured")
        if type(p.get("success")) is not bool:
            raise ValueError("Outcome must be boolean")
        notes = text(p.get("notes"), "Outcome evidence", 1000)
        h.outcomes[c["id"]] = {
            "id": c["id"],
            "procedure": c["procedure"],
            "endpoint": "NO_MAJOR_COMPLICATION_30D",
            "success": p["success"],
            "notes": notes,
            "recorded_at": now.isoformat(),
            "recorded_by": p.get("actor"),
            "is_demo": h.patients.get(c.get("patient_id"), {}).get("is_demo", False),
        }
        return self._result(True, "Mature outcome recorded", p)

    def ingest_telemetry(self, p):
        if self.hospital.config["mode"] != "CONNECTED":
            raise ValueError("Connected mode required")
        now = datetime.now(timezone.utc)
        scope = p.get("scope")
        stamp = aware(p.get("timestamp"))
        if scope != "facility" and scope not in self.rooms:
            raise ValueError("Unknown telemetry scope")
        if (
            not 0
            <= (now - stamp).total_seconds()
            <= self.hospital.config["sensor_timeout_seconds"]
        ):
            raise ValueError("Stale or future timestamp")
        previous = self.hospital.meters.get(scope)
        if previous and stamp <= aware(previous["timestamp"]):
            raise ValueError("Out-of-order sample")
        v = {
            "scope": scope,
            "timestamp": stamp.isoformat(),
            "power_kw": number(p.get("power_kw"), "Power", 0, 1e7),
            "source": text(p.get("source"), "Sensor source", 120),
        }
        if scope != "facility":
            for f, lo, hi in (
                ("temp_c", 0, 60),
                ("humidity", 0, 100),
                ("airflow_m3h", 0, 1e8),
            ):
                v[f] = number(p.get(f), f, lo, hi)
        elif "delta_p_pa" in p:
            v["delta_p_pa"] = number(p["delta_p_pa"], "Pressure", -100, 100)
        self.hospital.meters[scope] = v
        return {"ok": True, "scope": scope, "timestamp": v["timestamp"]}

    def financial_summary(self):
        row = self.store.db.execute(
            "SELECT SUM(cost) cost,SUM(seconds) seconds,SUM(baseline-actual) saved,SUM(measured) measured FROM energy WHERE tier=3600 AND scope=?",
            ("facility",),
        ).fetchone()
        cost = float(row["cost"] or 0)
        seconds = float(row["seconds"] or 0)
        config = self.hospital.config
        capex = config["capex_vnd"]
        opex = config["annual_opex_vnd"]
        allocated = opex * seconds / (365.25 * 86400)
        net = cost - allocated
        annual = cost / seconds * 365.25 * 86400 - opex if seconds >= 86400 else None
        return {
            "observed_savings_vnd": cost,
            "observed_seconds": seconds,
            "saved_kwh": float(row["saved"] or 0),
            "measured_seconds": float(row["measured"] or 0),
            "capex_vnd": capex,
            "allocated_opex_vnd": allocated,
            "net_operating_savings_vnd": net,
            "roi_percent": 100 * (net - capex) / capex if capex > 0 else None,
            "projected_annual_net_vnd": annual,
            "projected_payback_years": (
                capex / annual if annual and annual > 0 and capex > 0 else None
            ),
            "method": "Observed economics; annual projection requires 24 observed hours. Not a weather-normalized guarantee.",
        }
