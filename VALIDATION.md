# BEAM v11.1 English Demo — Validation Record

Final validation date: **2026-09-09**. These checks were executed against the English Demo source and its production frontend. Earlier evidence remains in `docs/` for provenance.

| Check | Executed result |
|---|---|
| Backend regression, importers, engineering, clinical, finance, gateway and demo | **106 passed**, no failures; 33.92 seconds |
| Frontend/backend source contract | **17 legacy action families** covered; Digital Twin, fullscreen Command Center, modal portal, heatmaps, trends, alarms and controls assertions passed |
| Authenticated real WebSocket | **27 commands validated**, including accepted/rejected commands and state changes |
| Standard v11 HTTP/WS workflow through the launcher | **21 HTTP commands**; room/resources, scheduling, engineering, energy/ROI, gateway receipt, role redaction and restart passed |
| English demo through the actual launcher and HTTP | **8 commands**; presenter login, populated data, editable computed probability, saved prediction, schedule preview/apply, virtual BMS, six energy resolutions and persistent restart passed |
| Demo needs only the floorplan as real input | Passed with a copy of `floorplan.json`, without neighboring EnergyPlus baseline or capability files |
| Demo model provenance | Three active artificial models, synthetic benchmark labels and no clinical approval; reevaluation remains demo-only; standard operation cannot use their demo eligibility |
| Energy accounting and restart | Overlapping seeded minute/hour totals agree; six resolutions contain simulation history; measured coverage is zero; CONNECTED excludes demo samples; restart does not duplicate seed history |
| Demo isolation | Untrusted-origin login rejected; protected API requires a session; external integration writes and CONNECTED switch rejected; a connected workspace is preserved when demo initialization refuses it |
| Production frontend | TypeScript compilation and Vite build passed; English HTML and current CSS/JS served; frontend/backend both `11.1.0` |
| English source review | No accented Vietnamese strings remain in frontend TypeScript/TSX; active operating documents translated; original source labels and historical documents intentionally preserved |
| Release persistence | Launcher/static assets, login, HTTP replay, energy/CSV, online SQLite backup integrity and restart passed |
| Original assets and distribution | ZIP CRC/safe paths/source equality passed; all seven original model/data files are byte-identical; all six demo model/benchmark files included |
| Fresh extraction | The extracted ZIP launched, calculated a changed prediction, scheduled cases, controlled virtual BMS and restored its demo without node_modules or the working source tree |

Raw output is in `validation/backend.txt`, `validation/frontend.txt`, `validation/transport.txt`, `validation/demo.txt` and `validation/archive.txt`. The extracted candidate contains the validated source/static assets; the final archive additionally includes the final evidence and documentation. Its complete file equality and CRC are checked again after packaging those records.

## Behavioral scope

The suite retains v9/v10/v11 tests for clinical resource checks, readiness, thermal/RH traits, source and stale-sample separation, atomic scheduling and resource drift, inspection history and conditional RUL, source-specific finance, declarative models and independent review gates, immutable predictions, clinical privacy, expiring gateway proposals and verified receipts. The added demo tests verify immediate population, source-aware calculations, editable predictions, artificial-model reevaluation, persistence, database refusal and floorplan-only operation.

`tools/smoke_v11.py` uses an isolated CONNECTED test workspace with fictional identities and generated telemetry. `tools/smoke_demo.py` starts the shipped launcher with a separate demo directory, authenticates the local presenter, changes clinical inputs and verifies the computed result, saves/replays a prediction, previews/applies a schedule, changes/releases room targets, checks energy/CSV and restarts. `tools/smoke_release.py` independently verifies standard startup, static assets, login, command replay, backup and restart.

Gateway tests address a fake Modbus TCP PLC on localhost, including frame/register decoding, scaling, byte/word order, write limits, expiry, write-enable interlock and read-back. They do not address physical hospital equipment.

## Reproduce

From the extracted project root with Python 3.12+ and `beam-backend/requirements-dev.txt` installed:

```bash
python -m pytest -q beam-backend
python beam-backend/test_frontend_contract.py
python beam-backend/test_transport_contract.py
python tools/build_frontend.py
python tools/check_setup.py
python tools/smoke_v11.py
python tools/smoke_release.py
python tools/smoke_demo.py
```

`RUN_TESTS.bat` runs regression, contracts, build and all three smoke workflows on Windows. It was not executed on native Windows in this session. All integration checks use disposable workspaces. Rebuilding requires Node.js/npm; running the bundled demo does not.

## Environment and limits

Executed on Linux with Python 3.12.13, FastAPI 0.141.1, uvicorn 0.52.4, websockets 16.1.1, Pydantic 2.13.5, Starlette 1.6.0, BeautifulSoup 4.15.0, pytest 9.1.1, httpx 0.28.1 and tzdata 2026.3. The frontend used the included lockfile and Vite 7.3.6. Backend top-level dependencies are pinned to the tested versions.

Two non-failing dependency deprecation warnings came from the Starlette TestClient httpx/AnyIO compatibility layer. npm reported its environment `http-proxy` setting warning. Vite reported the existing large application chunk: **780.39 kB minified / 229.79 kB gzip**; CSS is **64.84 kB / 12.29 kB gzip**. Compilation and source assertions do not establish every browser layout or interaction.

Browser visual/DOM/pointer/keyboard testing, native Windows execution, Docker build, Render deployment, load/soak and penetration testing, physical gateway commissioning, clinical validation and hospital energy M&V were not performed. Artificial model probabilities and synthetic benchmark scores demonstrate software behavior; they do not establish medical performance.

The distribution excludes runtime databases, credentials, bootstrap keys and installed dependency folders. No real patient database is included. The normal English demo operates with generated records and the supplied floorplan. See `V11_GUIDE_EN.md` for launch and data-source details.
