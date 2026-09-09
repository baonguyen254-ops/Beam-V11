import { useState, type FormEvent } from "react";
import { useIdentity } from "./AuthGate";
import {
  useLive,
  Input,
  Modal,
  fmt,
  time,
  localDate,
  type Row,
  type Send,
} from "./v11-ui";
import "./v11.css";

export default function ClinicalWorkspace({
  online,
  sendCommand,
}: {
  online: boolean;
  sendCommand: Send;
}) {
  const user = useIdentity(),
    admin = user?.role === "ADMIN",
    clinician = admin || user?.role === "CLINICIAN";
  const [refresh, setRefresh] = useState(0),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [modal, setModal] = useState<{ kind: string; model?: Row } | null>(
    null,
  );
  const [json, setJson] = useState("");
  const resource = useLive(clinician ? "/api/clinical/models" : null, refresh);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!modal || !online || busy) return;
    const values = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    setNotice("");
    try {
      let payload: Row;
      if (modal.kind === "register")
        payload = {
          action: "REGISTER_CLINICAL_MODEL",
          model: JSON.parse(json),
        };
      else if (modal.kind === "evaluate")
        payload = {
          action: "EVALUATE_CLINICAL_MODEL",
          model_id: modal.model!.id,
          rows: JSON.parse(json),
          source: values.source,
        };
      else if (modal.kind === "review")
        payload = {
          action: "REVIEW_CLINICAL_MODEL",
          model_id: modal.model!.id,
          expires_at: new Date(String(values.expires_at)).toISOString(),
          evidence: values.evidence,
        };
      else
        payload = {
          action: "REVOKE_CLINICAL_MODEL",
          model_id: modal.model!.id,
          reason: values.reason,
        };
      const result = await sendCommand(payload);
      setNotice(result.message);
      if (result.ok) {
        setModal(null);
        setRefresh((n) => n + 1);
      }
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const open = (kind: string, model?: Row) => {
    setNotice("");
    setJson("");
    setModal({ kind, model });
  };
  if (!clinician)
    return (
      <section className="hw-panel v11">
        <h2>Clinical prediction models</h2>
        <p>This workspace is available to clinicians and administrators.</p>
      </section>
    );
  return (
    <div className="v11">
      <div className="v11-topbar">
        <div>
          <h2>Clinical prediction models</h2>
          <p>
            
            Prediction endpoint: no major complication within 30 days. This is separate from room operational readiness.
          </p>
        </div>
        {admin && (
          <button
            className="hw-primary"
            disabled={!online || busy}
            onClick={() => open("register")}
          >
            
            Import model version
          </button>
        )}
      </div>
      {resource.error && (
        <p className="hw-error" role="alert">
          {resource.error}
        </p>
      )}
      {notice && !modal && (
        <p role="status" className="v11-notice">
          {notice}
        </p>
      )}
      <section className="hw-panel">
        {resource.data?.models.some((m: Row) => m.bundled_demo) && <p className="v11-notice"><strong>Demo models are already active.</strong> Open a room to view its case prediction, or edit preoperative inputs to see the probability change. The evaluation datasets and coefficients are synthetic; no clinical approval is claimed.</p>}
        <h2>Model activation workflow</h2>
        <p>
          
          Import a logistic JSON specification, evaluate an independent holdout dataset, obtain a separate review with an expiry date, then enter preoperative data in Rooms to predict eligible cases.
        </p>
        <p>
          
          Demo models use artificial coefficients for demonstration only. AUC, Brier score and calibration describe the evaluation dataset; real clinical use requires separate clinical evidence and approval.
        </p>
        <p className="hw-note">
          
          Specification and data templates are included in examples/clinical. Model versions are immutable; changing coefficients requires a new version and evaluation.
        </p>
      </section>
      <div className="v11-model-list">
        {resource.data?.models.map((model: Row) => {
          const evaluation = model.evaluations.at(-1);
          return (
            <section className="hw-panel" key={model.id}>
              <div className="hw-heading">
                <div>
                  <h2>{model.name}</h2>
                  <p>
                    {model.id} · {model.version} ·{" "}
                    <span className="hw-tag">{model.status}</span>{" "}
                    {model.simulation_only && (
                      <span className="hw-tag">SIMULATION ONLY</span>
                    )}
                  </p>
                </div>
                <div className="v11-buttons">
                  {admin && (
                    <button
                      disabled={!online || busy}
                      onClick={() => open("evaluate", model)}
                    >
                      
                      Evaluate holdout
                    </button>
                  )}
                  <button
                    disabled={
                      !online ||
                      busy ||
                      model.bundled_demo ||
                      !evaluation?.numerical_gate_passed ||
                      model.registered_by === user?.id ||
                      evaluation?.actor === user?.id
                    }
                    onClick={() => open("review", model)}
                  >
                    
                    Approve use
                  </button>
                  <button
                    disabled={!online || busy || model.status === "REVOKED"}
                    onClick={() => open("revoke", model)}
                  >
                    
                    Revoke
                  </button>
                </div>
              </div>
              <p>
                <strong>Procedures:</strong> {model.procedures.join(", ")}
              </p>
              <p>
                <strong>Population:</strong> {model.intended_population}
              </p>
              <p>
                <strong>Source:</strong> {model.source}
              </p>
              <p>
                <strong>Inputs:</strong>{" "}
                {Object.entries(model.features)
                  .map(
                    ([key, spec]) =>
                      `${key} (${(spec as Row).min}…${(spec as Row).max})`,
                  )
                  .join("; ")}
              </p>
              {evaluation ? (
                <>
                  <div className="v11-model-metrics">
                    <span>
                      {model.bundled_demo ? "Synthetic benchmark: " : "Holdout: "}<strong>{evaluation.cases}</strong> cases
                    </span>
                    <span>
                      AUC <strong>{fmt(evaluation.auc, 3)}</strong>
                    </span>
                    <span>
                      Brier <strong>{fmt(evaluation.brier, 3)}</strong>
                    </span>
                    <span>
                      Calibration ECE{" "}
                      <strong>
                        {fmt(evaluation.expected_calibration_error, 3)}
                      </strong>
                    </span>
                  </div>
                  <p>
                    {evaluation.meaning}{" "}
                    {evaluation.numerical_gate_passed
                      ? "The declared numerical gates have passed."
                      : "The declared gates have not passed; approval is unavailable."}{" "}
                    · {time(evaluation.at)}
                  </p>
                  <details>
                    <summary>Calibration by probability band</summary>
                    <div className="hw-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Band</th>
                            <th>Cases</th>
                            <th>Mean prediction</th>
                            <th>Observed outcome</th>
                          </tr>
                        </thead>
                        <tbody>
                          {evaluation.calibration_bins.map((b: Row) => (
                            <tr key={b.lower}>
                              <td>
                                {fmt(b.lower * 100, 0)}…
                                {fmt((b.lower + 0.1) * 100, 0)}%
                              </td>
                              <td>{b.count}</td>
                              <td>{fmt(b.predicted * 100)}%</td>
                              <td>{fmt(b.observed * 100)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </>
              ) : (
                <p>No holdout evaluation yet.</p>
              )}
              {model.review && (
                <p>
                  
                  Reviewed by {model.review.actor}  · expires{" "}
                  {time(model.review.expires_at)} · {model.review.evidence}
                </p>
              )}
            </section>
          );
        })}
        {resource.data?.models.length === 0 && (
          <div className="hw-panel hw-empty">
            
            No model is installed. Import a specification and evaluation dataset, or launch the bundled demo workspace.
          </div>
        )}
      </div>
      {modal && (
        <Modal
          title={
            {
              register: "Import model JSON",
              evaluate: "Evaluate independent holdout",
              review: "Review model",
              revoke: "Revoke model",
            }[modal.kind] || "Model"
          }
          onClose={() => setModal(null)}
        >
          <form onSubmit={submit}>
            {notice && (
              <p className="v11-notice" role="status">
                {notice}
              </p>
            )}
            {["register", "evaluate"].includes(modal.kind) && (
              <>
                <label>
                  
                  Choose JSON file
                  <input
                    type="file"
                    accept=".json,application/json"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      if (file.size > 110000) {
                        setNotice(
                          "Maximum file size: 110 KB. Split or reduce the input dataset.",
                        );
                        return;
                      }
                      setJson(await file.text());
                    }}
                  />
                </label>
                <label>
                  {modal.kind === "register"
                    ? "Model specification"
                    : "Array of 20–500 de-identified holdout records"}
                  <textarea
                    rows={12}
                    value={json}
                    onChange={(e) => setJson(e.target.value)}
                    required
                    spellCheck={false}
                  />
                </label>
              </>
            )}
            {modal.kind === "evaluate" && (
              <Input
                name="source"
                label="Source and evidence of independence from training data"
                type="textarea"
              />
            )}
            {modal.kind === "review" && (
              <>
                <p>
                  
                  The reviewer must be different from the registrar and evaluator. Evidence must establish the approved local scope of use.
                </p>
                <Input
                  name="expires_at"
                  label="Expiry date"
                  type="datetime-local"
                  value={localDate(
                    new Date(Date.now() + 90 * 86400000).toISOString(),
                  )}
                />
                <Input
                  name="evidence"
                  label="Clinical approval / validation reference"
                  type="textarea"
                />
              </>
            )}
            {modal.kind === "revoke" && (
              <Input name="reason" label="Reason for revocation" type="textarea" />
            )}
            <div className="hw-footer">
              <button type="button" onClick={() => setModal(null)}>
                
                Close
              </button>
              <button
                type="submit"
                className="hw-primary"
                disabled={!online || busy}
              >
                {busy ? "Processing…" : "Submit and validate"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
