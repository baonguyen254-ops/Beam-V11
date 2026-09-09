"""Regression tests for v10 safety, persistence, resources, economics and API boundaries."""

import asyncio
import importlib
import json
import math
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from beam_state import BeamState
from storage import Store
from energy_model import EnergyBaseline, _profile
from tools.import_energyplus_sql import (
    extract_hourly_electric_kw,
    find_electricity_dictionary_index,
)

ROOT = Path(__file__).resolve().parent
NOW = lambda: datetime.now(timezone.utc)


def run(awaitable):
    return asyncio.run(awaitable)


def fresh(path=None):
    state = BeamState(ROOT / "data/floorplan.json", db_path=path)
    state.his.cases.clear()
    state.autopilot = False
    return state


def patient(s, name="P1"):
    result = run(
        s.handle_command(
            {
                "action": "UPSERT_PATIENT",
                "record": {
                    "mrn": name,
                    "name": name,
                    "date_of_birth": "1985-02-01",
                    "sex": "UNKNOWN",
                },
            }
        )
    )
    assert result["ok"], result
    return result["record_id"]


def case(s, pid=None, label="TEST"):
    result = run(
        s.handle_command(
            {
                "action": "ADD_EXTERNAL_CASE",
                "case_label": label,
                "procedure": "Test procedure",
                "specialty": "GENERAL",
                "urgency": "ELECTIVE",
                "estimated_duration_min": 60,
                "patient_id": pid or patient(s, label),
            }
        )
    )
    assert result["ok"], result
    return s.his.case_by_id(result["case_id"])


def schedule(s, c, start=None):
    start = start or NOW() + timedelta(hours=2)
    return run(
        s.handle_command(
            {
                "action": "MANUAL_SCHEDULE_CASE",
                "case_id": c["id"],
                "room_id": s.his._eligible_operating_rooms(c["specialty"])[0]["id"],
                "start": start.isoformat(),
            }
        )
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "TOGGLE_AUTOPILOT", "value": "false"},
        {"action": "TOGGLE_ENERGY_AI", "value": 1},
        {"action": "SET_LIGHTING", "value": True},
        {"action": "SET_LIGHTING", "value": float("nan")},
        {"action": "SET_LIGHTING", "value": float("inf")},
        {"action": "ADD_EXTERNAL_CASE", "estimated_duration_min": 1.5},
        {"action": "ADD_EXTERNAL_CASE", "estimated_duration_min": True},
        {"action": "ADD_EXTERNAL_CASE", "prep_minutes": 0},
        {"action": "ADD_EXTERNAL_CASE", "recovery_minutes": 10000},
        {"action": "ASSIGN_CASE", "staff_ids": "not-a-list"},
    ],
)
def test_reject_invalid_command_types(payload):
    s = fresh()
    before = s.controls.copy()
    assert not run(s.handle_command(payload))["ok"]
    assert s.controls == before


def test_idempotency_survives_restart_and_checks_payload(tmp_path):
    path = tmp_path / "beam.db"
    s = fresh(path)
    p = {"action": "SET_LIGHTING", "value": 42, "actor": "A", "command_id": "same"}
    assert run(s.handle_command(p))["ok"]
    again = BeamState(ROOT / "data/floorplan.json", db_path=path)
    assert run(again.handle_command(p))["replayed"] is True
    assert not run(again.handle_command({**p, "value": 43}))["ok"]
    assert not run(again.handle_command({**p, "_role": "VIEWER"}))["ok"]
    assert again.lighting["level_percent"] == 42


def test_registry_validation_and_durability(tmp_path):
    path = tmp_path / "beam.db"
    s = fresh(path)
    pid = patient(s)
    assert not run(
        s.handle_command(
            {
                "action": "UPSERT_PATIENT",
                "record": {
                    "mrn": "P1",
                    "name": "Duplicate",
                    "date_of_birth": "2000-01-01",
                    "sex": "UNKNOWN",
                },
            }
        )
    )["ok"]
    assert not run(
        s.handle_command(
            {
                "action": "UPSERT_PATIENT",
                "record": {"id": pid, "date_of_birth": "2999-01-01"},
            }
        )
    )["ok"]
    assert not run(
        s.handle_command(
            {"action": "UPSERT_PATIENT", "record": {"id": pid, "active": "false"}}
        )
    )["ok"]
    restored = BeamState(ROOT / "data/floorplan.json", db_path=path)
    assert restored.hospital.patients[pid]["date_of_birth"] == "1985-02-01"


