# v9 Frontend ↔ Backend Action Audit

All server-bound controls use the centralized `sendCommand()` WebSocket wrapper with command ID, acknowledgement/rejection, pending state and timeout handling.

Validated action families (17):

- TOGGLE_AUTOPILOT
- TOGGLE_ENERGY_AI
- APPLY_CONTROL_PROFILE
- SET_PRESSURE_POLICY
- SET_LIGHTING
- SET_TEMPERATURE_SETPOINT
- SET_HUMIDITY_SETPOINT
- SET_FAN_SPEED
- SET_ROOM_MODE
- SET_ROOM_MANUAL_TARGETS
- RESET_ROOM_MANUAL_TARGETS
- ADD_EXTERNAL_CASE
- MANUAL_SCHEDULE_CASE
- STRESS_TEST_PRESSURE
- RESTORE_PRESSURE
- EMERGENCY_MODE
- CLEAR_EMERGENCY_MODE

The real WebSocket transport smoke validates 26 command scenarios because several action families are exercised in multiple states/modes.
