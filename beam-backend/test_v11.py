"""v11 behavioral contracts. Model coefficients below are synthetic test fixtures only."""

import copy
import json
import sqlite3
from datetime import timedelta
import pytest
from test_v10 import fresh, case, patient, schedule, run, NOW, ROOT
from beam_state import BeamState
from engineering import asset_health, finance, thermal_forecast, thermal_observe
from clinical_models import predict, evaluate
from storage import Store


def command(s, action, **fields):
    return run(
        s.handle_command(
            {"action": action, "actor": "engineer", "_role": "ADMIN", **fields}
        )
    )


def model_fixture():
    return {
        "id": "synthetic-unit-test-v1",
        "name": "Synthetic fixture, no medical interpretation",
        "version": "1",
        "type": "LOGISTIC_V1",
        "endpoint": "NO_MAJOR_COMPLICATION_30D",
        "simulation_only": True,
        "specialties": ["GENERAL"],
        "procedures": ["Test procedure"],
        "source": "Synthetic unit-test algebra",
        "intended_population": "No real patients; software tests only",
        "intercept": 0,
        "features": {
            "age_years": {
                "min": 18,
                "max": 100,
                "center": 50,
                "scale": 1,
                "coefficient": 0.1,
            }
        },
        "acceptance": {
            "min_cases": 100,
            "min_each_outcome": 10,
            "min_auc": 0.65,
            "max_brier": 0.25,
            "max_ece": 0.1,
        },
    }


def holdout():
    return [
        {
            "record_id": str(i),
            "features": {"age_years": 80 if i % 2 else 20},
            "success": bool(i % 2),
        }
        for i in range(100)
    ]


def test_model_workflow_is_gated_versioned_and_durable(tmp_path):
    s = fresh(tmp_path / "beam.db")
    c = case(s)
    m = model_fixture()
    assert command(s, "REGISTER_CLINICAL_MODEL", model=m)["ok"]
    assert not command(s, "REGISTER_CLINICAL_MODEL", model=m)["ok"]
    assert s.hospital.clinical(c)["predicted_success_percent"] is None
    assert command(
        s,
        "EVALUATE_CLINICAL_MODEL",
        model_id=m["id"],
        rows=holdout(),
        source="Independent synthetic holdout",
    )["evaluation"]["numerical_gate_passed"]
    review = {
        "model_id": m["id"],
        "expires_at": (NOW() + timedelta(days=30)).isoformat(),
        "evidence": "Synthetic review fixture",
    }
    assert not command(s, "REVIEW_CLINICAL_MODEL", **review)["ok"]
    assert command(
        s,
        "REVIEW_CLINICAL_MODEL",
        actor="clinical-reviewer",
        _role="CLINICIAN",
        **review
    )["ok"]
    assert command(
        s,
        "SET_CASE_CLINICAL_INPUTS",
        case_id=c["id"],
        features={},
        observed_at=NOW().isoformat(),
        source="Synthetic inputs",
    )["ok"]
    result = s.hospital.clinical(c)
    assert 0 < result["predicted_success_percent"] < 100
    assert result["prediction_status"] == "SIMULATION_MODEL"
    recorded = command(
        s, "RUN_CASE_PREDICTION", case_id=c["id"], command_id="prediction-once"
    )
    assert recorded["ok"]
    assert command(
        s, "RUN_CASE_PREDICTION", case_id=c["id"], command_id="prediction-once"
    )["replayed"]
    again = BeamState(ROOT / "data/floorplan.json", db_path=tmp_path / "beam.db")
    assert again.hospital.clinical(again.his.case_by_id(c["id"]))["model_id"] == m["id"]
    assert (
        len(
            again.hospital.clinical(again.his.case_by_id(c["id"]))[
                "recorded_predictions"
            ]
        )
        == 1
    )
    s.hospital.config["mode"] = "CONNECTED"
    assert s.hospital.clinical(c)["predicted_success_percent"] is None
    s.hospital.config["mode"] = "SIMULATION"
    assert command(
        s, "REVOKE_CLINICAL_MODEL", model_id=m["id"], reason="Fixture removed"
    )["ok"]
    assert s.hospital.clinical(c)["predicted_success_percent"] is None


