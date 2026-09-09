"""Versioned declarative logistic models, holdout evaluation and attributed review.

No executable pickle, automatic training, vendor model or clinical weights are shipped.
Numerical gates are software checks, never evidence of clinical approval by themselves.
"""

import hashlib
import math
import secrets
from datetime import datetime, date, timezone, timedelta
from statistics import mean
from hospital import aware, number, text
from his_engine import PROCEDURES
from storage import encode

FEATURES = {
    "age_years": (0, 125, "years"),
    "asa_class": (1, 6, "class"),
    "emergency": (0, 1, "0/1"),
    "bmi": (8, 100, "kg/m2"),
    "hemoglobin_g_dl": (1, 30, "g/dL"),
    "albumin_g_dl": (0.1, 10, "g/dL"),
    "creatinine_mg_dl": (0.1, 30, "mg/dL"),
}
ENDPOINT = "NO_MAJOR_COMPLICATION_30D"


def predict(model, values):
    terms = []
    for name, f in model["features"].items():
        if values.get(name) is None:
            raise ValueError("Missing predictor: " + name)
        value = number(values[name], name, f["min"], f["max"])
        if name in {"asa_class", "emergency"} and value != int(value):
            raise ValueError(name + " must be an integer")
        contribution = f["coefficient"] * (value - f["center"]) / f["scale"]
        terms.append(
            {
                "feature": name,
                "value": value,
                "unit": FEATURES[name][2],
                "log_odds_contribution": contribution,
            }
        )
    z = model["intercept"] + sum(t["log_odds_contribution"] for t in terms)
    probability = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
    return probability, terms


def evaluate(model, rows):
    if not isinstance(rows, list) or not 20 <= len(rows) <= 500:
        raise ValueError("Provide 20 to 500 independent holdout rows per evaluation")
    ids, values = set(), []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("success")) is not bool:
            raise ValueError("Each holdout outcome must be boolean")
        key = text(row.get("record_id"), "De-identified holdout ID", 100)
        if key in ids:
            raise ValueError("Duplicate holdout record")
        ids.add(key)
        probability, _ = predict(model, row.get("features", {}))
        values.append((probability, int(row["success"])))
    positives = [p for p, y in values if y]
    negatives = [p for p, y in values if not y]
    auc = (
        sum((a > b) + 0.5 * (a == b) for a in positives for b in negatives)
        / (len(positives) * len(negatives))
        if positives and negatives
        else None
    )
    bins = []
    for i in range(10):
        group = [(p, y) for p, y in values if min(9, int(p * 10)) == i]
        if group:
            bins.append(
                {
                    "lower": i / 10,
                    "count": len(group),
                    "predicted": mean(p for p, _ in group),
                    "observed": mean(y for _, y in group),
                }
            )
    brier = mean((p - y) ** 2 for p, y in values)
    ece = sum(b["count"] * abs(b["predicted"] - b["observed"]) for b in bins) / len(
        rows
    )
    gate = model["acceptance"]
    passed = (
        len(rows) >= gate["min_cases"]
        and min(len(positives), len(negatives)) >= gate["min_each_outcome"]
        and auc is not None
        and auc >= gate["min_auc"]
        and brier <= gate["max_brier"]
        and ece <= gate["max_ece"]
    )
    return {
        "cases": len(rows),
        "positive_outcomes": len(positives),
        "negative_outcomes": len(negatives),
        "auc": auc,
        "brier": brier,
        "expected_calibration_error": ece,
        "calibration_bins": bins,
        "numerical_gate_passed": passed,
        "dataset_sha256": hashlib.sha256(encode(rows).encode()).hexdigest(),
        "meaning": "Retrospective discrimination and calibration checks; not prospective clinical validation or regulatory clearance.",
    }


