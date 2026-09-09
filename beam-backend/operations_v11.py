"""Room-centred orchestration, durable engineering records and reviewable scheduling."""

import copy
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from hospital import aware, number, text
from storage import encode
from engineering import asset_health, thermal_forecast, thermal_observe, finance
from clinical_models import ClinicalModels

ADMIN_ACTIONS = {
    "SET_ROOM_FINANCE",
    "SET_DEVICE_ENGINEERING",
    "RECORD_DEVICE_INSPECTION",
    "RECORD_BMS_COST",
    "REGISTER_CLINICAL_MODEL",
    "EVALUATE_CLINICAL_MODEL",
}
CLINICAL_ACTIONS = {
    "RUN_CASE_PREDICTION",
    "PREVIEW_SCHEDULE",
    "APPLY_SCHEDULE_PLAN",
    "SET_CASE_CLINICAL_INPUTS",
    "REVIEW_CLINICAL_MODEL",
    "REVOKE_CLINICAL_MODEL",
}


class OperationsV11:
    def __init__(self, state):
        self.state = state
        self.data = state.store.get("v11", {})
        self.models = ClinicalModels(self)
        self.pending_targets = {}

    def observe(self, now):
        h = self.state.hospital
        for r in self.state.rooms.values():
            if not r["conditioned"]:
                continue
            connected = h.config["mode"] == "CONNECTED"
            thermal_observe(
                self.data,
                r,
                now,
                h.config["mode"],
                not connected or h.fresh(r["id"], now),
                h.meters.get(r["id"], {}).get("timestamp") if connected else None,
            )

    def trait(self, room, now):
        h = self.state.hospital
        targets = room.get("manual_targets") or {}
        return thermal_forecast(
            self.data,
            room,
            now,
            h.config["mode"],
            targets.get("temp_c", self.state.controls["temp_setpoint"]),
            targets.get("humidity", self.state.controls["rh_setpoint"]),
            h.config["mode"] == "SIMULATION" or h.fresh(room["id"], now),
        )

    def device(self, d):
        source = self.state.hospital.config["mode"]
        inspected = copy.deepcopy(d)
        if source == "CONNECTED" and d.get("inspection_source") != "CONNECTED":
            inspected["inspection_efficiency_percent"] = None
            inspected["service_history"] = []
        return asset_health(
            inspected,
            self.data.get("device_engineering", {}).get(d["id"], {}),
            [
                r
                for r in self.data.get("inspections", {}).get(d["id"], [])
                if r.get("source") == source
            ],
        )

    def business_fingerprint(self):
        s = self.state
        value = {
            "cases": [
                {k: v for k, v in c.items() if not k.startswith("_")}
                for c in s.his.cases
            ],
            "staff": s.hospital.staff,
            "patients": s.hospital.patients,
            "config": s.hospital.config,
            "rooms": {k: r["manual_mode"] for k, r in s.rooms.items()},
            "fault": s._pressure_fault_active,
        }
        return hashlib.sha256(encode(value).encode()).hexdigest()

    def control_fingerprint(self):
        s = self.state
        return hashlib.sha256(
            encode(
                {
                    "controls": s.controls,
                    "emergency": s.emergency_mode,
                    "fault": s._pressure_fault_active,
                    "pressure_alarm": s.sterility["pressure_alarm"],
                    "mode": s.hospital.config["mode"],
                    "energy_ai": s.energy_ai["enabled"],
                    "rooms": {
                        k: (r["manual_mode"], r.get("manual_targets"))
                        for k, r in s.rooms.items()
                    },
                    "cases": [
                        (
                            c["id"],
                            c["status"],
                            c.get("scheduled_start"),
                            c.get("scheduled_end"),
                            c.get("scheduled_room_id"),
                        )
                        for c in s.his.cases
                    ],
                }
            ).encode()
        ).hexdigest()

    def command(self, p, now):
        action = p["action"]
        if action == "RELEASE_ROOM_AUTOMATION":
            room = self.state.rooms.get(p.get("room_id"))
            if not room or not room["conditioned"]:
                raise ValueError("Select a conditioned room")
            room.update(manual_mode=None, manual_targets=None)
            return {
                "message": "Room manual modes and targets released to schedule and Energy AI"
            }
        result = self.models.command(p, now)
        if result is not None:
            return result
        if action == "SET_ROOM_FINANCE":
            room_id = p.get("room_id")
            if room_id not in self.state.rooms:
                raise ValueError("Unknown room")
            percentage = number(p.get("allocation_percent"), "Allocation", 0, 100)
            allocations = self.data.setdefault("room_finance", {})
            if (
                sum(
                    v["allocation_percent"]
                    for k, v in allocations.items()
                    if k != room_id
                )
                + percentage
                > 100 + 1e-8
            ):
                raise ValueError("Total room investment allocation cannot exceed 100%")
            allocations[room_id] = {
                "allocation_percent": percentage,
                "actor": p.get("actor"),
                "at": now.isoformat(),
            }
            return {"message": "Room share of facility CAPEX/OPEX saved"}
        if action == "SET_DEVICE_ENGINEERING":
            d = self.state.hospital.devices.get(p.get("device_id"))
            if not d:
                raise ValueError("Unknown device")
            if self.state.his.active_case_for_room(d["room_id"], now):
                raise ValueError("Cannot change equipment limits during an active case")
            settings = {
                "minimum_performance_percent": number(
                    p.get("minimum_performance_percent"),
                    "OEM performance threshold",
                    0,
                    100,
                ),
                "replacement_cost_vnd": number(
                    p.get("replacement_cost_vnd", 0), "Replacement cost"
                ),
                "evidence": text(
                    p.get("evidence"), "Manufacturer/technician specification", 1000
                ),
                "actor": p.get("actor"),
                "at": now.isoformat(),
            }
            if p.get("retire_on"):
                settings["retire_on"] = aware(p["retire_on"]).isoformat()
            self.data.setdefault("device_engineering", {})[d["id"]] = settings
            return {"message": "Equipment engineering limits saved"}
        if action == "RECORD_DEVICE_INSPECTION":
            d = self.state.hospital.devices.get(p.get("device_id"))
            if not d:
                raise ValueError("Unknown device")
            stamp = aware(p.get("observed_at"))
            if not 0 <= (now - stamp).total_seconds() <= 30 * 86400:
                raise ValueError("Inspection must be within the past 30 days")
            rows = self.data.setdefault("inspections", {}).setdefault(d["id"], [])
            runtime = number(
                p.get("runtime_hours"), "Observed runtime", 0, d["runtime_hours"]
            )
            if rows and (
                stamp <= aware(rows[-1]["at"]) or runtime < rows[-1]["runtime_hours"]
            ):
                raise ValueError(
                    "Inspection observations must progress in time and runtime"
                )
            rows.append(
                {
                    "id": secrets.token_hex(8),
                    "at": stamp.isoformat(),
                    "runtime_hours": runtime,
                    "performance_percent": number(
                        p.get("performance_percent"), "Measured performance", 0, 100
                    ),
                    "evidence": text(p.get("evidence"), "Inspection evidence", 1000),
                    "actor": p.get("actor"),
                    "source": self.state.hospital.config["mode"],
                }
            )
            return {
                "message": "Performance reading saved; service counter was not reset"
            }
        if action == "RECORD_BMS_COST":
            if p.get("room_id") not in self.state.rooms:
                raise ValueError("Select room for cost allocation")
            event = {
                "id": secrets.token_hex(8),
                "room_id": p["room_id"],
                "at": now.isoformat(),
                "cost_vnd": number(p.get("cost_vnd"), "Incremental BMS cost"),
                "evidence": text(
                    p.get("evidence"),
                    "Invoice/reference, exclude costs already in annual OPEX",
                    1000,
                ),
                "actor": p.get("actor"),
                "source": self.state.hospital.config["mode"],
            }
            self.data.setdefault("cost_events", []).append(event)
            return {
                "message": "Incremental BMS cost included in ROI",
                "record_id": event["id"],
            }
        if action == "PREVIEW_SCHEDULE":
            ids = p.get("case_ids")
            if (
                not isinstance(ids, list)
                or not 1 <= len(ids) <= 16
                or len(ids) != len(set(ids))
            ):
                raise ValueError("Choose 1 to 16 unique unscheduled cases")
            pending = [self.state.his.case_by_id(key) for key in ids]
            if any(not c or c["status"] != "UNSCHEDULED" for c in pending):
                raise ValueError("Only unscheduled cases can enter a plan")
            original = self.state.his.cases
            patients = copy.deepcopy(self.state.hospital.patients)
            fingerprint = self.business_fingerprint()
            rows, blocked = [], []
            try:
                self.state.his.cases = copy.deepcopy(original)
                ordered = sorted(
                    [self.state.his.case_by_id(key) for key in ids],
                    key=lambda c: -self.state.his.urgency_score(c, now),
                )
                for c in ordered:
                    if self.state.his.schedule_case(c, now + timedelta(minutes=2)):
                        rows.append(
                            {
                                k: c[k]
                                for k in (
                                    "id",
                                    "case_label",
                                    "scheduled_room_id",
                                    "scheduled_start",
                                    "scheduled_end",
                                    "staff_ids",
                                    "prep_room_id",
                                    "recovery_room_id",
                                )
                            }
                        )
                    else:
                        blocked.append(
                            {"case_id": c["id"], "reason": c.get("constraint_reason")}
                        )
            finally:
                self.state.his.cases = original
                self.state.hospital.patients = patients
            plan = {
                "id": secrets.token_hex(12),
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(seconds=90)).isoformat(),
                "fingerprint": fingerprint,
                "items": rows,
                "blocked": blocked,
                "status": "PROPOSED",
            }
            plans = self.data.setdefault("schedule_plans", {})
            for key in list(plans):
                if aware(plans[key]["expires_at"]) < now:
                    del plans[key]
            plans[plan["id"]] = plan
            return {
                "message": "Plan preview created; appointments are unchanged",
                "plan": plan,
            }
        if action == "APPLY_SCHEDULE_PLAN":
            plan = self.data.get("schedule_plans", {}).get(p.get("plan_id"))
            if (
                not plan
                or plan["status"] != "PROPOSED"
                or aware(plan["expires_at"]) < now
            ):
                raise ValueError(
                    "Plan expired or already applied; generate a fresh preview"
                )
            if plan["fingerprint"] != self.business_fingerprint():
                raise ValueError(
                    "Cases/resources changed since preview; generate a fresh plan"
                )
            for row in plan["items"]:
                ok, reason = self.state.his.manual_schedule_case(
                    row["id"],
                    row["scheduled_room_id"],
                    aware(row["scheduled_start"]),
                    now,
                )
                if not ok:
                    raise ValueError("Plan rolled back: " + reason)
            plan["status"] = "APPLIED"
            return {
                "message": f"Applied {len(plan['items'])} reservations atomically",
                "scheduled_count": len(plan["items"]),
            }
        return None

    def overview(self, now):
        rooms = []
        h = self.state.hospital
        for r in self.state.rooms.values():
            if not r["conditioned"]:
                continue
            primary = (
                self.state.his.active_case_for_room(r["id"], now)
                or self.state.his.waiting_case_for_room(r["id"], now)
                or self.state.his.next_case_for_room(r["id"], now)
            )
            _, _, _, _, reason = self.state._room_policy(copy.deepcopy(r), now)
            rooms.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "category": r["category"],
                    "status": r["status"],
                    "policy_reason": reason,
                    "temp_c": r["temp_c"],
                    "humidity": r["humidity"],
                    "power_kw": r["power_kw"],
                    "sensor_fresh": h.config["mode"] == "SIMULATION"
                    or h.fresh(r["id"], now),
                    "case_id": primary["id"] if primary else None,
                    "case_label": primary["case_label"] if primary else None,
                    "next_start": primary.get("scheduled_start") if primary else None,
                }
            )
        return {
            "contract": "beam-rooms-v11",
            "demo": self.state.demo_info,
            "at": now.isoformat(),
            "mode": h.config["mode"],
            "revision": self.state.revision,
            "rooms": rooms,
        }

    def room(self, room_id, now):
        s, h = self.state, self.state.hospital
        if room_id not in s.rooms:
            raise ValueError("Unknown room")
        r = s.rooms[room_id]
        trait = self.trait(r, now)
        cases = [
            c
            for c in s.his.cases
            if room_id
            in {
                c.get("scheduled_room_id"),
                c.get("prep_room_id"),
                c.get("recovery_room_id"),
            }
            and c["status"] != "CANCELLED"
            and c.get("scheduled_end")
            and c["scheduled_end"] + timedelta(minutes=max(18, c["recovery_minutes"]))
            > now
        ]
        cases.sort(key=lambda c: c["scheduled_start"])
        timeline = []
        for c in cases:
            start, end = c["scheduled_start"], c["scheduled_end"]
            if room_id == c.get("scheduled_room_id"):
                stages = [
                    (
                        "PRECONDITION",
                        start - timedelta(minutes=trait["lead_minutes"]),
                        start,
                    ),
                    ("SURGERY", start, end),
                    ("TURNOVER", end, end + timedelta(minutes=18)),
                ]
            elif room_id == c.get("prep_room_id"):
                stages = [
                    ("PREPARATION", start - timedelta(minutes=c["prep_minutes"]), start)
                ]
            else:
                stages = [
                    ("RECOVERY", end, end + timedelta(minutes=c["recovery_minutes"]))
                ]
            for stage, a, b in stages:
                if b > now and a < now + timedelta(hours=24):
                    timeline.append(
                        {
                            "case_id": c["id"],
                            "case_label": c["case_label"],
                            "stage": stage,
                            "start": a,
                            "end": b,
                            "basis": (
                                "ACTUAL_END"
                                if c.get("actual_end")
                                and stage in {"TURNOVER", "RECOVERY"}
                                else "SCHEDULE"
                            ),
                            "requires_actual_confirmation": c["source"] != "HIS_RANDOM"
                            and not c.get("actual_end"),
                        }
                    )
        active = s.his.active_case_for_room(
            room_id, now
        ) or s.his.waiting_case_for_room(room_id, now)
        if not active:
            active = next(
                (
                    c
                    for c in cases
                    if (
                        c.get("prep_room_id") == room_id
                        and c["scheduled_start"] - timedelta(minutes=c["prep_minutes"])
                        <= now
                        < c["scheduled_start"]
                    )
                    or (
                        c.get("recovery_room_id") == room_id
                        and c["status"] == "COMPLETED"
                        and c["scheduled_end"]
                        <= now
                        < c["scheduled_end"] + timedelta(minutes=c["recovery_minutes"])
                    )
                ),
                None,
            )
        primary = active or next(
            (c for c in cases if c["status"] in {"SCHEDULED", "IN_PROGRESS"}), None
        )
        assessment = None
        if primary:
            assessment = {
                "case": s.his.public_case(primary, now),
                "patient": h.patients.get(primary.get("patient_id")),
                "team": [
                    h.staff[i] for i in primary.get("staff_ids", []) if i in h.staff
                ],
                "readiness": h.readiness(primary, now),
                "clinical": h.clinical(primary),
                "clinical_inputs": self.data.get("clinical_inputs", {}).get(
                    primary["id"]
                ),
            }
        devices = [
            h.device_public(d) for d in h.devices.values() if d["room_id"] == room_id
        ]
        status, temp, rh, flow, reason = s._room_policy(copy.deepcopy(r), now)
        source = h.config["mode"]
        fresh = source == "SIMULATION" or h.fresh(room_id, now)
        baseline = s._standard_reference_room_power(r, now)
        alerts = []
        if not fresh:
            alerts.append(
                {
                    "level": "critical",
                    "message": "Room BMS data is stale; missing energy is not interpolated.",
                }
            )
        if s._pressure_fault_active or s.sterility["pressure_alarm"]:
            alerts.append(
                {
                    "level": "critical",
                    "message": "The pressure interlock takes priority over energy savings.",
                }
            )
        for d in devices:
            if not d["ready"]:
                alerts.append(
                    {
                        "level": "warning",
                        "message": d["name"] + ": not ready / service required.",
                    }
                )
        if (
            primary
            and primary["status"] == "SCHEDULED"
            and primary["scheduled_start"] < now
        ):
            alerts.append(
                {
                    "level": "warning",
                    "message": "The scheduled start has passed without confirmation; the room remains at active conditions.",
                }
            )
        if (
            trait["upper_eta_minutes"] is not None
            and primary
            and primary["scheduled_start"] > now
            and trait["upper_eta_minutes"]
            > (primary["scheduled_start"] - now).total_seconds() / 60
        ):
            alerts.append(
                {
                    "level": "warning",
                    "message": "Temperature or humidity may not reach the target range before the next case.",
                }
            )
        return {
            "contract": "beam-room-v11",
            "at": now.isoformat(),
            "mode": source,
            "room": s._public_room(r),
            "demo": s.demo_info,
            "current_case": assessment,
            "cases": [s.his.public_case(c, now) for c in cases],
            "devices": devices,
            "forecast": {
                "timeline": sorted(timeline, key=lambda x: x["start"]),
                "thermal": trait,
            },
            "alerts": alerts,
            "control": {
                "status": status,
                "target_temp_c": temp,
                "target_humidity": rh,
                "target_airflow_m3h": flow,
                "reason": reason,
                "receipt": self.data.get("receipts", {}).get(room_id),
                "requires_gateway_interlocks": True,
                "virtual_bms": s.demo_enabled,
            },
            "instant_energy": {
                "actual_kw": r["power_kw"] if fresh else None,
                "baseline_kw": baseline,
                "saved_kw": baseline - r["power_kw"] if fresh else None,
                "source": source,
            },
            "finance": finance(s, self.data, room_id),
            "room_finance": self.data.get("room_finance", {}).get(
                room_id, {"allocation_percent": 0}
            ),
        }

    def targets(self, now):
        self.pending_targets = {
            k: v
            for k, v in self.pending_targets.items()
            if aware(v["expires_at"]) > now
        }
        token = secrets.token_hex(16)
        out = {
            "contract": "beam-gateway-v11",
            "proposal_id": token,
            "mode": self.state.hospital.config["mode"],
            "revision": self.state.revision,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=15)).isoformat(),
            "requires_gateway_interlocks": True,
            "rooms": [],
        }
        for r in self.state.rooms.values():
            if not r["conditioned"]:
                continue
            status, temp, rh, flow, reason = self.state._room_policy(
                copy.deepcopy(r), now
            )
            out["rooms"].append(
                {
                    "room_id": r["id"],
                    "target_temp_c": temp,
                    "target_humidity": rh,
                    "target_airflow_m3h": flow,
                    "status": status,
                    "reason": reason,
                    "sensor_fresh": self.state.hospital.fresh(r["id"], now),
                }
            )
        self.pending_targets[token] = {
            **copy.deepcopy(out),
            "fingerprint": self.control_fingerprint(),
        }
        # Memory bound for a misconfigured high-rate gateway.
        while len(self.pending_targets) > 64:
            del self.pending_targets[next(iter(self.pending_targets))]
        return out

    def receipt(self, p, actor, now):
        if self.state.hospital.config["mode"] != "CONNECTED":
            raise ValueError("Connected mode required")
        proposal = self.pending_targets.get(p.get("proposal_id"))
        if not proposal or aware(proposal["expires_at"]) < now:
            raise ValueError("Unknown or expired target proposal")
        if proposal["fingerprint"] != self.control_fingerprint():
            raise ValueError("Operating policy changed; fetch new targets")
        target = next(
            (r for r in proposal["rooms"] if r["room_id"] == p.get("room_id")), None
        )
        if (
            not target
            or type(p.get("applied")) is not bool
            or type(p.get("revision")) is not int
            or p.get("revision") != proposal["revision"]
        ):
            raise ValueError("Target room/revision or applied decision mismatch")
        previous = self.data.get("receipts", {}).get(p["room_id"])
        if previous and previous.get("proposal_id") == p["proposal_id"]:
            if previous["applied"] != p["applied"] or previous.get("feedback") != p.get(
                "feedback"
            ):
                raise ValueError("Conflicting duplicate gateway receipt")
            return previous
        if previous and aware(previous["issued_at"]) > aware(proposal["issued_at"]):
            raise ValueError("Superseded target receipt")
        feedback = None
        if p["applied"]:
            if not self.state.hospital.fresh(p["room_id"], now):
                raise ValueError(
                    "Fresh room telemetry required before accepting applied targets"
                )
            feedback = p.get("feedback")
            if not isinstance(feedback, dict):
                raise ValueError("Read-back of applied setpoints required")
            for key, tolerance in (
                ("target_temp_c", 0.5),
                ("target_humidity", 1),
                ("target_airflow_m3h", max(1, target["target_airflow_m3h"] * 0.03)),
            ):
                value = number(feedback.get(key), "Read-back " + key, 0, 1e8)
                if abs(value - target[key]) > tolerance:
                    raise ValueError("Read-back disagrees with issued target: " + key)
        receipt = {
            "proposal_id": p["proposal_id"],
            "room_id": p["room_id"],
            "revision": p["revision"],
            "applied": p["applied"],
            "feedback": feedback,
            "issued_at": proposal["issued_at"],
            "at": now.isoformat(),
            "detail": text(p.get("detail"), "Gateway evidence", 1000),
            "actor": actor,
        }
        self.data.setdefault("receipts", {})[p["room_id"]] = receipt
        self.state.store.put("v11", self.data)
        self.state.store.audit(
            actor, "GATEWAY_ACTUATION", p["applied"], encode(receipt)
        )
        self.state.store.db.commit()
        return receipt
