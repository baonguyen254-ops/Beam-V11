# BEAM v11.1 English Demo checkpoints

## Baseline

Checkpoint 3 is the completed v11 release. Original floorplan and OpenStudio files remain unchanged.

## Checkpoint 4: English interface

Translated 521 frontend text occurrences across the legacy control surface, login, room workspace, patient/team/equipment forms, energy/ROI and clinical model registry. Backend alerts and privacy messages now use English. Number and date formatting uses en-US; VND and the configured reporting timezone remain explicit. Source floorplan labels remain intact and are displayed through the existing English-name mapping.

## Checkpoint 5: working synthetic demo

- Three bundled artificial logistic models and three synthetic evaluation datasets; eligible demo cases receive computed probabilities immediately.
- Eight original operating rooms, 16 opening cases/patients, 24 staff, 32 devices, 1,024 synthetic historical outcomes and 32 duration traits.
- Synthetic equipment inspections and degradation trends, warmed temperature/humidity models, virtual BMS response and initial chart history.
- 370 days of hourly energy, 24 hours of minute history, 15 minutes of second history, room allocations, CAPEX/OPEX and cost records. Sources remain SIMULATION.
- Local presenter entry, isolated demo directories, persistent restart and a fresh-demo launcher. Connected operation and external integration writes are disabled inside the demo workspace.
- Core regression reached 105 passing tests and the English production build passed. The checkpoint was saved before the final release gates and documentation pass.

## Checkpoint 6: final English Demo distribution

Completed on 2026-09-09.

- English README, full operating guide, release notes, modeling assumptions, action/feature references and updated interface contract. Original release documents are preserved in `docs/`.
- Added a floorplan-only startup regression and a bundled-model reevaluation assertion. Final backend result: 106 passed; all 17 legacy UI action families remain covered.
- Passed the 27-command real WebSocket contract, 21-command standard HTTP/WS workflow, standard release/backup/restart smoke and eight-command English demo HTTP workflow.
- TypeScript/Vite production build passed and the bundled backend static files match it. Both frontend and backend report 11.1.0.
- Fresh ZIP extraction passed the English demo launcher, authentication, data/model, editable prediction, scheduling, virtual control, energy and restart workflow without node_modules or the working source tree.
- All seven original OpenStudio/floorplan/capability/baseline files remain byte-identical. The distribution contains the three demo model specifications and three synthetic benchmark datasets; it excludes runtime databases and credentials.

The requested English conversion and immediately usable demo are complete. `VALIDATION.md` records executed checks and verification limits; `V11_GUIDE_EN.md` is the current operating guide.
