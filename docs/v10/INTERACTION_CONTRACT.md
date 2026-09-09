# BEAM v10 interaction contract

Frontend/backend version: `10.0.0`. Telemetry contract: `beam-final-v10`. Transport: same-origin HTTP and authenticated WebSocket `/ws`. `STATE_INIT` includes floorplan; `STATE_UPDATE` includes full live room/HIS/control/energy state and monotonic revision within a connection. A reconnect accepts the restored backend revision.

The client enters LIVE only after a valid matching state. Six seconds without telemetry changes the UI to STALE and blocks commands. Mismatched versions show MISMATCH and require refresh. A live socket alone is not proof of fresh BMS sensors: `system.mode` and per-room `telemetry_source` distinguish model, fresh BMS and stale BMS values.

Commands require `action` and a stable `command_id`. Server-supplied actor and role determine authorization. WebSocket answers with `COMMAND_ACK`/`COMMAND_REJECTED`; HTTP `/api/commands` answers with `ok`, `message`, `command_id`, `action` and optional result identifiers. A retry with the same actor/ID/body returns the stored result and `replayed: true`. Reusing an ID with another body is rejected.

At eight seconds without ACK, or after socket loss, the frontend reconciles via HTTP using the original ID and payload. If both transports fail, execution is uncertain and the user must check the registry/audit before creating a new command. Client-supplied identity never bypasses permissions. Invalid numeric, boolean, date, list and object inputs fail before accepted state is committed.

| Surface | Read source | Mutation source |
|---|---|---|
| Legacy operations / Command Center | WS state and floorplan | 17 existing command families |
| Patients | `/api/hospital` | `UPSERT_PATIENT` |
| Staff and availability | `/api/hospital` | `UPSERT_STAFF` |
| Device register and service | `/api/hospital` | `UPSERT_DEVICE`, `SERVICE_DEVICE` |
| Case workflow | WS HIS, `/api/cases/archive` | Intake, assignment, update, schedule, cancel, start, complete |
| Clinical record | `/api/intelligence`, case records | `RECORD_CLINICAL_ESTIMATE`, `RECORD_OUTCOME` |
| Traits / readiness | `/api/intelligence` | Learned from eligible observations and actual case timestamps |
| Energy / ROI | `/api/energy` and CSV | Observed ticks plus `SET_HOSPITAL_CONFIG` for future tariff/config |
| Accounts and audit | `/api/users`, `/api/audit` | Admin account creation; server audit only |
| BMS integration | `/api/integrations/targets` | Telemetry, actuator receipts, runtime counters |
| HIS integration | HIS command endpoint | Clinical allowlist with separate bearer token |

All clinical case start checks and resource reservations occur server-side, independent of frontend button visibility. A room target is a requested operating point, not proof of applied hardware state. Gateway receipts are separately labelled. A readiness score is a checklist result, not a predicted surgical success rate.

All REST registry views poll after completion of the prior request, preventing overlapping polls. Failed polls retain an explicit error banner and block registry mutation until the hospital state can be refreshed. Lists have search and pagination; the live case cache is bounded and terminal cases are persisted in the archive.
