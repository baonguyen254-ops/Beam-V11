"""Self-contained synthetic hospital, activated only in a dedicated demo workspace.

The supplied floorplan is the geometry authority. Every clinical, engineering and
historical operating record below is generated for presentation, not measured.
"""

import copy
import hashlib
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clinical_models import ENDPOINT, evaluate, predict
from engineering import thermal_observe
from his_engine import PROCEDURES
from hospital import CORE_DEVICES, aware
from storage import encode

PACK_ID = "beam-english-demo-11.1"
DEMO_SOURCE = "Bundled synthetic demonstration; no patient or meter observations"
MODEL_DIR = Path(__file__).resolve().parents[1] / "examples" / "demo" / "models"
FIRST_NAMES = ("Alex", "Jordan", "Morgan", "Taylor", "Casey", "Riley", "Jamie", "Avery")
LAST_NAMES = (
    "Parker",
    "Bennett",
    "Hayes",
    "Reed",
    "Brooks",
    "Carter",
    "Ellis",
    "Sutton",
)


def model_specs():
    groups = [
        (
            "general",
            "General surgery",
            ["GENERAL", "GASTROINTESTINAL", "UROLOGY"],
            2.35,
        ),
        (
            "complex",
            "Complex surgery",
            ["CARDIAC", "VASCULAR", "NEUROSURGERY", "TRAUMA"],
            1.75,
        ),
        (
            "specialty",
            "Specialty surgery",
            ["ORTHOPEDICS", "ENT", "MINOR", "ENDOSCOPY", "GYNECOLOGY"],
            2.65,
        ),
    ]
    for key, name, specialties, intercept in groups:
        yield {
            "id": "demo-" + key + "-1.0",
            "name": name + " · Synthetic demo",
            "version": "1.0-demo",
            "type": "LOGISTIC_V1",
            "endpoint": ENDPOINT,
            "simulation_only": True,
            "source": "BEAM artificial teaching coefficients. These are not fitted or validated on patients.",
            "intended_population": "Fictional adult demonstration cases only; never clinical decision-making.",
            "specialties": specialties,
            "procedures": [p for s in specialties for p, _, _ in PROCEDURES[s]],
            "intercept": intercept,
            "features": {
                "age_years": {
                    "min": 18,
                    "max": 100,
                    "center": 50,
                    "scale": 1,
                    "coefficient": -0.035,
                },
                "asa_class": {
                    "min": 1,
                    "max": 5,
                    "center": 2,
                    "scale": 1,
                    "coefficient": -0.72,
                },
                "emergency": {
                    "min": 0,
                    "max": 1,
                    "center": 0,
                    "scale": 1,
                    "coefficient": -0.6,
                },
                "bmi": {
                    "min": 16,
                    "max": 45,
                    "center": 25,
                    "scale": 1,
                    "coefficient": -0.035,
                },
                "hemoglobin_g_dl": {
                    "min": 7,
                    "max": 18,
                    "center": 12,
                    "scale": 1,
                    "coefficient": 0.18,
                },
                "albumin_g_dl": {
                    "min": 2,
                    "max": 5.5,
                    "center": 3.8,
                    "scale": 1,
                    "coefficient": 0.35,
                },
                "creatinine_mg_dl": {
                    "min": 0.3,
                    "max": 4,
                    "center": 1,
                    "scale": 1,
                    "coefficient": -0.25,
                },
            },
            "acceptance": {
                "min_cases": 100,
                "min_each_outcome": 10,
                "min_auc": 0.65,
                "max_brier": 0.25,
                "max_ece": 0.1,
            },
        }


def synthetic_holdout(spec, seed):
    """Known generator for a software demonstration; not an independent clinical cohort."""
    rng = random.Random(seed)
    rows = []
    for i in range(400):
        features = {
            "age_years": rng.randint(18, 90),
            "asa_class": rng.randint(1, 5),
            "emergency": rng.randint(0, 1),
            "bmi": round(rng.uniform(18, 40), 1),
            "hemoglobin_g_dl": round(rng.uniform(8, 16), 1),
            "albumin_g_dl": round(rng.uniform(2.5, 5), 2),
            "creatinine_mg_dl": round(rng.uniform(0.5, 3), 2),
        }
        probability, _ = predict(spec, features)
        rows.append(
            {
                "record_id": f"SYNTHETIC-{seed}-{i:04}",
                "features": features,
                "success": rng.random() < probability,
            }
        )
    return rows


