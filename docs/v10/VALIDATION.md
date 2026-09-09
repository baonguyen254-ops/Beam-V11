# BEAM v10 validation record

Validation date: **2026-09-08**. Results below were executed against the recovered v10 source in this delivery session, not carried over from an earlier workspace.

| Check | Executed result |
|---|---|
| Backend regression, original importer tests and v10 tests | **71 passed**, no failures |
| Static frontend/backend contract | **17 legacy action families** present, all source feature assertions passed |
| Real authenticated WebSocket through a temporary uvicorn server | **27 commands validated**, including accepted/rejected commands, state changes, patient intake and manual scheduling |
| Production frontend | TypeScript compilation and Vite production build passed |
| Shipped launcher and static bundle | `RUN_BEAM.py` started, served v10 index and referenced CSS/JS, protected hospital API before login |
| HTTP command reliability | Same ID replay confirmed, including after server restart |
| Durable energy and CSV | Observed sample written, CSV endpoint read, energy retained after restart |
| Online SQLite backup | Backup script succeeded; integrity and durable command records verified |
| Local installation check | Python dependencies, static build, OSM, floorplan, capabilities, baseline and tabular source present |

Backend regression covers strict input types, command identity/authority, CSRF origin and authentication, duplicate command payloads, registry uniqueness and persistence, staff unavailability, patient conflicts, device end of life/service, active-case mutation guards, real case lifecycle, reservations/turnover, synthetic pressure guards, missing/stale/out-of-order sensor data, signed energy integration and tariff changes, time bucket splitting, timezone/leap-day alignment, invalid/full-year SQL import, mature clinical outcomes and terminal archives.

The release smoke test runs with a temporary data directory and synthetic test identities, starts the actual `RUN_BEAM.py` process, authenticates over HTTP, checks the static assets, writes/replays a command, observes energy, exports CSV, makes an online backup, restarts the server and verifies persisted state. It does not inspect pixels or browser interactions.

## Reproduce

From the project root, using a Python 3.12+ environment with `requirements-dev.txt` installed:

```bash
python -m pytest -q beam-backend
python beam-backend/test_frontend_contract.py
python beam-backend/test_transport_contract.py
python tools/build_frontend.py
python tools/check_setup.py
python tools/smoke_release.py
```

`RUN_TESTS.bat` provides the regression/transport/build workflow on Windows. Tests must use their own temporary databases, never an operational patient database.

## Environment and warnings

Executed on Linux with Python 3.12.13, FastAPI 0.141.1, uvicorn 0.52.4, websockets 16.1.1, Pydantic 2.13.5, Starlette 1.6.0, BeautifulSoup 4.15.0, pytest 9.1.1, httpx 0.28.1 and tzdata 2026.3. Frontend Vite 7.3.6 used the included npm lockfile.

Two dependency deprecation warnings arose from Starlette TestClient's httpx/AnyIO compatibility layer. They did not fail the tests. Vite reported the existing large application chunk, about 745 kB minified and 221 kB gzip; this remains a startup-performance improvement opportunity. Runtime correctness was not inferred from bundle size or the absence of warnings.

## Not executed / not established

Browser visual, DOM and pointer/keyboard end-to-end testing was not performed. The build passing does not establish flawless layout on every screen or validate every browser interaction. Windows `.bat` execution, Docker image build, Render deployment, real PLC/BACnet/Modbus/Schneider commissioning, load/soak testing, penetration testing, clinical model validation and hospital energy M&V were not executed. Their configuration or implementation boundaries are documented in `V10_GUIDE_VI.md`; this record does not certify medical or production suitability.

No real patient database, password, runtime SQLite file or bootstrap key is included in the distribution archive. Test accounts and runtime state were created only in disposable test folders.
