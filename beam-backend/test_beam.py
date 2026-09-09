import asyncio
import math
from datetime import datetime, timedelta
from pathlib import Path

from beam_state import BeamState, EMISSION_KG_PER_KWH, TARIFF_VND_PER_KWH
from floorplan_model import load_floorplan
from his_engine import HISEngine


DATA = Path(__file__).resolve().parent / "data" / "floorplan.json"


def run(coro):
    return asyncio.run(coro)


def fresh():
    return BeamState(DATA)


def test_floorplan_geometry_and_english_mapping():
    fp = load_floorplan(DATA)
    assert len(fp.rooms) == 62
    assert len(fp.doors) == 88
    assert len(fp.operating_rooms()) == 8
    assert len(fp.rooms_by_category("PREP")) == 4
    assert len(fp.rooms_by_category("RECOVERY")) == 1
    assert len(fp.rooms_by_category("CORRIDOR")) == 4
    assert [r["name"] for r in fp.operating_rooms()] == [f"Operating Room {i}" for i in range(1, 9)]
    assert all(r["area_m2"] > 0 for r in fp.rooms)



def test_osm_crosscheck_contains_all_floorplan_space_handles():
    fp = load_floorplan(DATA)
    osm = (DATA.parent / "Hospital.osm").read_text(encoding="utf-8", errors="ignore")
    handles = [r["openstudio_handle"] for r in fp.rooms if r.get("openstudio_handle")]
    assert len(handles) == 62
    assert all(handle in osm for handle in handles)

def test_door_graph_has_real_connectivity():
    fp = load_floorplan(DATA)
    connected = [d for d in fp.doors if len(d["room_ids"]) == 2]
    assert len(connected) == 88
    recovery = fp.rooms_by_category("RECOVERY")[0]
    assert fp.adjacency[recovery["id"]]
    assert any(fp.shortest_path(or_room["id"], recovery["id"]) for or_room in fp.operating_rooms())


def test_capabilities_are_explicit_not_claimed_from_openstudio():
    fp = load_floorplan(DATA)
    for room in fp.operating_rooms():
        assert room["capabilities"]
        assert room["capability_source"] == "BEAM_DEMO_CONFIG_NOT_OPENSTUDIO"


def test_his_bootstrap_is_auto_scheduled_when_ai_on():
    s = fresh()
    his = s.to_dict()["his"]
    assert his["scheduler"]["unscheduled_count"] == 0
    assert len(his["cases"]) == 10
    assert all(c["status"] == "SCHEDULED" for c in his["cases"])


def test_ai_off_external_case_enters_red_manual_queue_then_ai_on_schedules():
    s = fresh()
    run(s.handle_command({"action": "TOGGLE_AUTOPILOT", "value": False}))
    result = run(s.handle_command({
        "action": "ADD_EXTERNAL_CASE",
        "case_label": "TRAUMA-X",
        "procedure": "Emergency fracture stabilization",
        "specialty": "TRAUMA",
        "urgency": "EMERGENCY",
        "estimated_duration_min": 90,
    }))
    assert result["ok"] is True
    state = s.to_dict()["his"]
    case = next(c for c in state["cases"] if c["id"] == result["case_id"])
    assert case["status"] == "UNSCHEDULED"
    assert case["manual_action_required"] is True
    assert state["scheduler"]["health"] == "CRITICAL"

    # v10 requires a registered patient before allocating a real external case.
    patient = run(s.handle_command({"action":"UPSERT_PATIENT","record":{"mrn":"TEST-1","name":"Test patient","date_of_birth":"1980-01-01","sex":"UNKNOWN"}}))
    assert patient["ok"]
    assert run(s.handle_command({"action":"ASSIGN_CASE","case_id":result["case_id"],"patient_id":patient["record_id"]}))["ok"]
    run(s.handle_command({"action": "TOGGLE_AUTOPILOT", "value": True}))
    case = next(c for c in s.to_dict()["his"]["cases"] if c["id"] == result["case_id"])
    assert case["status"] == "SCHEDULED"
    room = s.rooms[case["scheduled_room_id"]]
    assert "TRAUMA" in room["capabilities"]