def test_model_rejects_missing_ood_duplicate_and_bad_calibration():
    m = model_fixture()
    with pytest.raises(ValueError):
        predict(m, {})
    with pytest.raises(ValueError):
        predict(m, {"age_years": 2})
    with pytest.raises(ValueError):
        evaluate(m, [holdout()[0]] * 100)
    bad = [{**r, "success": not r["success"]} for r in holdout()]
    assert not evaluate(m, bad)["numerical_gate_passed"]
    assert evaluate(m, holdout())["auc"] == 1


def test_roi_source_separation_allocation_and_cost_idempotence(tmp_path):
    s = fresh(tmp_path / "beam.db")
    ids = list(s.rooms)[:2]
    now = NOW()
    for measured, power in ((False, 3), (True, 7)):
        s.store.record_energy(
            now,
            1,
            [(ids[0], power, 5, measured), ("facility", power, 5, measured)],
            2200,
            0.7,
        )
    sim = s.store.history(ids[0], "second", source="SIMULATION")
    actual = s.store.history(ids[0], "second", source="CONNECTED")
    assert sim["totals"]["saved_kwh"] > 0 > actual["totals"]["saved_kwh"]
    assert command(s, "SET_ROOM_FINANCE", room_id=ids[0], allocation_percent=60)["ok"]
    assert not command(s, "SET_ROOM_FINANCE", room_id=ids[1], allocation_percent=50)[
        "ok"
    ]
    assert command(s, "SET_ROOM_FINANCE", room_id=ids[1], allocation_percent=40)["ok"]
    s.hospital.config["capex_vnd"] = 1000000
    cost = {
        "room_id": ids[0],
        "cost_vnd": 100,
        "evidence": "Incremental invoice",
        "command_id": "invoice1",
    }
    assert command(s, "RECORD_BMS_COST", **cost)["ok"]
    assert command(s, "RECORD_BMS_COST", **cost)["replayed"]
    summary = finance(s, s.v11.data, ids[0], "SIMULATION")
    assert summary["service_cost_vnd"] == 100
    assert summary["capex_vnd"] == 600000
    assert finance(s, s.v11.data, ids[0], "CONNECTED")["service_cost_vnd"] == 0
    assert summary["projected_payback_years"] is None
    assert summary["net_operating_savings_vnd"] < 0


def test_v10_migration_labels_mixed_history(tmp_path):
    path = tmp_path / "v10.db"
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE energy(tier INTEGER,scope TEXT,bucket INTEGER,actual REAL,baseline REAL,cost REAL,carbon REAL,seconds REAL,measured REAL,PRIMARY KEY(tier,scope,bucket));PRAGMA user_version=1;"
    )
    db.execute("INSERT INTO energy VALUES(3600,'facility',0,2,4,4400,1,100,50)")
    db.commit()
    db.close()
    store = Store(path)
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert (
        store.db.execute("SELECT source FROM energy_by_source").fetchone()[0]
        == "LEGACY_MIXED"
    )
    store.db.close()
    assert (
        Store(path).db.execute("SELECT COUNT(*) FROM energy_by_source").fetchone()[0]
        == 1
    )


def test_device_joint_life_trend_threshold_and_post_service_reset():
    s = fresh()
    d = next(iter(s.hospital.devices.values()))
    d["runtime_hours"] = 500
    now = NOW()
    rows = [
        {
            "runtime_hours": i * 100,
            "performance_percent": 100 - i * 2,
            "at": (now - timedelta(days=6 - i)).isoformat(),
        }
        for i in range(6)
    ]
    data = asset_health(d, {"minimum_performance_percent": 80}, rows)
    assert data["trend"]["r_squared"] == 1
    assert data["performance_rul_hours"] == pytest.approx(500)
    assert data["life_x_performance_percent"] == pytest.approx(87.75)
    d["service_history"] = [{"at": now.isoformat()}]
    assert (
        asset_health(d, {"minimum_performance_percent": 80}, rows)[
            "performance_rul_hours"
        ]
        is None
    )
    d["inspection_efficiency_percent"] = 50
    assert command(
        s,
        "SET_DEVICE_ENGINEERING",
        device_id=d["id"],
        minimum_performance_percent=80,
        evidence="OEM fixture",
    )["ok"]
    assert not s.hospital.device_public(d)["ready"]


