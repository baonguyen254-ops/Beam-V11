"""Behavioral checks for the isolated, immediately usable English demo."""

import asyncio
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from beam_state import BeamState
from engineering import finance
from storage import Store

FLOORPLAN = Path(__file__).resolve().parent / "data" / "floorplan.json"


@pytest.fixture
def demo(tmp_path):
    state = BeamState(FLOORPLAN, db_path=tmp_path / "demo.sqlite3", demo=True)
    yield state
    state.store.db.close()


def command(s, action, **fields):
    return asyncio.run(
        s.handle_command(
            {"action": action, "actor": "demo-test", "_role": "ADMIN", **fields}
        )
    )


def test_demo_starts_with_every_requested_data_surface(demo):
    now = datetime.now(timezone.utc)
    assert demo.demo_info["operating_rooms"] == 8
    assert len(demo.v11.models.models) == 3
    assert len(demo.hospital.devices) == 32
    assert {c["status"] for c in demo.his.cases} >= {
        "SCHEDULED",
        "IN_PROGRESS",
        "COMPLETED",
        "UNSCHEDULED",
    }
    for c in demo.his.cases:
        clinical = demo.hospital.clinical(c)
        assert 0 < clinical["predicted_success_percent"] < 100
        assert clinical["prediction_status"] == "SIMULATION_MODEL"
        assert clinical["cohort"]["source"] == "SIMULATION"
        assert demo.hospital.patients[c["patient_id"]]["is_demo"]
    for r in demo.floorplan.operating_rooms():
        detail = demo.v11.room(r["id"], now)
        assert detail["forecast"]["thermal"]["eligible"]
        assert detail["control"]["virtual_bms"]
        assert detail["finance"]["projected_payback_years"] is not None
        assert demo.rooms[r["id"]]["trend"]
        for d in detail["devices"]:
            assert d["engineering"]["trend_samples"] == 8
            assert d["engineering"]["performance_rul_hours"] is not None
    assert all(
        t["eligible"] and t["source"] == "SIMULATION"
        for t in demo.hospital.insights(now)["duration_traits"]
    )
    assert demo.roi["history"] and demo.roi["beam_load_kw"] > 0


