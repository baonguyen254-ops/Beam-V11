from __future__ import annotations

import math
import time
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from floorplan_model import FloorplanModel


URGENCY_ORDER = {"STAT": 4, "EMERGENCY": 3, "URGENT": 2, "ELECTIVE": 1}
URGENCY_DEADLINE_MIN = {"STAT": 15, "EMERGENCY": 45, "URGENT": 180, "ELECTIVE": 24 * 60}
TURNOVER_MINUTES = 18
MAX_LIVE_CASES = 320
MAX_COMPLETED_CASES = 120
SCHEDULING_HORIZON_HOURS = 48


PROCEDURES: Dict[str, List[Tuple[str, int, int]]] = {
    "GENERAL": [
        ("Laparoscopic Cholecystectomy", 55, 110),
        ("Appendectomy", 45, 95),
        ("Hernia Repair", 50, 120),
        ("Bowel Resection", 90, 190),
    ],
    "CARDIAC": [
        ("Coronary Artery Bypass Graft", 180, 330),
        ("Valve Replacement", 150, 280),
        ("Cardiac Re-exploration", 90, 210),
    ],
    "VASCULAR": [
        ("Peripheral Vascular Bypass", 120, 240),
        ("Carotid Endarterectomy", 75, 150),
    ],
    "GASTROINTESTINAL": [
        ("Laparoscopic Colectomy", 100, 210),
        ("Exploratory Laparotomy", 80, 180),
    ],
    "UROLOGY": [
        ("Ureteroscopy", 45, 95),
        ("Transurethral Resection", 55, 120),
        ("Nephrectomy", 110, 220),
    ],
    "ORTHOPEDICS": [
        ("Total Knee Arthroplasty", 90, 160),
        ("Total Hip Arthroplasty", 95, 175),
        ("Fracture Fixation", 70, 180),
    ],
    "TRAUMA": [
        ("Trauma Damage-Control Surgery", 75, 210),
        ("Emergency Hemorrhage Control", 50, 160),
        ("Polytrauma Operative Stabilization", 100, 240),
    ],
    "NEUROSURGERY": [
        ("Craniotomy", 150, 300),
        ("Spinal Decompression", 110, 220),
        ("Emergency Hematoma Evacuation", 70, 160),
    ],
    "ENT": [
        ("Endoscopic Sinus Surgery", 50, 110),
        ("Tonsillectomy", 35, 75),
        ("Microlaryngoscopy", 25, 60),
    ],
    "MINOR": [
        ("Minor Surgical Procedure", 20, 55),
        ("Wound Debridement", 25, 70),
    ],
    "ENDOSCOPY": [
        ("Therapeutic Endoscopy", 25, 65),
        ("ERCP", 35, 90),
    ],
    "GYNECOLOGY": [
        ("Laparoscopic Gynecologic Surgery", 60, 130),
        ("Hysterectomy", 90, 180),
    ],
}