def test_external_case_validation():
    s = fresh()
    bad = run(s.handle_command({
        "action": "ADD_EXTERNAL_CASE",
        "procedure": "X",
        "specialty": "NOT_REAL",
        "urgency": "STAT",
        "estimated_duration_min": 30,
    }))
    assert bad["ok"] is False


def test_manual_schedule_rejects_wrong_capability():
    s = fresh()
    run(s.handle_command({"action": "TOGGLE_AUTOPILOT", "value": False}))
    result = run(s.handle_command({
        "action": "ADD_EXTERNAL_CASE",
        "procedure": "Cardiac emergency",
        "specialty": "CARDIAC",
        "urgency": "EMERGENCY",
        "estimated_duration_min": 120,
    }))
    wrong_room = next(r for r in s.floorplan.operating_rooms() if "CARDIAC" not in r["capabilities"])
    manual = run(s.handle_command({
        "action": "MANUAL_SCHEDULE_CASE",
        "case_id": result["case_id"],
        "room_id": wrong_room["id"],
        "start": (datetime.now().astimezone() + timedelta(minutes=10)).isoformat(),
    }))
    assert manual["ok"] is False


def test_room_control_is_server_authoritative():
    s = fresh()
    or1 = s.floorplan.operating_rooms()[0]["id"]
    result = run(s.handle_command({"action": "SET_ROOM_MODE", "room_id": or1, "mode": "MAXIMUM_RUNNING"}))
    assert result["ok"] is True
    run(s.tick(2.0))
    assert s.rooms[or1]["control_source"] == "MANUAL_MAX"
    assert abs(s.rooms[or1]["target_airflow_m3h"] - s.rooms[or1]["max_airflow_m3h"]) < 1.0


def test_unconditioned_space_rejects_hvac_override():
    s = fresh()
    stair = next(r for r in s.rooms.values() if r["category"] == "STAIRS")
    result = run(s.handle_command({"action": "SET_ROOM_MODE", "room_id": stair["id"], "mode": "MAXIMUM_RUNNING"}))
    assert result["ok"] is False


def test_setpoints_affect_real_dynamics():
    s = fresh()
    or1 = s.floorplan.operating_rooms()[0]["id"]
    run(s.handle_command({"action": "SET_ROOM_MODE", "room_id": or1, "mode": "MAXIMUM_RUNNING"}))
    run(s.handle_command({"action": "SET_TEMPERATURE_SETPOINT", "value": 18.0}))
    run(s.handle_command({"action": "SET_HUMIDITY_SETPOINT", "value": 45.0}))
    before_t = s.rooms[or1]["temp_c"]
    before_rh = s.rooms[or1]["humidity"]
    for _ in range(60):
        run(s.tick(2.0))
    assert s.rooms[or1]["target_temp_c"] == 18.0
    assert s.rooms[or1]["target_humidity"] == 45.0
    assert s.rooms[or1]["temp_c"] < before_t
    assert s.rooms[or1]["humidity"] < before_rh


def test_pressure_safety_overrides_manual_mode():
    s = fresh()
    s.his.cases.clear()  # Isolate pressure arbitration from the v10 reservation guard.
    or1 = s.floorplan.operating_rooms()[0]["id"]
    run(s.handle_command({"action": "SET_ROOM_MODE", "room_id": or1, "mode": "MINIMUM_RUNNING"}))
    run(s.handle_command({"action": "STRESS_TEST_PRESSURE"}))
    run(s.tick(2.0))
    assert s.rooms[or1]["status"] == "ALARM"
    assert s.rooms[or1]["control_source"] == "SAFETY_LOCK"
    result = run(s.handle_command({"action": "EMERGENCY_MODE", "mode": "Negative Pressure Isolation Mode"}))
    assert result["ok"] is False
    run(s.handle_command({"action": "RESTORE_PRESSURE"}))
    run(s.tick(2.0))
    assert s.rooms[or1]["control_source"] == "MANUAL_MIN"


