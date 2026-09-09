# B.E.A.M. v11.1 English Demo

**Hospital BMS · Surgical Digital Twin · Room Intelligence**

Open a populated hospital dashboard immediately: English interface, three artificial prediction models, live virtual BMS, cases, patients, staff, equipment, learned traits and energy/ROI history. The supplied floorplan is preserved. No patient dataset, model upload, external AI service or physical BMS connection is needed to run the demo.

## Start on Windows

1. Install Python 3.12 or later and extract the entire ZIP.
2. Run `INSTALL_BEAM.bat` once to install dependencies.
3. Run `START_BEAM.bat`, then select **Open demo dashboard** at `http://127.0.0.1:8000`.

The production interface is bundled; Node.js is only needed to rebuild it. Dependency installation needs internet access; normal demo operation runs locally.

| Launcher | Behavior |
|---|---|
| `START_BEAM.bat` | Open or resume the prepared English demo |
| `START_NEW_DEMO.bat` | Create a fresh populated demo in a separate directory |
| `START_STANDARD.bat` | Open the existing standard setup and data workspace |

Close the running server before using another launcher on port 8000. Demo presenter entry is local to your computer. Standard mode retains account setup, permissions and integration support.

## Linux/macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r beam-backend/requirements.txt
.venv/bin/python RUN_BEAM.py --demo --open
```

## Included at first launch

Eight original operating rooms, 16 opening cases/patients, 24 staff, 32 devices with inspection trends, 1,024 synthetic historical cases, 32 duration traits and 370 days of synthetic energy history. Second, minute, hour, day, month and year reports work immediately. New simulated cases and virtual room conditions continue to evolve.

Demo probabilities are computed using artificial coefficients and are labeled as demonstrations. They are not clinically validated surgical success estimates. Original Digital Twin, fullscreen Command Center, themes, heatmaps, HVAC/pressure/lighting controls, HIS Scheduler and Energy AI remain available.

## Documentation

- [V11_GUIDE_EN.md](V11_GUIDE_EN.md): walkthrough, demo models, energy math, restart and standard mode.
- [V11_RELEASE_NOTES.md](V11_RELEASE_NOTES.md): v11.1 changes and retained features.
- [VALIDATION.md](VALIDATION.md): executed checks and their limits.
- [INTERACTION_CONTRACT.md](INTERACTION_CONTRACT.md): frontend, HTTP, WebSocket and integration contracts.
- [V11_1_PROGRESS.md](V11_1_PROGRESS.md): saved checkpoints.
- [DEPLOY_HTTPS.md](DEPLOY_HTTPS.md): standard internal deployment.

Historical v9/v10/v11 documentation is preserved in `docs/`; it describes those releases and can contain their original language. Current interface and operating instructions are English.