def test_external_requires_patient_and_never_autostarts():
    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    c["scheduled_start"] = NOW() - timedelta(hours=2)
    c["scheduled_end"] = NOW() - timedelta(hours=1)
    s.his.generator_enabled = False
    s.his.simulation_enabled = True
    s.his.tick(NOW(), False)
    assert c["status"] == "SCHEDULED"
    assert not run(s.handle_command({"action": "START_CASE", "case_id": c["id"]}))["ok"]


def test_turnover_patient_and_team_constraints():
    s = fresh()
    pid = patient(s)
    a = case(s, pid, "A")
    start = NOW() + timedelta(hours=2)
    assert schedule(s, a, start)["ok"]
    b = case(s, pid, "B")
    assert not schedule(s, b, start + timedelta(minutes=30))["ok"]
    a = s.his.case_by_id(a["id"])
    b = s.his.case_by_id(b["id"])
    a.update(status="COMPLETED", actual_end=a["scheduled_end"])
    assert not schedule(s, b, a["scheduled_end"] + timedelta(minutes=10))["ok"]
    assert schedule(s, b, a["scheduled_end"] + timedelta(hours=2))["ok"]


def test_staff_unavailability_prevents_schedule():
    s = fresh()
    c = case(s)
    start = NOW() + timedelta(hours=2)
    for p in s.hospital.staff.values():
        p["unavailable"] = [
            {
                "start": (start - timedelta(days=1)).isoformat(),
                "end": (start + timedelta(days=1)).isoformat(),
            }
        ]
    result = schedule(s, c, start)
    assert not result["ok"]
    assert "No available surgeon" in result["message"]


def test_exhausted_assets_cannot_support_case():
    s = fresh()
    c = case(s)
    for d in s.hospital.devices.values():
        d["runtime_hours"] = d["design_life_hours"]
    result = schedule(s, c)
    assert not result["ok"]
    assert "device" in result["message"].lower()


def test_manual_mode_respects_reservations_and_physical_fault():
    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    rid = c["scheduled_room_id"]
    assert not run(
        s.handle_command(
            {"action": "SET_ROOM_MODE", "room_id": rid, "mode": "MINIMUM_RUNNING"}
        )
    )["ok"]
    assert run(s.handle_command({"action": "STRESS_TEST_PRESSURE"}))["ok"]
    assert not run(
        s.handle_command(
            {"action": "EMERGENCY_MODE", "mode": "Negative Pressure Isolation Mode"}
        )
    )["ok"]
    run(s.tick(1))
    assert s.rooms[rid]["control_source"] == "SAFETY_LOCK"


def test_lifecycle_gates_and_recovery_reservation():
    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    rid = c["scheduled_room_id"]
    r = s.rooms[rid]
    c.update(
        scheduled_start=NOW() - timedelta(seconds=1),
        consent_confirmed=True,
        preop_complete=True,
    )
    r.update(
        temp_c=r["target_temp_c"],
        humidity=r["target_humidity"],
        airflow_m3h=r["max_airflow_m3h"],
    )
    result = run(s.handle_command({"action": "START_CASE", "case_id": c["id"]}))
    assert result["ok"], result
    assert not run(
        s.handle_command(
            {"action": "CANCEL_CASE", "case_id": c["id"], "reason": "test"}
        )
    )["ok"]
    assert not run(
        s.handle_command(
            {"action": "SET_HOSPITAL_CONFIG", "config": {"mode": "CONNECTED"}}
        )
    )["ok"]
    assert run(s.handle_command({"action": "COMPLETE_CASE", "case_id": c["id"]}))["ok"]
    c = s.his.case_by_id(c["id"])
    assert c["actual_end"] >= c["actual_start"]
    assert c["recovery_room_id"]