def test_negative_isolation_is_intentional_when_no_fault():
    s = fresh()
    result = run(s.handle_command({"action": "EMERGENCY_MODE", "mode": "Negative Pressure Isolation Mode"}))
    assert result["ok"] is True
    for _ in range(10):
        run(s.tick(2.0))
    assert s.sterility["target_delta_p_pa"] == -2.5
    assert s.sterility["pressure_alarm"] is False
    assert all(r["control_source"] == "NEGATIVE_ISOLATION" for r in s.rooms.values() if r["conditioned"])


def test_roi_ledger_is_consistent_and_live():
    s = fresh()
    assert math.isclose(s.roi["financial_savings_vnd"], s.roi["total_kwh_saved"] * TARIFF_VND_PER_KWH)
    assert math.isclose(s.roi["co2_reduction_kg"], s.roi["total_kwh_saved"] * EMISSION_KG_PER_KWH)
    n = len(s.roi["history"])
    run(s.tick(2.0))
    assert len(s.roi["history"]) == n + 1
    assert s.roi["beam_load_kw"] > 0
    assert s.roi["baseline_kw"] > s.roi["beam_load_kw"]


def test_floorplan_only_sent_when_requested():
    s = fresh()
    assert "floorplan" not in s.to_dict(include_floorplan=False)
    state = s.to_dict(include_floorplan=True)
    assert len(state["floorplan"]["rooms"]) == 62


def test_entropy_generator_produces_unique_ids_and_nonfixed_next_time():
    fp = load_floorplan(DATA)
    a = HISEngine(fp)
    b = HISEngine(fp)
    ids_a = {c["id"] for c in a.cases}
    ids_b = {c["id"] for c in b.cases}
    assert ids_a.isdisjoint(ids_b)
    assert a.next_generation_at != b.next_generation_at


def test_circulation_paths_are_based_on_door_graph():
    s = fresh()
    cases = [c for c in s.to_dict()["his"]["cases"] if c["scheduled_room_id"]]
    assert cases
    for case in cases:
        path = case["circulation_path"]
        assert case["scheduled_room_id"] in path
        for a, b in zip(path, path[1:]):
            assert b in s.floorplan.adjacency[a]


def test_invalid_commands_are_rejected():
    s = fresh()
    assert run(s.handle_command({"action": "SET_TEMPERATURE_SETPOINT", "value": 99}))["ok"] is False
    assert run(s.handle_command({"action": "NO_SUCH_COMMAND"}))["ok"] is False



def test_energy_ai_is_separate_and_changes_idle_policy():
    s = fresh()
    office = next(r for r in s.rooms.values() if r["category"] == "OFFICE")
    run(s.tick(2.0))
    optimized_target = office["target_airflow_m3h"]
    result = run(s.handle_command({"action": "TOGGLE_ENERGY_AI", "value": False}))
    assert result["ok"] is True
    run(s.tick(2.0))
    standard_target = office["target_airflow_m3h"]
    assert standard_target > optimized_target
    assert office["control_source"] == "STANDARD_STANDBY"
    state = s.to_dict()
    assert state["energy_ai"]["enabled"] is False


def test_v82_openstudio_report_baseline_is_loaded_without_synthetic_session_history():
    s = fresh()
    assert s.roi["total_kwh_saved"] == 0.0
    assert s.roi["history"] == []
    assert s.energy_baseline.calibrated is True
    assert s.energy_baseline.calibration_tier == "FULL_ANNUAL_TABULAR"
    assert s.energy_baseline.reference_resolution == "MONTHLY_MEAN"
    assert math.isclose(s.energy_baseline.site_eui_kwh_m2_year, 163.4111, rel_tol=1e-5)
    assert math.isclose(s.energy_baseline.annual_electricity_kwh, 604134.19, rel_tol=1e-6)
    assert len(s.energy_baseline.monthly_electricity_kwh or []) == 12
    run(s.tick(2.0))
    assert len(s.roi["history"]) == 1
    assert s.roi["total_beam_kwh"] > 0
    assert s.roi["total_reference_kwh"] > 0
    public = s.to_dict()["roi"]
    provenance = public["baseline_provenance"]
    assert provenance["calibrated"] is True
    assert provenance["calibration_tier"] == "FULL_ANNUAL_TABULAR"
    assert provenance["reference_resolution"] == "MONTHLY_MEAN"
    assert provenance["has_hourly_profile"] is False
    assert provenance["has_monthly_profile"] is True
    assert public["calibration_method"] == "MONTHLY_MEAN_FACILITY_REFERENCE_END_USE_SCALED_CONTROL_RATIO"
    assert 0.42 < public["control_eligible_end_use_fraction"] < 0.44
    assert abs(public["applied_control_delta_kw"]) <= abs(public["raw_modeled_delta_kw"])