def test_thermal_uses_distinct_observations_both_dimensions_and_source():
    data = {}
    s = fresh()
    r = copy.deepcopy(next(iter(s.rooms.values())))
    r.update(temp_c=25, humidity=60, airflow_m3h=r["max_airflow_m3h"])
    now = NOW()
    for i in range(16):
        at = now - timedelta(seconds=(15 - i) * 10)
        r.update(temp_c=25 - i * 0.03, humidity=60 - i * 0.1)
        thermal_observe(data, r, at, "CONNECTED", True, at)
        thermal_observe(data, r, at + timedelta(seconds=1), "CONNECTED", True, at)
    result = thermal_forecast(data, r, now, "CONNECTED", 20, 45)
    assert result["eligible"]
    assert all(d["samples"] == 15 for d in result["dimensions"])
    assert result["eta_minutes"] == max(d["eta_minutes"] for d in result["dimensions"])
    assert not thermal_forecast(data, r, now, "SIMULATION", 20, 45)["eligible"]
    assert not thermal_forecast(data, r, now + timedelta(hours=1), "CONNECTED", 20, 45)[
        "eligible"
    ]


def test_room_view_links_people_team_devices_forecast_energy_and_turnover():
    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    room = c["scheduled_room_id"]
    result = s.v11.room(room, NOW())
    assert result["current_case"]["patient"]["id"] == c["patient_id"]
    assert len(result["current_case"]["team"]) >= 3
    assert len(result["devices"]) >= 3
    assert {x["stage"] for x in result["forecast"]["timeline"]} == {
        "PRECONDITION",
        "SURGERY",
        "TURNOVER",
    }
    assert result["finance"]["scope"] == room
    c.update(
        status="COMPLETED",
        scheduled_end=NOW() - timedelta(minutes=1),
        actual_end=NOW() - timedelta(minutes=1),
    )
    assert s._room_policy(s.rooms[room], NOW())[-1] == "HIS_TURNOVER"


def test_schedule_preview_is_nonmutating_atomic_and_checks_changes():
    s = fresh()
    a = case(s, label="A")
    b = case(s, label="B")
    before = copy.deepcopy(s.his.cases)
    preview = command(s, "PREVIEW_SCHEDULE", case_ids=[a["id"], b["id"]])
    assert preview["ok"], preview
    assert s.his.cases == before
    plan = preview["plan"]
    assert len(plan["items"]) == 2
    applied = command(s, "APPLY_SCHEDULE_PLAN", plan_id=plan["id"])
    assert applied["ok"], applied
    assert all(c["status"] == "SCHEDULED" for c in s.his.cases)
    c = case(s, label="C")
    plan = command(s, "PREVIEW_SCHEDULE", case_ids=[c["id"]])["plan"]
    s.hospital.patients[c["patient_id"]]["active"] = False
    assert not command(s, "APPLY_SCHEDULE_PLAN", plan_id=plan["id"])["ok"]
    assert s.his.case_by_id(c["id"])["status"] == "UNSCHEDULED"


def test_gateway_requires_exact_fresh_proposal_feedback_and_persists(tmp_path):
    s = fresh(tmp_path / "gateway.db")
    s.hospital.config["mode"] = "CONNECTED"
    room = next(r for r in s.rooms.values() if r["conditioned"])
    now = NOW()
    rid = room["id"]
    s.ingest_telemetry(
        {
            "scope": rid,
            "timestamp": now.isoformat(),
            "power_kw": 2,
            "temp_c": 22,
            "humidity": 50,
            "airflow_m3h": 1000,
            "source": "BMS fixture",
        }
    )
    proposal = s.v11.targets(now)
    target = next(r for r in proposal["rooms"] if r["room_id"] == rid)
    payload = {
        "proposal_id": proposal["proposal_id"],
        "room_id": rid,
        "revision": proposal["revision"],
        "applied": True,
        "feedback": {k: v for k, v in target.items() if k.startswith("target_")},
        "detail": "PLC readback fixture",
    }
    with pytest.raises(ValueError):
        s.v11.receipt({**payload, "proposal_id": "unknown"}, "test", now)
    with pytest.raises(ValueError):
        s.v11.receipt(payload, "test", now + timedelta(seconds=16))
    with pytest.raises(ValueError):
        s.v11.receipt(
            {**payload, "feedback": {**payload["feedback"], "target_temp_c": 1}},
            "test",
            now,
        )
    receipt = s.v11.receipt(payload, "test", now)
    assert receipt["applied"]
    assert s.store.get("v11")["receipts"][rid]["proposal_id"] == proposal["proposal_id"]
    s.controls["temp_setpoint"] += 1
    with pytest.raises(ValueError):
        s.v11.receipt(payload, "test", now)