def test_device_service_is_measured_and_cannot_reset_runtime():
    s = fresh()
    d = next(iter(s.hospital.devices.values()))
    d["runtime_hours"] = 100
    assert not run(
        s.handle_command(
            {"action": "UPSERT_DEVICE", "record": {"id": d["id"], "runtime_hours": 0}}
        )
    )["ok"]
    assert not run(
        s.handle_command(
            {
                "action": "UPSERT_DEVICE",
                "record": {"id": d["id"], "last_service_hours": 50},
            }
        )
    )["ok"]
    result = run(
        s.handle_command(
            {
                "action": "SERVICE_DEVICE",
                "device_id": d["id"],
                "efficiency_percent": 85,
                "cost_vnd": 10000,
                "notes": "Bench inspection record",
                "inspection_passed": False,
            }
        )
    )
    assert result["ok"]
    d = s.hospital.devices[d["id"]]
    assert (
        d["runtime_hours"] == 100
        and d["last_service_hours"] == 100
        and d["status"] == "OFFLINE"
    )
    assert not s.hospital.device_public(d)["ready"]
    assert len(d["service_history"]) == 1


def test_connected_no_fallback_or_new_credit_without_meter():
    s = fresh()
    assert run(
        s.handle_command(
            {"action": "SET_HOSPITAL_CONFIG", "config": {"mode": "CONNECTED"}}
        )
    )["ok"]
    run(s.tick(1))
    assert s.financial_summary()["observed_seconds"] == 0
    assert s.sterility["pressure_alarm"]
    assert not run(s.handle_command({"action": "RESTORE_PRESSURE"}))["ok"]
    assert not run(s.handle_command({"action": "STRESS_TEST_PRESSURE"}))["ok"]
    p = {
        "scope": "facility",
        "timestamp": NOW().isoformat(),
        "power_kw": 500,
        "source": "meter-1",
        "delta_p_pa": 3.2,
    }
    assert s.ingest_telemetry(p)["ok"]
    with pytest.raises(ValueError):
        s.ingest_telemetry(p)
    run(s.tick(1))
    assert s.financial_summary()["observed_seconds"] == pytest.approx(1)
    assert s.financial_summary()["measured_seconds"] == pytest.approx(1)
    s.hospital.meters["facility"]["timestamp"] = (
        NOW() - timedelta(minutes=1)
    ).isoformat()
    run(s.tick(1))
    assert s.financial_summary()["observed_seconds"] == pytest.approx(1)


def test_energy_signed_integral_bucket_splitting_tariff_and_restart(tmp_path):
    path = tmp_path / "ledger.db"
    store = Store(path)
    stamp = datetime(2026, 2, 1, tzinfo=timezone.utc)
    store.record_energy(
        stamp + timedelta(seconds=1), 2, [("facility", 20, 10, True)], 2000, 0.7
    )
    store.record_energy(
        stamp + timedelta(seconds=2), 1, [("facility", 0, 10, True)], 3000, 0.7
    )
    store.db.commit()
    store = Store(path)
    report = store.history(
        "facility", "second", stamp.timestamp() - 1, stamp.timestamp() + 3, "UTC"
    )
    assert len(report["points"]) == 3
    assert report["totals"]["saved_kwh"] == pytest.approx(-10 / 3600)
    assert report["totals"]["savings_vnd"] == pytest.approx(
        (-20 * 2000 + 10 * 3000) / 3600
    )
    months = store.history(
        "facility", "month", stamp.timestamp() - 3600, stamp.timestamp() + 3600, "UTC"
    )
    assert {p["period"] for p in months["points"]} == {"2026-01", "2026-02"}


def test_roi_does_not_invent_payback_with_short_history():
    s = fresh()
    s.hospital.config["capex_vnd"] = 1000000
    run(s.tick(1))
    f = s.financial_summary()
    assert f["projected_payback_years"] is None
    assert f["roi_percent"] == pytest.approx(
        (f["net_operating_savings_vnd"] - 1000000) / 10000
    )


