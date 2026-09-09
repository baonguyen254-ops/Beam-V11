# BEAM v11.1 interaction contract

Frontend/backend version: `11.1.0`. Telemetry contract: `beam-final-v11`. Transport: same-origin HTTP and authenticated WebSocket `/ws`. `STATE_INIT` includes floorplan; `STATE_UPDATE` includes full live room/HIS/control/energy state and monotonic revision within a connection. A reconnect accepts the restored backend revision.

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


## v11 room and integration extensions

| API / action | Contract |
|---|---|
| GET `/api/rooms/overview` | `beam-rooms-v11`, all conditioned room summaries |
| GET `/api/rooms/{id}` | `beam-room-v11`, linked case/patient/team/devices/readiness/timeline/targets/ROI |
| `RELEASE_ROOM_AUTOMATION` | Atomically clears room manual mode and targets; physical safety remains higher priority |
| `PREVIEW_SCHEDULE`, `APPLY_SCHEDULE_PLAN` | 1–16 unscheduled cases, immutable proposal semantics, business fingerprint, 90s expiry, atomic apply |
| `SET_ROOM_FINANCE`, `RECORD_BMS_COST` | Facility CAPEX/OPEX allocation total <=100%, durable incremental costs |
| `SET_DEVICE_ENGINEERING`, `RECORD_DEVICE_INSPECTION` | OEM limits/provenance and measured readings without service-counter reset |
| GET `/api/clinical/models` | ADMIN/CLINICIAN only; registry and predictor units |
| `REGISTER_CLINICAL_MODEL`, `EVALUATE_CLINICAL_MODEL` | ADMIN, declarative JSON only, immutable model ID, independent holdout |
| `REVIEW_CLINICAL_MODEL`, `REVOKE_CLINICAL_MODEL` | ADMIN/CLINICIAN; reviewer differs from registrar/evaluator; expiry and provenance |
| `SET_CASE_CLINICAL_INPUTS`, `RUN_CASE_PREDICTION` | Preoperative data <=72h; recorded prediction retains exact model/input/review provenance |
| GET `/api/energy` | source=SIMULATION/CONNECTED/LEGACY_MIXED/ALL; default current mode; finance follows scope and selected bounds |
| GET `/api/integrations/targets` | `beam-gateway-v11`, proposal_id, revision, issued_at, expires_at, room targets |
| POST `/api/integrations/actuation` | Valid unexpired proposal, unchanged control policy, exact room/revision; applied=true requires fresh telemetry and read-back |

HTTP command results are JSON-normalized, including nested datetime values in schedule proposals. HTTP fallback preserves the same command ID as WebSocket. Payloads above 60 KB use HTTP immediately; body limit is 128 KiB. Gateway receipts are durable; pending proposals intentionally do not survive a restart.

Clinical fields are filtered for OPERATOR/VIEWER across HTTP and WebSocket. Archive/model reads require clinical roles. The new room view uses WebSocket readings for live metrics and serial five-second API refreshes for relational details; it does not synthesize a second independent simulation in the browser.

## v11.1 isolated English demo

`RUN_BEAM.py --demo` selects its own persistent workspace and loopback binding. `--new-demo` creates a separate workspace; `--standard` retains the earlier setup and `BEAM_DATA_DIR` behavior. Demo mode rejects connected/non-demo workspaces before initialization can replace their records.

`GET /api/session` advertises `demo_available`. `POST /api/demo/login` issues the normal authenticated presenter session only in a local simulation demo with a trusted origin. It is unavailable in standard mode. The presenter uses the same protected read endpoints and command handlers as the application.

`system.demo` and room/hospital demo metadata describe the prepared pack. `control.virtual_bms` identifies simulated actuation. Models marked `bundled_demo` can use `DEMO_READY` only in a simulation demo; no review is synthesized. Evaluations have `dataset_kind=SYNTHETIC_BENCHMARK`. New synthetic case intake receives linked patient records and preoperative inputs even with scheduling paused.

Seeded histories retain SIMULATION provenance and zero measured seconds; CONNECTED filters exclude them. Bootstrap is idempotent across restart. A demo refuses CONNECTED mode changes and external HIS/BMS integration writes. The frontend renders backend data rather than maintaining an unrelated simulation.