@pytest.mark.parametrize(
    "action",
    [
        "REGISTER_CLINICAL_MODEL",
        "SET_DEVICE_ENGINEERING",
        "SET_ROOM_FINANCE",
        "RECORD_BMS_COST",
        "PREVIEW_SCHEDULE",
        "SET_CASE_CLINICAL_INPUTS",
    ],
)
def test_new_commands_enforce_roles(action):
    result = command(fresh(), action, _role="VIEWER")
    assert not result["ok"] and "role" in result["message"]


def test_clinical_redaction_preserves_operational_data_and_original():
    from privacy import for_role

    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    raw = s.v11.room(c["scheduled_room_id"], NOW())
    redacted = for_role(raw, "OPERATOR")
    assert redacted["current_case"]["patient"].get("mrn") is None
    assert (
        redacted["current_case"]["clinical"]["prediction_status"]
        == "CLINICAL_ACCESS_REQUIRED"
    )
    assert raw["current_case"]["patient"]["mrn"] == "TEST"
    assert redacted["instant_energy"] == raw["instant_energy"]
    assert redacted["current_case"]["case"]["patient_id"] is None


def test_recent_gateway_receipt_survives_older_full_snapshot(tmp_path):
    path = tmp_path / "receipt.db"
    s = fresh(path)
    s.checkpoint()
    s.store.db.commit()
    s.v11.data["receipts"] = {"room": {"proposal_id": "newer-than-snapshot"}}
    s.store.put("v11", s.v11.data)
    s.store.db.commit()
    restored = BeamState(ROOT / "data/floorplan.json", db_path=path)
    assert restored.v11.data["receipts"]["room"]["proposal_id"] == "newer-than-snapshot"


def test_release_automation_clears_both_manual_overrides():
    s = fresh()
    r = next(r for r in s.rooms.values() if r["conditioned"])
    r.update(
        manual_mode="MAXIMUM_RUNNING",
        manual_targets={"temp_c": 22, "humidity": 50, "airflow_percent": 90},
    )
    assert command(s, "RELEASE_ROOM_AUTOMATION", room_id=r["id"])["ok"]
    assert r["manual_mode"] is None and r["manual_targets"] is None


def test_simulated_inspection_cannot_qualify_connected_equipment():
    s = fresh()
    d = next(iter(s.hospital.devices.values()))
    d.update(
        inspection_passed=True,
        inspection_efficiency_percent=99,
        inspection_source="SIMULATION",
    )
    s.hospital.config["mode"] = "CONNECTED"
    result = s.hospital.device_public(d)
    assert not result["ready"]
    assert result["engineering"]["measured_performance_percent"] is None


def test_legacy_command_center_roi_and_reservations_follow_mode(tmp_path):
    s = fresh(tmp_path / "mode.db")
    now = NOW()
    s.store.record_energy(now, 10, [("facility", 2, 5, False)], 2200, 0.7)
    s.store.record_energy(now, 10, [("facility", 7, 5, True)], 2200, 0.7)
    c = case(s)
    assert schedule(s, c)["ok"]
    c.update(source="HIS_RANDOM", status="COMPLETED", scheduled_end=now, actual_end=now)
    assert command(s, "SET_HOSPITAL_CONFIG", config={"mode": "CONNECTED"})["ok"]
    assert s.roi["total_kwh_saved"] == pytest.approx(-2 * 10 / 3600)
    assert s.roi["ledger_source"] == "CONNECTED"
    assert not s.his.cases
    assert c["id"] in s.store.records("case_archive")
    again = BeamState(ROOT / "data/floorplan.json", db_path=tmp_path / "mode.db")
    assert again.roi["total_kwh_saved"] == pytest.approx(-2 * 10 / 3600)
