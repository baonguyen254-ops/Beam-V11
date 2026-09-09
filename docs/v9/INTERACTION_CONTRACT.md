# B.E.A.M. v9 Interaction Contract

Frontend expected version: `9.0.0`

Backend telemetry contract: `beam-final-v9`

The frontend checks **both** version and telemetry contract. A mixed/stale frontend-backend pair surfaces a visible `VERSION MISMATCH` banner.

Server-bound flow:

`UI → sendCommand() → WebSocket → backend validation/arbitration → COMMAND_ACK/COMMAND_REJECTED → STATE_UPDATE → UI`

No server-bound control is considered successfully applied merely because local React state changed.

Room control remains below physical safety and emergency arbitration. Command Center reuses the exact same control components and backend action families as the normal dashboard.