def install_models(state, now):
    for i, spec in enumerate(model_specs()):
        if spec["id"] in state.v11.models.models:
            continue
        state.v11.models.command(
            {
                "action": "REGISTER_CLINICAL_MODEL",
                "actor": "bundled-demo-generator",
                "model": spec,
            },
            now,
        )
        model = state.v11.models.models[spec["id"]]
        fixture = MODEL_DIR / (spec["id"] + ".holdout.json")
        rows = (
            json.loads(fixture.read_text())
            if fixture.exists()
            else synthetic_holdout(spec, 1110 + i)
        )
        metrics = evaluate(model, rows)
        metrics.update(
            at=now.isoformat(),
            actor="synthetic-data-generator",
            source=DEMO_SOURCE,
            dataset_kind="SYNTHETIC_BENCHMARK",
            meaning="Artificial samples generated from the same teaching formula. These metrics do not measure clinical performance.",
        )
        model.update(
            status="DEMO_READY",
            bundled_demo=True,
            demo_activated_at=now.isoformat(),
            evaluations=[metrics],
            review=None,
        )


def enrich_case(state, case, now):
    """Give both opening fixtures and ongoing random intake complete linked demo records."""
    if not state.demo_enabled or not (
        case.get("is_demo") or case.get("source") == "HIS_RANDOM"
    ):
        return
    patient = state.hospital.patients.get(case.get("patient_id"))
    if not patient or not patient.get("is_demo"):
        return
    seed = int(hashlib.sha256(case["id"].encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    if not patient.get("demo_enriched") and patient["name"].startswith("Demo patient "):
        age = rng.randint(24, 78)
        patient.update(
            name=f"{FIRST_NAMES[seed % 8]} {LAST_NAMES[(seed // 8) % 8]} (Demo)",
            date_of_birth=f"{now.year - age}-01-15",
            sex=rng.choice(["FEMALE", "MALE"]),
            asa_class=rng.choice([1, 2, 2, 3, 4]),
            allergies=rng.choice(
                ["None reported (synthetic)", "Penicillin (synthetic)"]
            ),
            conditions=rng.choice(
                [
                    "None recorded (synthetic)",
                    "Controlled hypertension (synthetic)",
                    "Type 2 diabetes (synthetic)",
                ]
            ),
            notes=DEMO_SOURCE,
            demo_enriched=True,
        )
    inputs = state.v11.data.setdefault("clinical_inputs", {})
    previous = inputs.get(case["id"])
    if (
        not previous
        or previous.get("source") == DEMO_SOURCE
        and (now - aware(previous["observed_at"])).total_seconds() > 12 * 3600
    ):
        inputs[case["id"]] = {
            "patient_id": patient["id"],
            "observed_at": now.isoformat(),
            "source": DEMO_SOURCE,
            "actor": "demo-generator",
            "features": {
                "asa_class": patient.get("asa_class") or 2,
                "emergency": int(case["urgency"] in {"STAT", "EMERGENCY"}),
                "bmi": round(rng.uniform(20, 34), 1),
                "hemoglobin_g_dl": round(rng.uniform(10, 15), 1),
                "albumin_g_dl": round(rng.uniform(3, 4.8), 1),
                "creatinine_mg_dl": round(rng.uniform(0.6, 1.8), 1),
            },
        }


def seed_equipment(state, now):
    hospital = state.hospital
    for i, person in enumerate(hospital.staff.values()):
        if person.get("is_demo"):
            title = "Nurse" if person["role"] == "NURSE" else "Dr."
            person["name"] = (
                f"{title} {FIRST_NAMES[i % 8]} {LAST_NAMES[(i // 3) % 8]} {i + 1} (Demo)"
            )
    for i, room in enumerate(state.floorplan.operating_rooms()):
        key = "demo-spare-" + room["id"]
        hospital.devices[key] = {
            "id": key,
            "asset_tag": key,
            "name": f"Spare insufflator {i + 1} (Demo)",
            "type": "INSUFFLATOR",
            "room_id": room["id"],
            "status": "MAINTENANCE" if i == 0 else "AVAILABLE",
            "commissioned_on": (now - timedelta(days=900)).date().isoformat(),
            "design_life_hours": 18000.0,
            "runtime_hours": 7500.0,
            "maintenance_interval_hours": 2000.0,
            "last_service_hours": 6300.0,
            "service_history": [],
            "is_demo": True,
        }
    for i, device in enumerate(hospital.devices.values()):
        if not device.get("is_demo"):
            continue
        hours = 2400.0 + (i * 719) % 10500
        performance = 78.0 if device["status"] == "MAINTENANCE" else 90.0 + i % 8
        service_at = (now - timedelta(days=90)).isoformat()
        device.update(
            runtime_hours=hours,
            last_service_hours=max(0, hours - 1200),
            maintenance_interval_hours=2000.0,
            design_life_hours=18000.0 + (i % 4) * 3000,
            commissioned_on=(now - timedelta(days=400 + i * 20)).date().isoformat(),
            inspection_efficiency_percent=performance,
            inspection_passed=performance >= 82,
            inspection_source="SIMULATION",
            inspected_at=(now - timedelta(hours=1)).isoformat(),
            runtime_source="SYNTHETIC_DEMO_HISTORY",
            service_history=[
                {
                    "at": service_at,
                    "runtime_hours": max(0, hours - 1200),
                    "performance_percent": 99,
                    "source": "SIMULATION",
                    "notes": DEMO_SOURCE,
                    "cost_vnd": 0,
                }
            ],
        )
        state.v11.data.setdefault("device_engineering", {})[device["id"]] = {
            "minimum_performance_percent": 82.0,
            "replacement_cost_vnd": 120000000 + i * 3000000,
            "retire_on": (now + timedelta(days=450 + i * 15)).isoformat(),
            "source": DEMO_SOURCE,
        }
        state.v11.data.setdefault("inspections", {})[device["id"]] = [
            {
                "at": (now - timedelta(days=(7 - j) * 4, hours=1)).isoformat(),
                "runtime_hours": hours - (7 - j) * 100,
                "performance_percent": round(performance + (7 - j) * 0.28, 2),
                "source": "SIMULATION",
                "evidence": DEMO_SOURCE,
                "actor": "demo-generator",
            }
            for j in range(8)
        ]


def warm_room_models(state, now):
    for i, room in enumerate(state.rooms.values()):
        if not room["conditioned"]:
            continue
        model = copy.deepcopy(room)
        model.update(airflow_m3h=room["max_airflow_m3h"], temp_c=23.0, humidity=56.0)
        state.v11.data.setdefault("traits", {}).pop("SIMULATION:" + room["id"], None)
        for j in range(100):
            direction = -1 if (j // 25) % 2 == 0 else 1
            model["temp_c"] += (
                direction * (0.012 + i % 7 * 0.001) * (1 + 0.1 * math.sin(j))
            )
            model["humidity"] += (
                direction * (0.045 + i % 5 * 0.003) * (1 + 0.1 * math.cos(j))
            )
            thermal_observe(
                state.v11.data,
                model,
                now - timedelta(seconds=(100 - j) * 5),
                "SIMULATION",
                True,
            )
        trait = state.v11.data["traits"]["SIMULATION:" + room["id"]]
        trait.update(
            provenance=DEMO_SOURCE,
            previous={
                "at": now.isoformat(),
                "temp_c": room["temp_c"],
                "humidity": room["humidity"],
            },
        )
        state.hospital.thermal[room["id"]] = {
            "samples": 49,
            "cooling_c_per_min": 0.15 + i % 7 * 0.012,
            "at": now.isoformat(),
            "temp_c": room["temp_c"],
            "source": "SIMULATION",
        }


def seed_case_history(state, now):
    archive = {}
    for specialty, procedures in PROCEDURES.items():
        for procedure, low, high in procedures:
            key = hashlib.sha256(procedure.encode()).hexdigest()[:8]
            for j in range(32):
                case_id = f"demo-history-{key}-{j}"
                duration = round(
                    low + (high - low) * (0.25 + 0.5 * ((j * 7) % 31) / 31)
                )
                start = now - timedelta(days=40 + j * 9, hours=2)
                end = start + timedelta(minutes=duration)
                archive[case_id] = {
                    "id": case_id,
                    "case_label": "Synthetic history " + key + f"-{j:02}",
                    "source": "HIS_RANDOM",
                    "is_demo": True,
                    "procedure": procedure,
                    "specialty": specialty,
                    "status": "COMPLETED",
                    "urgency": "ELECTIVE",
                    "estimated_duration_min": duration,
                    "prep_minutes": 20,
                    "recovery_minutes": 45,
                    "created_at": start - timedelta(days=1),
                    "actual_start": start,
                    "actual_end": end,
                    "scheduled_start": start,
                    "scheduled_end": end,
                    "patient_id": None,
                    "staff_ids": [],
                    "scheduled_room_id": None,
                    "prep_room_id": None,
                    "recovery_room_id": None,
                    "notes": DEMO_SOURCE,
                }
                state.hospital.outcomes[case_id] = {
                    "case_id": case_id,
                    "procedure": procedure,
                    "is_demo": True,
                    "success": j % 11 != 0,
                    "endpoint": ENDPOINT,
                    "followup_days": 30,
                    "at": (end + timedelta(days=31)).isoformat(),
                    "evidence": DEMO_SOURCE,
                    "actor": "demo-generator",
                }
    state.store.save_records("case_archive", archive)
    return len(archive)


def new_case(state, now, room, index):
    specialty = room["capabilities"][0]
    procedure, low, high = PROCEDURES[specialty][index % len(PROCEDURES[specialty])]
    case = state.his._random_case(now)
    case.update(
        id=f"demo-case-{now.strftime('%Y%m%d%H%M%S')}-{index}",
        case_label=f"DEMO-{index + 1:03}",
        specialty=specialty,
        procedure=procedure,
        urgency="ELECTIVE",
        estimated_duration_min=round((low + high) / 2),
        prep_minutes=15,
        recovery_minutes=25,
        created_at=now - timedelta(hours=3),
        latest_start_at=now + timedelta(hours=24),
        notes=DEMO_SOURCE,
        is_demo=True,
    )
    state.hospital.prepare_case(case, now)
    return case


def seed_opening_schedule(state, now):
    rooms = state.floorplan.operating_rooms()
    state.his.cases = []
    order = (
        ([2, 0, 1] + list(range(3, len(rooms))))
        if len(rooms) >= 3
        else list(range(len(rooms)))
    )
    for i in order:
        room = rooms[i]
        case = new_case(state, now, room, i)
        state.his.cases.append(case)
        # Stagger recovery windows because the original floorplan has shared support capacity.
        if i == 0:
            start = now - timedelta(minutes=case["estimated_duration_min"] - 9)
        elif i == 1:
            start = now + timedelta(minutes=7)
        elif i == 2:
            start = now - timedelta(minutes=case["estimated_duration_min"] + 4)
        else:
            start = now + timedelta(minutes=40 + (i - 3) * 75)
        for _ in range(60):
            end = start + timedelta(minutes=case["estimated_duration_min"])
            valid, reason = state.hospital.slot_check(
                case, room["id"], start, end, commit=True
            )
            if valid:
                break
            start += timedelta(minutes=15)
        if not valid:
            case["constraint_reason"] = reason
            continue
        case.update(
            status="SCHEDULED",
            scheduled_room_id=room["id"],
            scheduled_start=start,
            scheduled_end=end,
        )
        state.v11.models.command(
            {
                "action": "RUN_CASE_PREDICTION",
                "case_id": case["id"],
                "actor": "demo-generator",
            },
            now,
        )
        if end <= now:
            case.update(status="COMPLETED", actual_start=start, actual_end=end)
        elif start <= now:
            case.update(status="IN_PROGRESS", actual_start=start)
            state.rooms[room["id"]].update(
                temp_c=20.2,
                humidity=50.5,
                airflow_m3h=state.rooms[room["id"]]["max_airflow_m3h"],
            )
        state.his.total_generated += 1
    for j in range(8):
        case = new_case(state, now, rooms[j % len(rooms)], len(rooms) + j)
        case.update(
            constraint_reason="Awaiting the next demo planning cycle",
            _retry_after=now.timestamp() + 300,
        )
        state.his.cases.append(case)
        state.his.total_generated += 1
    state.his.next_generation_at = now + timedelta(seconds=45)


def energy_at(state, timestamp, scopes):
    """Deterministic illustrative loads. No random values are generated in the UI."""
    # A single piecewise-hourly history integrates identically at every resolution.
    stamp = datetime.fromtimestamp(int(timestamp // 3600) * 3600, timezone.utc)
    day_fraction = (stamp.hour + stamp.minute / 60 + stamp.second / 3600) / 24
    seasonal = 1 + 0.1 * math.sin(2 * math.pi * stamp.timetuple().tm_yday / 365.25)
    rows = []
    for i, (scope, design) in enumerate(scopes):
        daily = 0.84 + 0.16 * math.sin(2 * math.pi * (day_fraction - 0.25))
        baseline = design * daily * seasonal
        reduction = 0.12 + 0.14 * (
            0.5 + 0.5 * math.sin(2 * math.pi * day_fraction + i * 0.37)
        )
        # A short above-baseline episode keeps signed savings visible in the demo.
        if i % 9 == 0 and stamp.hour == 13:
            reduction = -0.04
        actual = baseline * (1 - reduction)
        rows.append((scope, actual, baseline))
    return rows


def seed_energy(state, now):
    stop = int(now.timestamp())
    scopes = [
        (r["id"], max(0.1, state._standard_reference_room_power(r, now)))
        for r in state.rooms.values()
        if r["conditioned"]
    ]
    # The building includes a synthetic common load in addition to the floor rooms.
    reference, _ = state.energy_baseline.facility_reference_kw(now)
    scopes.insert(0, ("facility", reference or sum(power for _, power in scopes) * 1.2))
    tariff, emission = (
        state.hospital.config["tariff_vnd_kwh"],
        state.hospital.config["emission_kg_kwh"],
    )
    room_rows = []

    def flush():
        state.store.db.executemany(
            "INSERT OR IGNORE INTO energy VALUES(?,?,?,?,?,?,?,?,?)", room_rows
        )
        state.store.db.executemany(
            "INSERT OR IGNORE INTO energy_by_source VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(r[0], r[1], "SIMULATION", *r[2:]) for r in room_rows],
        )
        room_rows.clear()

    for tier, span in ((3600, 370 * 86400), (60, 86400), (1, 900)):
        start = (stop - span) // tier * tier
        for bucket in range(start, stop, tier):
            seconds = min(tier, stop - bucket)
            for scope, actual, baseline in energy_at(
                state, bucket + seconds / 2, scopes
            ):
                hours = seconds / 3600
                saving = (baseline - actual) * hours
                room_rows.append(
                    (
                        tier,
                        scope,
                        bucket,
                        actual * hours,
                        baseline * hours,
                        saving * tariff,
                        saving * emission,
                        seconds,
                        0.0,
                    )
                )
            if len(room_rows) >= 3000:
                flush()
        flush()
    state.store.last_prune = stop
    return {
        "days": 370,
        "minute_hours": 24,
        "second_minutes": 15,
        "through": datetime.fromtimestamp(stop, timezone.utc).isoformat(),
        "source": "SIMULATION",
    }


def activate(state, now):
    """Called under startup ownership, before the server accepts requests."""
    if not state.demo_enabled:
        return
    if state.hospital.config["mode"] != "SIMULATION":
        raise ValueError(
            "Demo requires its own simulation workspace; use --standard for connected data"
        )
    if any(
        not p.get("is_demo")
        for kind in ("patients", "staff", "devices")
        for p in getattr(state.hospital, kind).values()
    ) or any(
        c["source"] != "HIS_RANDOM" and not c.get("is_demo") for c in state.his.cases
    ):
        raise ValueError(
            "This database contains non-demo records. Start a new isolated demo workspace."
        )
    existing = state.store.get("demo_pack")
    install_models(state, now)
    if not existing:
        if state.store.db.execute("SELECT 1 FROM energy LIMIT 1").fetchone():
            raise ValueError(
                "Use a new demo workspace; existing energy history will not be overwritten"
            )
        seed_equipment(state, now)
        history_count = seed_case_history(state, now)
        state.hospital.config.update(capex_vnd=850000000.0, annual_opex_vnd=24000000.0)
        controlled = [r for r in state.rooms.values() if r["conditioned"]]
        total_area = sum(r["area_m2"] for r in controlled)
        state.v11.data["room_finance"] = {
            r["id"]: {
                "allocation_percent": 100 * r["area_m2"] / total_area,
                "actor": "demo-generator",
                "at": now.isoformat(),
                "source": DEMO_SOURCE,
            }
            for r in controlled
        }
        first = state.floorplan.operating_rooms()[0]
        state.v11.data["cost_events"] = [
            {
                "id": "demo-bms-service",
                "room_id": first["id"],
                "at": (now - timedelta(days=30)).isoformat(),
                "source": "SIMULATION",
                "cost_vnd": 1500000.0,
                "evidence": "Synthetic BMS service invoice",
                "actor": "demo-generator",
            }
        ]
        energy = seed_energy(state, now)
        existing = {
            "id": PACK_ID,
            "installed_at": now.isoformat(),
            "history_cases": history_count,
            "energy_history": energy,
            "source": DEMO_SOURCE,
        }
        state.store.put("demo_pack", existing)
        seed_opening_schedule(state, now)
    elif not any(
        c["status"] == "UNSCHEDULED"
        or c["status"] in {"SCHEDULED", "IN_PROGRESS"}
        and c.get("scheduled_end")
        and aware(c["scheduled_end"]) > now
        for c in state.his.cases
    ):
        state.store.save_records(
            "case_archive",
            {
                c["id"]: c
                for c in state.his.cases
                if c["status"] in {"COMPLETED", "CANCELLED"}
            },
        )
        seed_opening_schedule(state, now)
    for case in state.his.cases:
        if case["status"] in {"UNSCHEDULED", "SCHEDULED"}:
            enrich_case(state, case, now)
    warm_room_models(state, now)
    for room in state.rooms.values():
        state._apply_room_dynamics(room, 1, now)
    state.demo_info = {
        **existing,
        "active": True,
        "models": len(state.v11.models.models),
        "operating_rooms": len(state.floorplan.operating_rooms()),
        "equipment": len(state.hospital.devices),
        "patients": len(state.hospital.patients),
    }


def warm_charts(state, now):
    """Initialize the preserved command center from synthetic history, without adding energy."""
    records = state.store.db.execute(
        "SELECT bucket,actual,baseline,seconds FROM energy_by_source WHERE scope='facility' AND source='SIMULATION' AND tier=60 ORDER BY bucket DESC LIMIT 60"
    ).fetchall()
    state.roi["history"] = [
        {
            "time_label": datetime.fromtimestamp(r["bucket"]).strftime("%H:%M:%S"),
            "beam_load_kw": r["actual"] * 3600 / r["seconds"],
            "baseline_kw": r["baseline"] * 3600 / r["seconds"],
        }
        for r in reversed(records)
        if r["seconds"]
    ]
    state._update_roi(0, now)
    for room in state.rooms.values():
        if room["conditioned"]:
            room["trend"] = [
                {
                    "time": (now - timedelta(seconds=(36 - j) * 10)).isoformat(),
                    "temp_c": round(room["temp_c"] + 0.35 * (36 - j) / 36, 2),
                    "humidity": round(room["humidity"] + 1.2 * (36 - j) / 36, 2),
                    "airflow_m3h": round(
                        room["airflow_m3h"] * (0.94 + 0.06 * j / 36), 1
                    ),
                    "power_kw": round(
                        room["power_kw"] * (1 + 0.02 * math.sin(j / 6)), 3
                    ),
                }
                for j in range(36)
            ]