def test_energy_ai_never_beats_pressure_safety():
    s = fresh()
    room = next(r for r in s.rooms.values() if r["category"] == "OPERATING_ROOM")
    assert run(s.handle_command({"action": "TOGGLE_ENERGY_AI", "value": True}))["ok"]
    assert run(s.handle_command({"action": "STRESS_TEST_PRESSURE"}))["ok"]
    run(s.tick(2.0))
    assert room["status"] == "ALARM"
    assert room["control_source"] == "SAFETY_LOCK"
    assert s.energy_ai["status"] == "SAFETY_OVERRIDE"

def main():
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    passed = 0
    for test in tests:
        test()
        passed += 1
        print(f"PASS {test.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")


if __name__ == "__main__":
    main()


def test_room_trends_utilization_and_power_density_are_tick_derived():
    s = fresh()
    or1 = s.floorplan.operating_rooms()[0]["id"]
    assert s.rooms[or1]["trend"] == []
    run(s.handle_command({"action": "SET_ROOM_MODE", "room_id": or1, "mode": "MAXIMUM_RUNNING"}))
    for _ in range(3):
        run(s.tick(2.0))
    public = next(r for r in s.to_dict()["rooms"] if r["id"] == or1)
    assert len(public["trend"]) >= 1
    assert public["session_observed_seconds"] >= 6.0
    assert public["power_density_w_m2"] >= 0.0
    assert 0.0 <= public["session_utilization_percent"] <= 100.0


def test_room_alarm_hierarchy_surfaces_pressure_fault_as_critical():
    s = fresh()
    run(s.handle_command({"action": "STRESS_TEST_PRESSURE"}))
    run(s.tick(2.0))
    conditioned = [r for r in s.to_dict()["rooms"] if r["conditioned"]]
    assert conditioned
    assert all(r["alarm_severity"] == "CRITICAL" for r in conditioned)
    assert all(r["alarm_reasons"] for r in conditioned)


def test_v7_atomic_control_profiles_and_active_or_guardrail():
    s = fresh()
    result = run(s.handle_command({"action": "APPLY_CONTROL_PROFILE", "profile": "ENERGY_BALANCED"}))
    assert result["ok"] is True
    assert s.controls == {"temp_setpoint": 21.0, "rh_setpoint": 50.0, "fan_speed": 60.0}
    assert s.lighting["level_percent"] == 45
    or1 = next(r for r in s.rooms.values() if r["category"] == "OPERATING_ROOM")
    or1["status"] = "ACTIVE"
    blocked = run(s.handle_command({"action": "APPLY_CONTROL_PROFILE", "profile": "NIGHT_SETBACK"}))
    assert blocked["ok"] is False


def test_v7_pressure_policy_and_real_pressure_trend():
    s = fresh()
    result = run(s.handle_command({"action": "SET_PRESSURE_POLICY", "policy": "ENHANCED"}))
    assert result["ok"] is True
    assert s.sterility["positive_pressure_policy"] == "ENHANCED"
    for _ in range(3):
        run(s.tick(2.0))
    public = s.to_dict()["sterility"]
    assert public["positive_pressure_policy"] == "ENHANCED"
    assert len(public["trend"]) >= 1
    assert "trend_sample_accumulator_s" not in public
    run(s.handle_command({"action": "STRESS_TEST_PRESSURE"}))
    rejected = run(s.handle_command({"action": "SET_PRESSURE_POLICY", "policy": "STANDARD"}))
    assert rejected["ok"] is False