class ClinicalModels:
    def __init__(self, services):
        self.s = services

    @property
    def models(self):
        return self.s.data.setdefault("models", {})

    def command(self, p, now):
        action = p["action"]
        if action == "RUN_CASE_PREDICTION":
            c = self.s.state.his.case_by_id(p.get("case_id"))
            if not c or c["status"] not in {"UNSCHEDULED", "SCHEDULED"}:
                raise ValueError(
                    "A preoperative case is required to record a prediction"
                )
            result = self.assessment(c, now)
            if result.get("predicted_success_percent") is None:
                raise ValueError(result["reason"])
            model = self.models[result["model_id"]]
            record = {
                "id": secrets.token_hex(10),
                "at": now.isoformat(),
                "actor": p.get("actor"),
                "patient_id": c["patient_id"],
                "model_id": model["id"],
                "specification_sha256": model["specification_sha256"],
                "endpoint": ENDPOINT,
                "predicted_success_percent": result["predicted_success_percent"],
                "status": result["prediction_status"],
                "inputs": result["contributions"],
                "inputs_observed_at": result["inputs_observed_at"],
                "review": dict(model.get("review") or {}),
                "evaluation_sha256": model["evaluations"][-1]["dataset_sha256"],
            }
            self.s.data.setdefault("predictions", {}).setdefault(c["id"], []).append(
                record
            )
            return {
                "message": "Preoperative prediction saved with exact model and input provenance",
                "prediction": record,
            }
        if action == "REGISTER_CLINICAL_MODEL":
            record = p.get("model")
            if not isinstance(record, dict):
                raise ValueError("Model object required")
            key = text(record.get("id"), "Model/version ID", 100)
            if key in self.models:
                raise ValueError("Model versions are immutable; register a new ID")
            if len(self.models) >= 100:
                raise ValueError("Model registry limit reached")
            if (
                record.get("endpoint") != ENDPOINT
                or record.get("type") != "LOGISTIC_V1"
            ):
                raise ValueError(
                    "Supported: LOGISTIC_V1, NO_MAJOR_COMPLICATION_30D endpoint"
                )
            if type(record.get("simulation_only")) is not bool:
                raise ValueError("simulation_only must be explicit")
            specialties = record.get("specialties")
            if (
                not isinstance(specialties, list)
                or not specialties
                or any(s not in PROCEDURES for s in specialties)
            ):
                raise ValueError("Supported specialties required")
            procedures = record.get("procedures")
            if (
                not isinstance(procedures, list)
                or not procedures
                or len(procedures) > 50
            ):
                raise ValueError(
                    "List exact procedure labels; wildcard models are not accepted"
                )
            procedures = [text(x, "Procedure", 80) for x in procedures]
            features = record.get("features")
            if (
                not isinstance(features, dict)
                or not features
                or set(features) - set(FEATURES)
            ):
                raise ValueError("Unsupported or empty predictor set")
            validated = {}
            for name, f in features.items():
                if not isinstance(f, dict):
                    raise ValueError("Predictor specification required")
                lo, hi, _ = FEATURES[name]
                lower = number(f.get("min"), name + " min", lo, hi)
                upper = number(f.get("max"), name + " max", lower, hi)
                validated[name] = {
                    "min": lower,
                    "max": upper,
                    "coefficient": number(
                        f.get("coefficient"), "Coefficient", -100, 100
                    ),
                    "center": number(f.get("center", 0), "Center", -1e6, 1e6),
                    "scale": number(f.get("scale", 1), "Scale", 0.001, 1e6),
                }
            acceptance = record.get("acceptance", {})
            criteria = {
                "min_cases": 100,
                "min_each_outcome": 10,
                "min_auc": 0.65,
                "max_brier": 0.25,
                "max_ece": 0.1,
            }
            if not isinstance(acceptance, dict) or set(acceptance) - set(criteria):
                raise ValueError("Unknown acceptance criterion")
            criteria.update(acceptance)
            for name, lo, hi in (
                ("min_cases", 100, 500),
                ("min_each_outcome", 10, 250),
                ("min_auc", 0.5, 1),
                ("max_brier", 0.001, 0.25),
                ("max_ece", 0.001, 0.2),
            ):
                criteria[name] = number(criteria[name], name, lo, hi)
            model = {
                "id": key,
                "type": "LOGISTIC_V1",
                "endpoint": ENDPOINT,
                "simulation_only": record["simulation_only"],
                "name": text(record.get("name"), "Model name"),
                "version": text(record.get("version"), "Version", 80),
                "source": text(record.get("source"), "Model provenance", 1000),
                "intended_population": text(
                    record.get("intended_population"), "Intended population", 1000
                ),
                "specialties": specialties,
                "procedures": procedures,
                "features": validated,
                "intercept": number(record.get("intercept"), "Intercept", -1000, 1000),
                "acceptance": criteria,
                "status": "DRAFT",
                "registered_at": now.isoformat(),
                "registered_by": p.get("actor"),
                "evaluations": [],
            }
            model["specification_sha256"] = hashlib.sha256(
                encode(model).encode()
            ).hexdigest()
            self.models[key] = model
            return {
                "record_id": key,
                "message": "Immutable model version registered; review required",
            }
        if action in {
            "EVALUATE_CLINICAL_MODEL",
            "REVIEW_CLINICAL_MODEL",
            "REVOKE_CLINICAL_MODEL",
        }:
            model = self.models.get(p.get("model_id"))
            if not model:
                raise ValueError("Unknown model")
            if action == "EVALUATE_CLINICAL_MODEL":
                metrics = evaluate(model, p.get("rows"))
                metrics.update(
                    at=now.isoformat(),
                    actor=p.get("actor"),
                    source=text(
                        p.get("source"), "Holdout provenance and independence", 1000
                    ),
                )
                model["evaluations"].append(metrics)
                model["evaluations"] = model["evaluations"][-20:]
                # Every evaluation invalidates any previous review, including failed reevaluations.
                model.update(status="EVALUATED", review=None)
                if model.get("bundled_demo") and self.s.state.demo_enabled:
                    metrics.update(
                        dataset_kind="SYNTHETIC_BENCHMARK",
                        meaning="Synthetic demonstration evaluation; not clinical performance or independent clinical validation.",
                    )
                    model["status"] = (
                        "DEMO_READY"
                        if metrics["numerical_gate_passed"]
                        else "DEMO_EVALUATION_FAILED"
                    )
                    return {
                        "message": "Synthetic demo evaluation recorded",
                        "evaluation": metrics,
                    }
                return {
                    "message": "Holdout evaluation recorded; clinician review required",
                    "evaluation": metrics,
                }
            if action == "REVOKE_CLINICAL_MODEL":
                model.update(
                    status="REVOKED",
                    revocation={
                        "at": now.isoformat(),
                        "actor": p.get("actor"),
                        "reason": text(p.get("reason"), "Revocation reason", 1000),
                    },
                )
                return {"message": "Model revoked; further predictions blocked"}
            latest = (model["evaluations"] or [{}])[-1]
            if not latest.get("numerical_gate_passed"):
                raise ValueError(
                    "Latest independent holdout evaluation must pass the declared numerical gates"
                )
            if model["registered_by"] == p.get("actor") or latest.get("actor") == p.get(
                "actor"
            ):
                raise ValueError(
                    "Review requires a different clinician account from the registrar and evaluator"
                )
            expires = aware(p.get("expires_at"))
            if not now < expires <= now + timedelta(days=366):
                raise ValueError("Review expiry must be within one year")
            model.update(
                status="REVIEWED",
                review={
                    "actor": p.get("actor"),
                    "at": now.isoformat(),
                    "expires_at": expires.isoformat(),
                    "evidence": text(
                        p.get("evidence"),
                        "Clinical governance approval reference",
                        1000,
                    ),
                },
            )
            return {"message": "Attributed clinical review saved with expiry"}
        if action == "SET_CASE_CLINICAL_INPUTS":
            c = self.s.state.his.case_by_id(p.get("case_id"))
            if not c or c["status"] not in {"UNSCHEDULED", "SCHEDULED"}:
                raise ValueError("Preoperative case required")
            stamp = aware(p.get("observed_at"))
            if not 0 <= (now - stamp).total_seconds() <= 72 * 3600:
                raise ValueError("Inputs must be observed within the past 72 hours")
            values = p.get("features")
            if (
                not isinstance(values, dict)
                or set(values) - set(FEATURES)
                or "age_years" in values
            ):
                raise ValueError(
                    "Use supported predictors; age is derived from the patient record"
                )
            clean = {k: number(v, k, *FEATURES[k][:2]) for k, v in values.items()}
            for k in ("asa_class", "emergency"):
                if k in clean and clean[k] != int(clean[k]):
                    raise ValueError(k + " must be an integer")
            self.s.data.setdefault("clinical_inputs", {})[c["id"]] = {
                "patient_id": c["patient_id"],
                "features": clean,
                "observed_at": stamp.isoformat(),
                "source": text(p.get("source"), "Clinical input provenance", 1000),
                "actor": p.get("actor"),
            }
            return {
                "message": "Preoperative predictors saved with units and provenance"
            }
        return None

    def assessment(self, c, now):
        eligible = [
            m
            for m in self.models.values()
            if c["specialty"] in m["specialties"]
            and c["procedure"] in m["procedures"]
            and (
                m["status"] == "REVIEWED"
                and aware(m["review"]["expires_at"]) > now
                or self.s.state.demo_enabled
                and m.get("bundled_demo")
                and m["simulation_only"]
                and m["status"] == "DEMO_READY"
            )
            and (
                not m["simulation_only"]
                or self.s.state.hospital.config["mode"] == "SIMULATION"
            )
        ]
        if not eligible:
            return {
                "prediction_status": "REVIEWED_MODEL_REQUIRED",
                "predicted_success_percent": None,
                "reason": "No valid, independently reviewed model matches this procedure.",
            }
        patient = self.s.state.hospital.patients.get(c.get("patient_id"), {})
        inputs = self.s.data.get("clinical_inputs", {}).get(c["id"], {})
        if (
            inputs.get("patient_id") != c.get("patient_id")
            or not inputs.get("observed_at")
            or not 0
            <= (now - aware(inputs["observed_at"])).total_seconds()
            <= 72 * 3600
        ):
            return {
                "prediction_status": "FRESH_INPUTS_REQUIRED",
                "predicted_success_percent": None,
                "reason": "Confirmed preoperative inputs for this patient must be from the past 72 hours.",
            }
        dob = date.fromisoformat(patient["date_of_birth"])
        today = now.date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        values = {**inputs["features"], "age_years": age}
        model = sorted(
            eligible,
            key=lambda m: (m.get("review") or {}).get(
                "at", m.get("demo_activated_at", "")
            ),
            reverse=True,
        )[0]
        try:
            probability, terms = predict(model, values)
        except ValueError as exc:
            return {
                "prediction_status": "MISSING_OR_OUT_OF_RANGE_INPUTS",
                "predicted_success_percent": None,
                "reason": str(exc),
                "model_id": model["id"],
            }
        return {
            "prediction_status": (
                "SIMULATION_MODEL"
                if model["simulation_only"]
                else "REVIEWED_LOCAL_MODEL"
            ),
            "predicted_success_percent": probability * 100,
            "model_id": model["id"],
            "model_version": model["version"],
            "endpoint": ENDPOINT,
            "model_source": model["source"],
            "evaluation": model["evaluations"][-1],
            "review": model["review"],
            "contributions": terms,
            "inputs_observed_at": inputs["observed_at"],
            "reason": (
                "Artificial demo probability from synthetic inputs; not a patient-specific clinical estimate."
                if model.get("bundled_demo")
                else "Estimate from the selected model and recorded inputs; it does not determine surgery eligibility or HVAC control."
            ),
        }