class HISEngine:
    """Continuous stochastic intake + constraint-aware OR scheduling.

    Randomness comes from secrets.SystemRandom (OS entropy; no fixed application seed).
    The generator is intentionally bounded in memory and generation catch-up to keep
    a long-running demo stable.
    """

    def __init__(self, floorplan: FloorplanModel, bootstrap=True) -> None:
        self.floorplan = floorplan
        self.rng = secrets.SystemRandom()
        self.cases: List[Dict[str, Any]] = []
        self._recent_signatures: List[str] = []
        self.next_generation_at = datetime.now().astimezone() + timedelta(seconds=self._next_interval_seconds())
        self.total_generated = 0
        self.total_external = 0
        self.prepare_case_hook=None
        self.slot_check_hook=None
        self.generator_enabled=True
        self.simulation_enabled=True
        if bootstrap:self._bootstrap()

    # ------------------------------------------------------------------
    # Random intake
    # ------------------------------------------------------------------

    def _next_interval_seconds(self) -> float:
        # Exponential inter-arrival process, truncated for demo usability.
        # This is not a repeating table or deterministic seeded cycle.
        mean = 24.0
        u = max(1e-9, min(1.0 - 1e-9, self.rng.random()))
        seconds = -math.log(1.0 - u) * mean
        return max(7.0, min(55.0, seconds))

    def _choose_urgency(self) -> str:
        x = self.rng.random()
        if x < 0.04:
            return "STAT"
        if x < 0.18:
            return "EMERGENCY"
        if x < 0.48:
            return "URGENT"
        return "ELECTIVE"

    def _choose_specialty(self) -> str:
        # Weighted by aggregate OR capability coverage so the stream remains
        # schedulable while still producing constrained/high-acuity cases.
        population = [
            "GENERAL", "GENERAL", "GENERAL",
            "ORTHOPEDICS", "TRAUMA", "CARDIAC", "ENT", "UROLOGY",
            "NEUROSURGERY", "GYNECOLOGY", "GASTROINTESTINAL", "MINOR",
            "ENDOSCOPY", "VASCULAR",
        ]
        return self.rng.choice(population)

    def _case_signature(self, specialty: str, procedure: str, urgency: str, duration: int) -> str:
        return f"{specialty}|{procedure}|{urgency}|{duration // 10}"

    def _random_case(self, now: datetime) -> Dict[str, Any]:
        # Reroll a few times if the recent signature repeats. This is not needed
        # for entropy, but prevents visible short-term repetition in a demo UI.
        for _ in range(8):
            specialty = self._choose_specialty()
            procedure, lo, hi = self.rng.choice(PROCEDURES[specialty])
            duration = self.rng.randint(lo, hi)
            urgency = self._choose_urgency()
            sig = self._case_signature(specialty, procedure, urgency, duration)
            if sig not in self._recent_signatures[-8:]:
                break
        else:
            specialty = self._choose_specialty()
            procedure, lo, hi = self.rng.choice(PROCEDURES[specialty])
            duration = self.rng.randint(lo, hi)
            urgency = self._choose_urgency()
            sig = self._case_signature(specialty, procedure, urgency, duration)

        self._recent_signatures.append(sig)
        self._recent_signatures = self._recent_signatures[-24:]
        if urgency == "STAT":
            prep = self.rng.randint(5, 10)
        elif urgency == "EMERGENCY":
            prep = self.rng.randint(8, 16)
        elif urgency == "URGENT":
            prep = self.rng.randint(12, 28)
        else:
            prep = self.rng.randint(15, 35)
        recovery = self.rng.randint(35, 140)
        case_id = f"his-{secrets.token_hex(6)}"
        latest = now + timedelta(minutes=URGENCY_DEADLINE_MIN[urgency])
        return {
            "id": case_id,
            "case_label": f"HIS-{case_id[-6:].upper()}",
            "source": "HIS_RANDOM",
            "procedure": procedure,
            "specialty": specialty,
            "urgency": urgency,
            "estimated_duration_min": duration,
            "prep_minutes": prep,
            "recovery_minutes": recovery,
            "created_at": now,
            "latest_start_at": latest,
            "status": "UNSCHEDULED",
            "scheduled_room_id": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "prep_room_id": None,
            "recovery_room_id": None,
            "constraint_reason": None,
            "notes": "Generated by continuous HIS intake simulator",
        }

    def _bootstrap(self) -> None:
        now = datetime.now().astimezone()
        # Populate the dashboard without using a fixed daily pattern.
        for idx in range(10):
            arrival = now - timedelta(minutes=self.rng.randint(0, 8))
            case = self._random_case(arrival)
            self.cases.append(case)
            self.total_generated += 1
        self.schedule_all_unscheduled(now)

    def generate_due(self, now: datetime, autopilot: bool) -> List[Dict[str, Any]]:
        generated: List[Dict[str, Any]] = []
        if not self.generator_enabled:return generated
        # Bounded catch-up prevents a paused machine from generating thousands of
        # events immediately after resume.
        catch_up = 0
        while now >= self.next_generation_at and catch_up < 3 and sum(c["status"] not in {"COMPLETED","CANCELLED"} for c in self.cases) < MAX_LIVE_CASES:
            case = self._random_case(now)
            if self.prepare_case_hook:self.prepare_case_hook(case,now)
            self.cases.append(case)
            self.total_generated += 1
            generated.append(case)
            catch_up += 1
            self.next_generation_at = now + timedelta(seconds=self._next_interval_seconds())
            if autopilot:
                self.schedule_case(case, now)
        if catch_up == 0 and now >= self.next_generation_at:
            self.next_generation_at = now + timedelta(seconds=self._next_interval_seconds())
        return generated

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _eligible_operating_rooms(self, specialty: str) -> List[Dict[str, Any]]:
        return [
            room
            for room in self.floorplan.operating_rooms()
            if specialty in room.get("capabilities", [])
        ]

    def _scheduled_intervals(self, room_id: str, exclude_case_id: Optional[str] = None) -> List[Tuple[datetime, datetime]]:
        intervals: List[Tuple[datetime, datetime]] = []
        for case in self.cases:
            if case["id"] == exclude_case_id:
                continue
            if case.get("scheduled_room_id") != room_id:
                continue
            if case.get("status") == "CANCELLED":
                continue
            start = case.get("scheduled_start")
            end = case.get("scheduled_end")
            if isinstance(start, datetime) and isinstance(end, datetime):
                if case["status"] in {"SCHEDULED","IN_PROGRESS"} and case["source"]!="HIS_RANDOM" and start<=datetime.now().astimezone():
                    end=max(end,datetime.now().astimezone()+timedelta(minutes=case["estimated_duration_min"]))
                intervals.append((start, end))
        return sorted(intervals, key=lambda x: x[0])

    def _earliest_slot(self, room_id: str, not_before: datetime, duration_min: int, exclude_case_id: Optional[str] = None) -> datetime:
        duration = timedelta(minutes=duration_min)
        turnover = timedelta(minutes=TURNOVER_MINUTES)
        candidate = not_before.replace(second=0, microsecond=0)
        if candidate < not_before:candidate += timedelta(minutes=1)
        # Add non-periodic minute jitter to avoid a synthetic all-cases-on-5-min grid.
        candidate += timedelta(minutes=self.rng.randint(0, 4))
        for start, end in self._scheduled_intervals(room_id, exclude_case_id):
            if candidate + duration + turnover <= start:
                return candidate
            if candidate < end + turnover:
                candidate = end + turnover
        return candidate

    def _nearest_room(self, origin_id: str, categories: List[str]) -> Optional[str]:
        candidates = [r for r in self.floorplan.rooms if r["category"] in categories]
        if not candidates:
            return None
        candidates.sort(key=lambda r: (self.floorplan.graph_distance(origin_id, r["id"]), r["area_m2"]))
        return candidates[0]["id"]

    def schedule_case(self, case: Dict[str, Any], now: datetime) -> bool:
        if case.get("status") not in {"UNSCHEDULED", "SCHEDULED"}:
            return False
        if self.prepare_case_hook:self.prepare_case_hook(case,now)
        eligible = self._eligible_operating_rooms(case["specialty"])
        if not eligible:
            case["constraint_reason"] = f"No OR capability for {case['specialty']}"
            return False

        not_before = max(now, case["created_at"]) + timedelta(minutes=int(case["prep_minutes"]))
        scored: List[Tuple[float, datetime, Dict[str, Any]]] = []
        recovery_rooms = self.floorplan.rooms_by_category("RECOVERY")
        recovery_id = recovery_rooms[0]["id"] if recovery_rooms else None
        last_reason="No free OR slot"
        for room in eligible:
            start = self._earliest_slot(room["id"], not_before, int(case["estimated_duration_min"]), case["id"])
            if self.slot_check_hook:
                attempts=0
                while start<=now+timedelta(hours=SCHEDULING_HORIZON_HOURS) and attempts<577:
                    valid,last_reason=self.slot_check_hook(case,room['id'],start,start+timedelta(minutes=case['estimated_duration_min']))
                    if valid:break
                    if any(x in last_reason for x in ('Assign an active patient','Room unavailable','Required device','Physical pressure','Synthetic','inactive staff','specialty mismatch','Assign complete')):
                        start=now+timedelta(hours=SCHEDULING_HORIZON_HOURS+1);break
                    start=self._earliest_slot(room['id'],start+timedelta(minutes=5),case['estimated_duration_min'],case['id'])
                    attempts+=1
            if start > now + timedelta(hours=SCHEDULING_HORIZON_HOURS):
                continue
            route_penalty = 0
            if recovery_id:
                route_penalty += self.floorplan.graph_distance(room["id"], recovery_id)
            # Urgent cases strongly favor earliest start; route distance is a
            # small tie-breaker for staff/patient movement.
            score = start.timestamp() + route_penalty * 45.0
            scored.append((score, start, room))

        if not scored:
            case["constraint_reason"] = "No slot in 48-hour horizon: "+last_reason
            return False

        _, start, room = min(scored, key=lambda x: x[0])
        end = start + timedelta(minutes=int(case["estimated_duration_min"]))
        prep_room = self._nearest_room(room["id"], ["PREP", "PREOP"])
        recovery_room = self._nearest_room(room["id"], ["RECOVERY"])
        case.update(
            {
                "status": "SCHEDULED",
                "scheduled_room_id": room["id"],
                "scheduled_start": start,
                "scheduled_end": end,
                "prep_room_id": prep_room,
                "recovery_room_id": recovery_room,
                "constraint_reason": None,
            }
        )
        if self.slot_check_hook:self.slot_check_hook(case,room["id"],start,end,commit=True)
        return True

    def schedule_all_unscheduled(self, now: datetime) -> int:
        pending = [c for c in self.cases if c["status"] == "UNSCHEDULED"]
        pending.sort(key=lambda c: (-URGENCY_ORDER[c["urgency"]], c["latest_start_at"], c["created_at"]))
        scheduled = 0
        attempts=0;started=time.monotonic()
        for case in pending:
            if attempts>=16 or time.monotonic()-started>1:break
            if now.timestamp()<case.get('_retry_after',0):continue
            attempts+=1
            if self.schedule_case(case, now):
                case.pop('_retry_after',None);scheduled += 1
            else:case['_retry_after']=now.timestamp()+30
        return scheduled

    def manual_schedule_case(self, case_id: str, room_id: str, start: datetime, now: datetime) -> Tuple[bool, str]:
        case = self.case_by_id(case_id)
        room = next((r for r in self.floorplan.operating_rooms() if r["id"] == room_id), None)
        if not case:
            return False, "Unknown HIS case"
        if case["status"] not in {"UNSCHEDULED","SCHEDULED"}:return False,"Only pending cases can be scheduled"
        if self.prepare_case_hook:self.prepare_case_hook(case,now)
        if not room:
            return False, "Selected room is not an operating room"
        if case["specialty"] not in room.get("capabilities", []):
            return False, f"{room['name']} is not configured for {case['specialty']}"
        if start.tzinfo is None:return False,'Start must include timezone'
        if start<max(now,case['created_at'])+timedelta(minutes=case['prep_minutes']):return False,'Manual start must allow full preparation'
        if start>now+timedelta(hours=SCHEDULING_HORIZON_HOURS):return False,'Manual start exceeds 48-hour horizon' 
        end = start + timedelta(minutes=int(case["estimated_duration_min"]))
        turnover = timedelta(minutes=TURNOVER_MINUTES)
        for other_start, other_end in self._scheduled_intervals(room_id, case_id):
            if not (end + turnover <= other_start or start >= other_end + turnover):
                return False, "Manual slot overlaps an existing case or required turnover window"
        if self.slot_check_hook:
            valid,reason=self.slot_check_hook(case,room_id,start,end)
            if not valid:return False,reason
        case.update(
            {
                "status": "SCHEDULED",
                "scheduled_room_id": room_id,
                "scheduled_start": start,
                "scheduled_end": end,
                "prep_room_id": self._nearest_room(room_id, ["PREP", "PREOP"]),
                "recovery_room_id": self._nearest_room(room_id, ["RECOVERY"]),
                "constraint_reason": None,
            }
        )
        if self.slot_check_hook:self.slot_check_hook(case,room_id,start,end,commit=True)
        return True, f"{case['case_label']} manually scheduled in {room['name']}"

    # ------------------------------------------------------------------
    # External case intake / lifecycle
    # ------------------------------------------------------------------

    def add_external_case(self, payload: Dict[str, Any], now: datetime, autopilot: bool) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        if sum(c["status"] not in {"COMPLETED","CANCELLED"} for c in self.cases)>=MAX_LIVE_CASES:return False,"Live case limit reached",None
        specialty = str(payload.get("specialty") or "").upper()
        urgency = str(payload.get("urgency") or "").upper()
        procedure = str(payload.get("procedure") or "").strip()
        case_label = str(payload.get("case_label") or "").strip()
        notes = str(payload.get("notes") or "").strip()
        if specialty not in PROCEDURES:
            return False, "Unsupported specialty", None
        if urgency not in URGENCY_ORDER:
            return False, "Urgency must be STAT, EMERGENCY, URGENT, or ELECTIVE", None
        if not procedure or len(procedure) > 80:
            return False, "Procedure must contain 1–80 characters", None
        try:
            duration = int(payload.get("estimated_duration_min"))
        except (TypeError, ValueError, OverflowError):
            return False, "Estimated duration must be an integer", None
        if not 15 <= duration <= 480:
            return False, "Estimated duration must be 15–480 minutes", None
        if len(case_label) > 40 or len(notes) > 300:
            return False, "Case label or notes are too long", None

        case_id = f"ext-{secrets.token_hex(6)}"
        case = {
            "id": case_id,
            "case_label": case_label or f"EXT-{case_id[-6:].upper()}",
            "source": "EXTERNAL",
            "procedure": procedure,
            "specialty": specialty,
            "urgency": urgency,
            "estimated_duration_min": duration,
            "prep_minutes": int(max(5, min(90, int(payload.get("prep_minutes") or {"STAT": 8, "EMERGENCY": 12, "URGENT": 20, "ELECTIVE": 25}[urgency])))),
            "recovery_minutes": int(max(15, min(240, int(payload.get("recovery_minutes") or 60)))),
            "created_at": now,
            "latest_start_at": now + timedelta(minutes=URGENCY_DEADLINE_MIN[urgency]),
            "status": "UNSCHEDULED",
            "scheduled_room_id": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "prep_room_id": None,
            "recovery_room_id": None,
            "constraint_reason": None,
            "notes": notes,
        }
        for f in ("patient_id","staff_ids","required_device_types","consent_confirmed","preop_complete"):
            if f in payload:case[f]=payload[f]
        if self.prepare_case_hook:self.prepare_case_hook(case,now)
        self.cases.append(case)
        self.total_external += 1
        if autopilot:
            self.schedule_case(case, now)
        return True, f"External case {case['case_label']} added to HIS", case

    def case_by_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        return next((c for c in self.cases if c["id"] == case_id), None)

    def tick(self, now: datetime, autopilot: bool) -> List[Dict[str, Any]]:
        generated = self.generate_due(now, autopilot)
        if autopilot:
            self.schedule_all_unscheduled(now)

        for case in self.cases:
            start = case.get("scheduled_start")
            end = case.get("scheduled_end")
            if self.simulation_enabled and case["source"]=="HIS_RANDOM" and case["status"] == "SCHEDULED" and isinstance(start, datetime) and start <= now:
                if self.slot_check_hook:
                    valid,reason=self.slot_check_hook(case,case['scheduled_room_id'],start,end)
                    if not valid:
                        case.update(status='UNSCHEDULED',constraint_reason=reason,scheduled_room_id=None,scheduled_start=None,scheduled_end=None)
                        continue
                case["status"] = "IN_PROGRESS"
                case["actual_start"] = start
            if self.simulation_enabled and case["source"]=="HIS_RANDOM" and case["status"] == "IN_PROGRESS" and isinstance(end, datetime) and end <= now:
                case["status"] = "COMPLETED"
                case["actual_end"] = end

        # Stable memory footprint for indefinite execution.
        completed = [c for c in self.cases if c["status"] in {"COMPLETED","CANCELLED"}]
        if len(completed) > MAX_COMPLETED_CASES:
            completed_sorted = sorted(completed, key=lambda c: c.get("scheduled_end") or c["created_at"], reverse=True)
            keep_completed = {c["id"] for c in completed_sorted[:MAX_COMPLETED_CASES]}
            self.cases = [c for c in self.cases if c["status"] not in {"COMPLETED","CANCELLED"} or c["id"] in keep_completed]
        return generated

    # ------------------------------------------------------------------
    # Queries / public state
    # ------------------------------------------------------------------

    def active_case_for_room(self, room_id: str, now: datetime) -> Optional[Dict[str, Any]]:
        active = [
            c for c in self.cases
            if c.get("scheduled_room_id") == room_id
            and c.get("scheduled_start")
            and c.get("scheduled_end")
            and (c["status"]=="IN_PROGRESS" or c["source"]=="HIS_RANDOM" and c["status"]=="SCHEDULED" and c["scheduled_start"]<=now<c["scheduled_end"])
        ]
        return min(active, key=lambda c: c["scheduled_start"]) if active else None

    def waiting_case_for_room(self,room_id,now):
        rows=[c for c in self.cases if c['status']=='SCHEDULED' and c.get('scheduled_room_id')==room_id and c.get('scheduled_start') and c['scheduled_start']<=now]
        return min(rows,key=lambda c:c['scheduled_start']) if rows else None

    def next_case_for_room(self, room_id: str, now: datetime) -> Optional[Dict[str, Any]]:
        upcoming = [
            c for c in self.cases
            if c.get("scheduled_room_id") == room_id
            and c.get("scheduled_start")
            and c["scheduled_start"] > now
            and c["status"] == "SCHEDULED"
        ]
        return min(upcoming, key=lambda c: c["scheduled_start"]) if upcoming else None

    def room_activity(self, room_id: str, category: str, now: datetime) -> Optional[str]:
        if category in {"PREP", "PREOP"}:
            for case in self.cases:
                if case["status"] in {"CANCELLED","UNSCHEDULED"}:continue
                if case.get("prep_room_id") != room_id or not case.get("scheduled_start"):
                    continue
                start = case["scheduled_start"] - timedelta(minutes=int(case["prep_minutes"]))
                if start <= now < case["scheduled_start"]:
                    return "PREP_ACTIVE" if category == "PREP" else "PREOP_ACTIVE"
        if category == "RECOVERY":
            for case in self.cases:
                if case["status"] in {"CANCELLED","UNSCHEDULED"}:continue
                if case['source']!='HIS_RANDOM' and case['status']!='COMPLETED':continue
                if case.get("recovery_room_id") != room_id or not case.get("scheduled_end"):
                    continue
                end = case["scheduled_end"] + timedelta(minutes=int(case["recovery_minutes"]))
                if case["scheduled_end"] <= now < end:
                    return "RECOVERY_ACTIVE"
        if category == "CORRIDOR":
            # Corridor activity follows actual door-graph circulation paths for
            # active/prep/recovery case windows instead of a fixed occupancy pattern.
            for case in self.cases:
                if case["status"] in {"CANCELLED","UNSCHEDULED"}:continue
                if room_id not in self._route(case):
                    continue
                start = case.get("scheduled_start")
                end = case.get("scheduled_end")
                if not isinstance(start, datetime) or not isinstance(end, datetime):
                    continue
                flow_start = start - timedelta(minutes=int(case["prep_minutes"]))
                flow_end = end + timedelta(minutes=int(case["recovery_minutes"]))
                if flow_start <= now < flow_end:
                    return "CIRCULATION_ACTIVE"
        return None

    def urgency_score(self, case: Dict[str, Any], now: datetime) -> float:
        base = URGENCY_ORDER[case["urgency"]] * 100.0
        waited = max(0.0, (now - case["created_at"]).total_seconds() / 60.0)
        overdue = max(0.0, (now - case["latest_start_at"]).total_seconds() / 60.0)
        return round(base + waited * 0.5 + overdue * 5.0, 1)

    def _route(self, case: Dict[str, Any]) -> List[str]:
        prep = case.get("prep_room_id")
        operating = case.get("scheduled_room_id")
        recovery = case.get("recovery_room_id")
        if not operating:
            return []
        path: List[str] = []
        if prep:
            p1 = self.floorplan.shortest_path(prep, operating)
            path.extend(p1)
        else:
            path.append(operating)
        if recovery:
            p2 = self.floorplan.shortest_path(operating, recovery)
            if p2:
                path.extend(p2[1:] if path else p2)
        return path

    @staticmethod
    def _iso(value: Any) -> Any:
        return value.isoformat() if isinstance(value, datetime) else value

    def public_case(self, case: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        eligible_ids = [r["id"] for r in self._eligible_operating_rooms(case["specialty"])]
        deadline_breach = bool(
            isinstance(case.get("scheduled_start"), datetime)
            and case["scheduled_start"] > case["latest_start_at"]
        )
        deadline_overdue = bool(case["status"] == "UNSCHEDULED" and now > case["latest_start_at"])
        return {
            **{k:self._iso(case.get(k)) for k in ("patient_id","staff_ids","required_device_types","consent_confirmed","preop_complete","actual_start","actual_end","clinical_estimate")},
            "id": case["id"],
            "case_label": case["case_label"],
            "source": case["source"],
            "procedure": case["procedure"],
            "specialty": case["specialty"],
            "urgency": case["urgency"],
            "estimated_duration_min": case["estimated_duration_min"],
            "prep_minutes": case["prep_minutes"],
            "recovery_minutes": case["recovery_minutes"],
            "created_at": self._iso(case["created_at"]),
            "latest_start_at": self._iso(case["latest_start_at"]),
            "status": case["status"],
            "scheduled_room_id": case.get("scheduled_room_id"),
            "scheduled_start": self._iso(case.get("scheduled_start")),
            "scheduled_end": self._iso(case.get("scheduled_end")),
            "prep_room_id": case.get("prep_room_id"),
            "recovery_room_id": case.get("recovery_room_id"),
            "constraint_reason": case.get("constraint_reason"),
            "notes": case.get("notes", ""),
            "priority_score": self.urgency_score(case, now),
            "manual_action_required": case["status"] == "UNSCHEDULED",
            "deadline_breach": deadline_breach,
            "deadline_overdue": deadline_overdue,
            "eligible_room_ids": eligible_ids,
            "circulation_path": self._route(case),
        }

    def public_state(self, now: datetime, autopilot: bool) -> Dict[str, Any]:
        cases = [self.public_case(c, now) for c in self.cases]
        cases.sort(
            key=lambda c: (
                c["status"] == "COMPLETED",
                c["status"] != "UNSCHEDULED",
                -c["priority_score"],
                c.get("scheduled_start") or c["created_at"],
            )
        )
        unscheduled = [c for c in cases if c["status"] == "UNSCHEDULED"]
        urgent_unscheduled = [c for c in unscheduled if c["urgency"] in {"STAT", "EMERGENCY", "URGENT"}]
        sla_risk = [c for c in cases if c["status"] not in {"COMPLETED","CANCELLED"} and (c.get("deadline_breach") or c.get("deadline_overdue"))]
        if not autopilot and urgent_unscheduled:
            health = "CRITICAL"
        elif unscheduled or sla_risk:
            health = "DEGRADED"
        else:
            health = "HEALTHY"
        return {
            "generator": {
                "enabled": self.generator_enabled,
                "mode": "OS_ENTROPY_STOCHASTIC_STREAM",
                "next_case_at": self.next_generation_at.isoformat(),
                "total_generated": self.total_generated,
                "total_external": self.total_external,
                "bounded_live_case_limit": MAX_LIVE_CASES,
            },
            "scheduler": {
                "autopilot": autopilot,
                "health": health,
                "unscheduled_count": len(unscheduled),
                "urgent_unscheduled_count": len(urgent_unscheduled),
                "sla_risk_count": len(sla_risk),
                "turnover_minutes": TURNOVER_MINUTES,
                "capability_source": "BEAM_DEMO_CONFIG_NOT_OPENSTUDIO",
            },
            "cases": cases,
        }
