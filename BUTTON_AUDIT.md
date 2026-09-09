# Frontend and Backend Action Coverage

The centralized command path supplies stable command IDs, pending state, acknowledgement/rejection and HTTP reconciliation after WebSocket uncertainty. Source and transport checks are recorded in `VALIDATION.md`.

The 17 retained legacy families are `TOGGLE_AUTOPILOT`, `TOGGLE_ENERGY_AI`, `APPLY_CONTROL_PROFILE`, `SET_PRESSURE_POLICY`, `SET_LIGHTING`, `SET_TEMPERATURE_SETPOINT`, `SET_HUMIDITY_SETPOINT`, `SET_FAN_SPEED`, `SET_ROOM_MODE`, `SET_ROOM_MANUAL_TARGETS`, `RESET_ROOM_MANUAL_TARGETS`, `ADD_EXTERNAL_CASE`, `MANUAL_SCHEDULE_CASE`, `STRESS_TEST_PRESSURE`, `RESTORE_PRESSURE`, `EMERGENCY_MODE` and `CLEAR_EMERGENCY_MODE`.

The hospital and room workspaces add registry edits, case lifecycle, resource-aware planning, clinical inputs/predictions, model management, inspections, room finance and automation release. The API/action mapping is maintained in `INTERACTION_CONTRACT.md`. Backend authorization, validation and resource checks apply independently of button visibility.

The v11.1 demo uses those same HTTP/WebSocket commands. It provides populated backend records and local presenter authentication, rather than a separate collection of frontend mock controls. See `tools/smoke_demo.py` for the executable edit/predict/schedule/control/energy/restart workflow.
