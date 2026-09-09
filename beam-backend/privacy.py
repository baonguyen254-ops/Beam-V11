"""Clinical fields are available only to ADMIN/CLINICIAN on HTTP and WebSocket."""


def for_role(payload, role):
    if role in {"ADMIN", "CLINICIAN"}:
        return payload

    def redact(value):
        if isinstance(value, list):
            return [redact(v) for v in value]
        if not isinstance(value, dict):
            return value
        out = {}
        for key, item in value.items():
            if key == "patients":
                out[key] = []
            elif key == "patient":
                out[key] = {"name": "Clinical record restricted to clinicians"} if item else None
            elif key == "clinical":
                out[key] = {
                    "prediction_status": "CLINICAL_ACCESS_REQUIRED",
                    "predicted_success_percent": None,
                    "cohort_count": 0,
                    "reason": "Sign in with a clinical role to view predictions.",
                }
            elif key in {
                "patient_id",
                "clinical_inputs",
                "clinical_estimate",
                "notes",
                "allergies",
                "conditions",
                "date_of_birth",
                "asa_class",
                "cancellation_reason",
            }:
                out[key] = None
            elif key == "case_label":
                out[key] = value.get("id") or value.get("case_id") or "Assigned case"
            elif key in {"incident_log", "incidents"}:
                out[key] = [
                    {
                        **r,
                        "type": (
                            r.get("type")
                            if r.get("status") in {"ALARM", "INFO"}
                            else "Operational action; details are in the restricted audit log"
                        ),
                    }
                    for r in item
                ]
            else:
                out[key] = redact(item)
        return out

    return redact(payload)