def test_v8_per_room_manual_targets_are_persistent_and_safety_bounded():
    s = fresh()
    room = next(r for r in s.rooms.values() if r["conditioned"] and r["category"] == "PREP")
    result = run(s.handle_command({
        "action": "SET_ROOM_MANUAL_TARGETS",
        "room_id": room["id"],
        "temp_c": 19.5,
        "humidity": 48,
        "airflow_percent": 65,
    }))
    assert result["ok"] is True
    run(s.tick(2.0))
    public = next(r for r in s.to_dict()["rooms"] if r["id"] == room["id"])
    assert public["manual_targets"] == {"temp_c": 19.5, "humidity": 48.0, "airflow_percent": 65.0}
    assert public["target_temp_c"] == 19.5
    assert public["target_humidity"] == 48.0
    assert public["control_source"] == "MANUAL_TARGETS"
    reset = run(s.handle_command({"action": "RESET_ROOM_MANUAL_TARGETS", "room_id": room["id"]}))
    assert reset["ok"] is True
    assert s.rooms[room["id"]]["manual_targets"] is None


def test_v8_room_manual_target_validation_rejects_unsafe_ranges():
    s = fresh()
    room = next(r for r in s.rooms.values() if r["conditioned"])
    bad = run(s.handle_command({"action": "SET_ROOM_MANUAL_TARGETS", "room_id": room["id"], "temp_c": 10, "humidity": 48, "airflow_percent": 60}))
    assert bad["ok"] is False
    bad2 = run(s.handle_command({"action": "SET_ROOM_MANUAL_TARGETS", "room_id": room["id"], "temp_c": 20, "humidity": 48, "airflow_percent": 5}))
    assert bad2["ok"] is False


def test_v82_openstudio_result_metadata_and_end_uses_are_exposed():
    s = fresh()
    p = s.energy_baseline.public_dict()
    assert p["calibration_tier"] == "FULL_ANNUAL_TABULAR"
    assert p["reference_resolution"] == "MONTHLY_MEAN"
    assert len(p["monthly"]) == 12
    assert len(p["end_uses_electricity"]) == 4
    assert math.isclose(p["floor_area_m2"], 3697.0, rel_tol=1e-6)
    assert math.isclose(p["conditioned_floor_area_m2"], 3554.0, rel_tol=1e-6)
    assert math.isclose(p["annual_peak_electric_kw"], 115.6125, rel_tol=1e-6)
    assert p["metadata"]["total_unmet_hours"] == 0.0
    assert "Ho.Chi.Minh" in p["metadata"]["weather_file"]


def test_v82_monthly_mean_reference_uses_current_calendar_month():
    s = fresh()
    ref, method = s.energy_baseline.facility_reference_kw(datetime(2026, 9, 2, 12, 0).astimezone())
    assert method == "MONTHLY_MEAN_FACILITY_REFERENCE"
    # September report consumption 50,077.18 kWh / 720 h = 69.5516 kW.
    assert math.isclose(ref, 69.5516, rel_tol=1e-4)


def test_v9_all_floorplan_spaces_link_back_to_energyplus_space_calibration():
    s = fresh()
    rooms = s.to_dict()["rooms"]
    assert len(rooms) == 62
    assert sum(bool(r["openstudio_space_calibration"].get("matched")) for r in rooms) == 62
    operating_rooms = [r for r in rooms if r["category"] == "OPERATING_ROOM"]
    assert len(operating_rooms) == 8
    assert all(r["lighting_design_w_m2"] == 18.0 for r in operating_rooms)
    assert all(r["equipment_design_w_m2"] == 60.0 for r in operating_rooms)
    assert all(r["max_airflow_source"] == "ENERGYPLUS_ZONE_FLOW_AREA_ALLOCATION" for r in operating_rooms)
    assert all(r["fan_power_source"] == "ENERGYPLUS_SYSTEM_FAN_PROPORTIONAL" for r in operating_rooms)