def test_demo_energy_resolutions_integrate_consistently(demo):
    end = int(datetime.now(timezone.utc).timestamp() // 3600) * 3600
    for scope in ("facility", demo.floorplan.operating_rooms()[0]["id"]):
        for resolution in ("second", "minute", "hour", "day", "month", "year"):
            report = demo.store.history(
                scope=scope, resolution=resolution, source="SIMULATION"
            )
            assert report["points"] and report["totals"]["observed_seconds"] > 0
            assert report["totals"]["measured_seconds"] == 0
        minutes = demo.store.history(
            scope=scope,
            resolution="minute",
            start=end - 3600,
            end=end,
            source="SIMULATION",
        )["totals"]
        hours = demo.store.history(
            scope=scope,
            resolution="hour",
            start=end - 3600,
            end=end,
            source="SIMULATION",
        )["totals"]
        for field in ("actual_kwh", "baseline_kwh", "savings_vnd", "observed_seconds"):
            assert minutes[field] == pytest.approx(hours[field], rel=1e-10)
        assert demo.store.history(scope=scope, source="CONNECTED")["points"] == []


def test_demo_predictions_are_computed_editable_and_persistent(demo):
    c = next(c for c in demo.his.cases if c["status"] == "UNSCHEDULED")
    before = demo.hospital.clinical(c)["predicted_success_percent"]
    inputs = copy.deepcopy(demo.v11.data["clinical_inputs"][c["id"]])
    asa = inputs["features"]["asa_class"]
    inputs["features"]["asa_class"] = asa + 1
    assert command(
        demo,
        "SET_CASE_CLINICAL_INPUTS",
        case_id=c["id"],
        observed_at=inputs["observed_at"],
        source="Edited synthetic demo inputs",
        features=inputs["features"],
    )["ok"]
    after = demo.hospital.clinical(c)["predicted_success_percent"]
    assert after < before
    saved = command(
        demo, "RUN_CASE_PREDICTION", case_id=c["id"], command_id="demo-prediction-once"
    )
    assert saved["ok"]
    assert command(
        demo, "RUN_CASE_PREDICTION", case_id=c["id"], command_id="demo-prediction-once"
    )["replayed"]
    assert len(demo.v11.data["predictions"][c["id"]]) == 1
    assert not saved["prediction"]["review"]
    assert all(
        m["status"] == "DEMO_READY" and m["review"] is None
        for m in demo.v11.models.models.values()
    )
    model_id = next(iter(demo.v11.models.models))
    fixture = (
        FLOORPLAN.parents[2] / "examples/demo/models" / (model_id + ".holdout.json")
    )
    evaluated = command(
        demo,
        "EVALUATE_CLINICAL_MODEL",
        model_id=model_id,
        rows=json.loads(fixture.read_text()),
        source="Bundled synthetic teaching benchmark",
    )
    assert evaluated["ok"]
    assert evaluated["evaluation"]["dataset_kind"] == "SYNTHETIC_BENCHMARK"
    assert demo.v11.models.models[model_id]["status"] == "DEMO_READY"
    assert demo.v11.models.models[model_id]["review"] is None


def test_demo_restart_does_not_duplicate_history_and_standard_cannot_use_demo_models(
    demo, tmp_path
):
    before = finance(demo, demo.v11.data)
    ids = {c["id"] for c in demo.his.cases}
    restored = BeamState(FLOORPLAN, db_path=tmp_path / "demo.sqlite3", demo=True)
    try:
        assert {c["id"] for c in restored.his.cases} == ids
        assert (
            finance(restored, restored.v11.data)["observed_seconds"]
            == before["observed_seconds"]
        )
        assert (
            finance(restored, restored.v11.data)["actual_kwh"] == before["actual_kwh"]
        )
        assert len(restored.v11.models.models) == 3
        assert not command(
            restored, "SET_HOSPITAL_CONFIG", config={"mode": "CONNECTED"}
        )["ok"]
        restored.demo_enabled = False
        assert (
            restored.v11.models.assessment(
                restored.his.cases[0], datetime.now(timezone.utc)
            )["predicted_success_percent"]
            is None
        )
    finally:
        restored.store.db.close()


def test_demo_rejects_connected_database_without_replacing_data(tmp_path):
    path = tmp_path / "connected.sqlite3"
    store = Store(path)
    store.put("config", {"mode": "CONNECTED"})
    store.put("sentinel", "preserve me")
    store.db.commit()
    store.db.close()
    with pytest.raises(ValueError, match="own simulation workspace"):
        BeamState(FLOORPLAN, db_path=path, demo=True)
    store = Store(path)
    assert store.get("sentinel") == "preserve me"
    assert store.get("config")["mode"] == "CONNECTED"
    assert not store.db.execute("SELECT 1 FROM energy LIMIT 1").fetchone()
    store.db.close()


def test_demo_needs_only_the_supplied_floorplan_as_real_input(tmp_path):
    standalone = tmp_path / "floorplan.json"
    standalone.write_bytes(FLOORPLAN.read_bytes())
    assert not standalone.with_name("energy_baseline.json").exists()
    assert not standalone.with_name("or_capabilities.json").exists()
    state = BeamState(standalone, db_path=tmp_path / "demo.sqlite3", demo=True)
    try:
        assert state.demo_info["operating_rooms"] == 8
        assert state.his.cases
        assert all(
            0 < state.hospital.clinical(c)["predicted_success_percent"] < 100
            for c in state.his.cases
        )
        assert state.store.history(source="SIMULATION")["points"]
        assert state.roi["beam_load_kw"] > 0
    finally:
        state.store.db.close()
