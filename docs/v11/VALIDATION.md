# BEAM v11 validation record

Validation date: **2026-09-08**. These checks were executed against the v11 source and its production frontend in this delivery session. Earlier v9/v10 records remain in `docs/` for provenance.

| Check | Executed result |
|---|---|
| Backend regression, importers, v11 engineering/clinical/finance and gateway tests | **100 passed**, no failures |
| Static frontend/backend contract | **17 legacy action families** covered; Digital Twin, fullscreen Command Center, modal portal, heatmaps, trends, alarms and control assertions passed |
| Authenticated real WebSocket through a temporary server | **27 commands validated**, including accepted/rejected commands and state changes |
| v11 real HTTP/WS workflow through the shipped launcher | **21 HTTP commands**; room/resources, schedule preview/apply, engineering, six-resolution source-specific energy/ROI, gateway receipt, role redaction and restart passed |
| Production frontend | TypeScript compilation and Vite production build passed; current output copied into `beam-backend/static` |
| Shipped launcher and static bundle | `RUN_BEAM.py` started and served the v11 index and referenced CSS/JS; hospital API required login |
| HTTP command reliability | Same-ID replay confirmed, including after restart; datetime-containing schedule results serialize correctly |
| Durable energy, CSV and backup | Observed samples and CSV checked; online SQLite backup passed integrity check; commands and energy survived restart |
| Local installation check | Python dependencies, static build, OSM, floorplan, capabilities and baseline sources present |
| Extracted release | ZIP CRC and source/static equality passed; all 7 original v10 model/data files preserved byte-for-byte; launcher/login/CSV/backup/restart smoke passed from a fresh extraction without node_modules |

Raw output is included in `validation/backend.txt`, `validation/frontend.txt`, `validation/transport.txt` and `validation/archive.txt`. The archive record describes the tested source/static candidate; the final package also includes that record and the final documentation. The contract checks are source assertions and transport exercises; they do not replace browser interaction testing.

The backend suite includes the retained v9/v10 tests and v11 tests for thermal/RH traits, source and stale-sample separation, atomic scheduling and resource drift, engineering inspection history and conditional RUL, source-specific energy migration and room finance, declarative clinical models and evaluation/review gates, immutable prediction records, clinical privacy, expiring gateway proposals, verified receipts and restart persistence. It also checks that the legacy Command Center does not mix simulated savings into CONNECTED totals and that demo cases do not reserve real resources after a mode change.

Gateway tests use a fake Modbus TCP PLC on localhost, including frame/register decoding, scale/byte/word order, write limits, proposal expiry, local write-enable interlock and read-back. No real PLC or hospital device was addressed.

`tools/smoke_v11.py` uses an isolated CONNECTED database and fictitious test identities. It starts the actual launcher, creates patient/staff/device/case data, verifies room and scheduling workflows, ingests test telemetry, validates a gateway receipt, checks all six energy resolutions and source separation, verifies clinical redaction at HTTP/WS boundaries, rejects a viewer mutation and checks state after restart. `tools/smoke_release.py` independently checks startup, static assets, login, command replay, CSV, online backup and restart.

## Reproduce

From the project root with Python 3.12+ and `beam-backend/requirements-dev.txt` installed:

```bash
python -m pytest -q beam-backend
python beam-backend/test_frontend_contract.py
python beam-backend/test_transport_contract.py
python tools/build_frontend.py
python tools/check_setup.py
python tools/smoke_v11.py
python tools/smoke_release.py
```

`RUN_TESTS.bat` runs this workflow on Windows. The batch file itself has not been executed on native Windows during this session. All tests must use disposable databases, never an operational patient database. Rebuilding requires Node.js/npm; launching the bundled release does not.

## Environment and warnings

Executed on Linux with Python 3.12.13, FastAPI 0.141.1, uvicorn 0.52.4, websockets 16.1.1, Pydantic 2.13.5, Starlette 1.6.0, BeautifulSoup 4.15.0, pytest 9.1.1, httpx 0.28.1 and tzdata 2026.3. The frontend used the included npm lockfile and Vite 7.3.6. Backend top-level dependencies are pinned to these tested versions.

Two non-failing dependency deprecation warnings came from Starlette TestClient's httpx/AnyIO compatibility layer. npm reported an environment `http-proxy` setting warning. Vite reported a large application chunk: **780.92 kB minified / 230.79 kB gzip**; CSS is 64.84 kB / 12.29 kB gzip. Splitting the application bundle remains a startup-performance opportunity. Passing compilation does not establish every browser interaction or layout.

## Not executed / not established

Browser visual, DOM, pointer and keyboard testing; native Windows execution; Docker image build; Render deployment; load/soak and penetration testing; real PLC/BACnet/Modbus/Schneider commissioning; clinical model validation; and hospital energy M&V were not performed. The clinical tests establish software behavior using artificial coefficients, not medical performance. No medical weights are supplied. Deployment-specific limits and setup requirements are documented in `V11_GUIDE_VI.md`.

The distribution excludes runtime databases, credentials, bootstrap keys and installed dependency folders. No real patient database is included. Test identities and runtime state were confined to temporary folders.
