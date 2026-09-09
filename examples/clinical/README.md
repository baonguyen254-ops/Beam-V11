# Standard Clinical Model Import Formats

The English demo already has three working artificial models in `../demo/models/`; no import is required to present the dashboard.

This directory is for the separate standard-mode model workflow. `model.template.json` intentionally contains null coefficients and cannot be registered until completed with an appropriate specification. `holdout-format.json` shows the row shape only; one row is insufficient for evaluation.

Use **Clinical models** to register a model version and evaluate a holdout dataset. Supply coefficients, centers, scales, units and bounds exactly as defined by the model specification. The engine performs no automatic unit conversion or missing-value imputation. Standard use requires independent outcomes matching the endpoint/population, declared numerical gates and an attributed review by a different eligible reviewer. Bundled synthetic demo rows do not establish clinical validity.