def test_no_fabricated_clinical_prediction_and_mature_archive_outcomes():
    s = fresh()
    c = case(s)
    clinical = s.hospital.clinical(c)
    assert clinical["predicted_success_percent"] is None and clinical["cohort"] is None
    c.update(
        status="COMPLETED",
        actual_start=NOW() - timedelta(days=31, hours=1),
        actual_end=NOW() - timedelta(days=31),
    )
    s.checkpoint()
    s.store.db.commit()
    s.his.cases.clear()
    result = run(
        s.handle_command(
            {
                "action": "RECORD_OUTCOME",
                "case_id": c["id"],
                "success": True,
                "notes": "30-day follow-up completed",
            }
        )
    )
    assert result["ok"], result
    assert not s.hospital.outcomes[c["id"]]["is_demo"]
    for i in range(30):
        s.hospital.outcomes[str(i)] = {
            "procedure": c["procedure"],
            "success": i < 24,
            "is_demo": False,
        }
    stats = s.hospital.clinical(c)["cohort"]
    assert stats["cases"] == 31
    assert (
        0
        < stats["interval_95_percent"][0]
        < stats["observed_rate_percent"]
        < stats["interval_95_percent"][1]
        < 100
    )


def test_sql_import_rejects_timestep_and_partial_calendar():
    db = sqlite3.connect(":memory:")
    db.executescript(
        'CREATE TABLE ReportDataDictionary(ReportDataDictionaryIndex INTEGER,Name TEXT,ReportingFrequency TEXT,Units TEXT);INSERT INTO ReportDataDictionary VALUES(1,"Electricity:Facility","Timestep","J");'
    )
    with pytest.raises(ValueError, match="Hourly"):
        find_electricity_dictionary_index(db)
    db.execute('UPDATE ReportDataDictionary SET ReportingFrequency="Hourly"')
    db.executescript(
        "CREATE TABLE Time(TimeIndex INTEGER,EnvironmentPeriodIndex INTEGER,Interval INTEGER,WarmupFlag INTEGER,Month INTEGER,Day INTEGER,Hour INTEGER);CREATE TABLE ReportData(TimeIndex INTEGER,ReportDataDictionaryIndex INTEGER,Value REAL);INSERT INTO Time VALUES(1,1,60,0,1,1,1);INSERT INTO ReportData VALUES(1,1,3600000);"
    )
    with pytest.raises(ValueError, match="complete year"):
        extract_hourly_electric_kw(db)


def test_sql_failed_import_preserves_existing_baseline(tmp_path):
    db = tmp_path / "empty.sql"
    sqlite3.connect(db).close()
    out = tmp_path / "baseline.json"
    out.write_text('{"keep":"original"}')
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/import_energyplus_sql.py"),
            str(db),
            "--out",
            str(out),
        ],
        capture_output=True,
    )
    assert result.returncode != 0
    assert out.read_text() == '{"keep":"original"}'


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    path = tmp_path_factory.mktemp("api")
    os.environ["BEAM_DATA_DIR"] = str(path)
    import main
    from fastapi.testclient import TestClient

    with TestClient(
        main.app, base_url="http://testserver", headers={"Origin": "http://testserver"}
    ) as c:
        yield c, main, path


