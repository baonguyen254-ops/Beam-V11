# Bundled English Demonstration Models

`models/` contains three artificial logistic specifications and a 400-row synthetic evaluation dataset for each specification. `beam-backend/demo_pack.py` installs them automatically in an isolated demo workspace, creates fictional patient/team/device/case records and seeds traits and energy history.

Models use status `DEMO_READY`, `simulation_only: true`, synthetic benchmark provenance and no clinician approval. Evaluation rows are generated from the same teaching formula; their scores are not independent clinical validation. These fixtures are not eligible standard-mode medical models.

Start with `START_BEAM.bat` and select **Open demo dashboard**. See `V11_GUIDE_EN.md` at the project root for the complete walkthrough. A fresh-demo launcher creates a separate session without deleting old work.
