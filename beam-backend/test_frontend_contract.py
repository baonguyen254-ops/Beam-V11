from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "beam-frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
BACKEND = (Path(__file__).resolve().parent / "beam_state.py").read_text(encoding="utf-8")

EXPECTED = {
    "TOGGLE_AUTOPILOT",
    "TOGGLE_ENERGY_AI",
    "APPLY_CONTROL_PROFILE",
    "SET_PRESSURE_POLICY",
    "SET_LIGHTING",
    "SET_TEMPERATURE_SETPOINT",
    "SET_HUMIDITY_SETPOINT",
    "SET_FAN_SPEED",
    "SET_ROOM_MODE",
    "SET_ROOM_MANUAL_TARGETS",
    "RESET_ROOM_MANUAL_TARGETS",
    "ADD_EXTERNAL_CASE",
    "MANUAL_SCHEDULE_CASE",
    "STRESS_TEST_PRESSURE",
    "RESTORE_PRESSURE",
    "EMERGENCY_MODE",
    "CLEAR_EMERGENCY_MODE",
}

backend_actions = set(re.findall(r'action == "([A-Z_]+)"', BACKEND))
missing_backend = EXPECTED - backend_actions
assert not missing_backend, f"Frontend contract actions missing backend handlers: {sorted(missing_backend)}"

missing_frontend_strings = {action for action in EXPECTED if action not in APP}
assert not missing_frontend_strings, f"Expected command strings not represented in App.tsx: {sorted(missing_frontend_strings)}"

# All server-bound actions should funnel through the one reliability wrapper.
assert "function makeCommandId" in APP
assert "No acknowledgement for ${action} within 8 seconds" in APP
assert "pendingCommandsRef" in APP
assert APP.count("ws.send(") == 1, "WebSocket sends should be centralized in sendCommand"

print(f"PASS static frontend/backend contract: {len(EXPECTED)} UI action families covered")

# v9 final visualization / command-center + calibration contract: these features are source-driven
# and must remain wired to server telemetry rather than synthetic arrays.
for token in [
    'type FloorLayer = "STATUS" | "TEMPERATURE" | "HUMIDITY" | "ENERGY"',
    'power_density_w_m2',
    'session_utilization_percent',
    'alarm_severity',
    'active_case_id',
    'MiniSparkline',
    'CommandCenterView',
    'beamIconPerson',
    'createPortal',
    'APPLY_CONTROL_PROFILE',
    'SET_PRESSURE_POLICY',
    'Hard architectural boundary pass',
    'openCommandCenter',
    'interiorLabelPoint',
    'type BeamTheme = "light" | "dark"',
    'Room Manual Setup',
    'presentation="OVERVIEW"',
    'SET_ROOM_MANUAL_TARGETS',
    'data-beam-room-id',
    'const floorplanTheme =',
    'beam-modal-backdrop',
    'OPENSTUDIO ${tier}',
    'MONTHLY-MEAN LIVE REF',
    'OpenStudio annual result · monthly profile & end uses',
    'has_monthly_profile',
    'reference_resolution',
    'HVAC + Sterility',
    'FULL_ANNUAL_TABULAR',
    'EnergyPlus calibrated room design',
    'calibrated_min_airflow_m3h',
    'beam-final-v11',
]:
    assert token in APP, f"Missing v8 UI feature contract token: {token}"
assert 'Math.random()' not in APP.split('function FloorplanTwin', 1)[1], "Floorplan must not synthesize fake telemetry"
print("PASS v9 visualization/calibration contract: hard boundaries, fullscreen command center, modal portal, heatmaps, trends, alarms and controls")