def test_api_setup_auth_csrf_and_roles(client):
    c, main, path = client
    assert c.get("/api/hospital").status_code == 401
    assert c.get("/state").status_code == 401
    assert c.get("/api/session").json()["needs_setup"]
    result = c.post(
        "/api/setup",
        json={
            "key": (path / "bootstrap-key.txt").read_text(),
            "username": "admin",
            "password": "testing-password-123",
        },
    )
    assert result.status_code == 200, result.text
    assert "httponly" in result.headers["set-cookie"].lower()
    assert not (path / "bootstrap-key.txt").exists()
    assert (
        c.post(
            "/api/commands",
            headers={"Origin": "https://evil.example"},
            json={"action": "SET_LIGHTING", "value": 40, "command_id": "csrf"},
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/commands", json={"action": "SET_LIGHTING", "value": 40}
        ).status_code
        == 422
    )
    assert c.get("/api/hospital").status_code == 200
    assert c.get("/api/integrations/targets").status_code == 200
    assert c.get("/api/unknown-route").status_code == 404
    assert (
        c.post(
            "/api/users",
            json={
                "username": "viewer",
                "password": "testing-password-456",
                "role": "VIEWER",
            },
        ).status_code
        == 200
    )
    assert c.post("/api/logout", json={}).status_code == 200
    assert c.get("/api/hospital").status_code == 401
    assert (
        c.post(
            "/api/login",
            json={"username": "viewer", "password": "testing-password-456"},
        ).status_code
        == 200
    )
    result = c.post(
        "/api/commands",
        json={
            "action": "SET_LIGHTING",
            "value": 42,
            "command_id": "spoof",
            "actor": "ADMIN",
            "_role": "ADMIN",
        },
    )
    assert result.status_code == 422 and not result.json()["ok"]
    assert c.get("/api/users").status_code == 403
    assert c.get("/api/energy?resolution=second&format=csv").status_code == 200
    assert c.get("/api/energy?scope=unknown").status_code == 422


def test_websocket_rejects_untrusted_origin(client):
    c, main, path = client
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws", headers={"Origin": "https://evil.example"}):
            pass


def test_new_frontend_commands_have_backend_and_security_hooks():
    src = (ROOT.parent / "beam-frontend/src/HospitalWorkspace.tsx").read_text()
    for action in [
        "UPSERT_PATIENT",
        "UPSERT_STAFF",
        "UPSERT_DEVICE",
        "SERVICE_DEVICE",
        "UPDATE_CASE",
        "START_CASE",
        "COMPLETE_CASE",
        "RECORD_OUTCOME",
        "RECORD_CLINICAL_ESTIMATE",
        "SET_HOSPITAL_CONFIG",
    ]:
        assert action in src and action in (ROOT / "runtime.py").read_text()
    app = (ROOT.parent / "beam-frontend/src/App.tsx").read_text()
    assert "MISMATCH" in app and "6000" in app and "reconcile(commandId)" in app
    assert "document.fullscreenElement ?? document.body" in app
    assert "unscheduled.slice(0, 8)" not in app


def test_baseline_calendar_alignment_handles_timezone_and_leap_day():
    baseline = EnergyBaseline(
        calibrated=True,
        source="TEST",
        hourly_electric_kw=list(range(8760)),
        metadata={"timezone": 7},
    )
    # At 17:00 UTC it is midnight March 1 in the EPW local standard-time profile.
    assert (
        baseline.hourly_reference_kw(datetime(2024, 2, 29, 17, tzinfo=timezone.utc))
        == 59 * 24
    )
    assert (
        baseline.hourly_reference_kw(datetime(2024, 2, 29, 0, tzinfo=timezone.utc))
        == 58 * 24 + 7
    )
    assert (
        baseline.hourly_reference_kw(datetime(2026, 3, 1, 0, tzinfo=timezone.utc))
        == 59 * 24 + 7
    )
    month = EnergyBaseline(
        calibrated=True, source="TEST", monthly_mean_electric_kw=list(range(1, 13))
    )
    assert (
        month.monthly_mean_reference_kw(datetime(2026, 1, 31, 17, tzinfo=timezone.utc))
        == 2
    )


def test_nonfinite_baseline_values_rejected():
    for value in (float("nan"), float("inf"), -1, True):
        with pytest.raises(ValueError):
            _profile([value] * 12, allowed_lengths={12}, field="test")


def test_sql_complete_year_accepted_but_duplicate_calendar_rejected():
    db = sqlite3.connect(":memory:")
    db.executescript(
        'CREATE TABLE ReportDataDictionary(ReportDataDictionaryIndex INTEGER,Name TEXT,ReportingFrequency TEXT,Units TEXT);INSERT INTO ReportDataDictionary VALUES(1,"Electricity:Facility","Hourly","J");CREATE TABLE Time(TimeIndex INTEGER,EnvironmentPeriodIndex INTEGER,Interval INTEGER,WarmupFlag INTEGER,Month INTEGER,Day INTEGER,Hour INTEGER);CREATE TABLE ReportData(TimeIndex INTEGER,ReportDataDictionaryIndex INTEGER,Value REAL);'
    )
    beginning = datetime(2023, 1, 1)
    rows = []
    for i in range(8760):
        d = beginning + timedelta(hours=i)
        rows.append((i + 1, 1, 60, 0, d.month, d.day, d.hour + 1))
    db.executemany("INSERT INTO Time VALUES(?,?,?,?,?,?,?)", rows)
    db.executemany(
        "INSERT INTO ReportData VALUES(?,1,3600000)", [(i + 1,) for i in range(8760)]
    )
    values, metadata = extract_hourly_electric_kw(db)
    assert len(values) == 8760 and sum(values) == 8760
    db.execute("UPDATE Time SET Hour=1 WHERE TimeIndex=2")
    with pytest.raises(ValueError, match="calendar"):
        extract_hourly_electric_kw(db)


def test_external_intake_cannot_remove_core_device_requirements():
    s = fresh()
    pid = patient(s)
    before = len(s.his.cases)
    result = run(
        s.handle_command(
            {
                "action": "ADD_EXTERNAL_CASE",
                "specialty": "GENERAL",
                "urgency": "ELECTIVE",
                "procedure": "Test",
                "estimated_duration_min": 60,
                "patient_id": pid,
                "required_device_types": [],
            }
        )
    )
    assert not result["ok"] and len(s.his.cases) == before


def test_active_case_inventory_and_team_cannot_be_modified():
    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    c["status"] = "IN_PROGRESS"
    device = next(
        d for d in s.hospital.devices.values() if d["room_id"] == c["scheduled_room_id"]
    )
    for payload in [
        {
            "action": "UPSERT_DEVICE",
            "record": {"id": device["id"], "status": "OFFLINE"},
        },
        {
            "action": "UPSERT_STAFF",
            "record": {"id": c["staff_ids"][0], "active": False},
        },
        {
            "action": "UPSERT_PATIENT",
            "record": {"id": c["patient_id"], "active": False},
        },
    ]:
        assert not run(s.handle_command(payload))["ok"]


def test_terminal_archive_survives_live_cache_pruning_and_restart(tmp_path):
    path = tmp_path / "archive.db"
    s = fresh(path)
    c = case(s)
    assert run(
        s.handle_command(
            {
                "action": "CANCEL_CASE",
                "case_id": c["id"],
                "reason": "No longer required",
            }
        )
    )["ok"]
    s.his.cases.clear()
    s.checkpoint()
    s.store.db.commit()
    other = BeamState(ROOT / "data/floorplan.json", db_path=path)
    assert other.store.records("case_archive")[c["id"]]["status"] == "CANCELLED"


def test_connected_isolation_does_not_mask_missing_pressure():
    s = fresh()
    s.hospital.config["mode"] = "CONNECTED"
    s.emergency_mode = "Negative Pressure Isolation Mode"
    s._update_sterility(1)
    room = s.rooms[s.floorplan.operating_rooms()[0]["id"]]
    assert s._room_policy(room, NOW())[-1] == "SAFETY_LOCK"


def test_support_room_activity_uses_assignment_and_actual_completion():
    s = fresh()
    c = case(s)
    assert schedule(s, c)["ok"]
    now = NOW()
    c.update(
        scheduled_start=now + timedelta(minutes=5),
        scheduled_end=now + timedelta(minutes=65),
    )
    assert s.his.room_activity(c["prep_room_id"], "PREOP", now) == "PREOP_ACTIVE"
    assert s.his.room_activity("unassigned-preop", "PREOP", now) is None
    c.update(
        scheduled_start=now - timedelta(hours=2),
        scheduled_end=now - timedelta(minutes=10),
    )
    assert s.his.room_activity(c["recovery_room_id"], "RECOVERY", now) is None
    c["status"] = "COMPLETED"
    c["actual_end"] = c["scheduled_end"]
    assert (
        s.his.room_activity(c["recovery_room_id"], "RECOVERY", now) == "RECOVERY_ACTIVE"
    )
