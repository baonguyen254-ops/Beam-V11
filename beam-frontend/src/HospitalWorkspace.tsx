import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import { api } from "./api";
import { useIdentity } from "./AuthGate";
import "./hospital.css";
import RoomWorkspace from "./RoomWorkspace";
import ClinicalWorkspace from "./ClinicalWorkspace";

// Registry/API records are extensible; legacy v9 telemetry remains typed in App.
type Row = Record<string, any>;
type Result = { ok: boolean; message: string; [key: string]: any };
type Props = {
  view: string;
  onView: (v: string) => void;
  rooms: unknown[];
  cases: unknown[];
  sendCommand: (p: Row) => Promise<Result>;
  online: boolean;
  mode: string;
};
const TABS = [
  ["rooms", "Rooms"],
  ["operations", "Operations"],
  ["cases", "Surgical cases"],
  ["people", "Patients & team"],
  ["devices", "Equipment"],
  ["intelligence", "Operational intelligence"],
  ["models", "Clinical prediction models"],
  ["energy", "Energy & ROI"],
  ["settings", "Settings & integrations"],
];
const SPECIALTIES = [
  "GENERAL",
  "CARDIAC",
  "VASCULAR",
  "GASTROINTESTINAL",
  "UROLOGY",
  "ORTHOPEDICS",
  "TRAUMA",
  "NEUROSURGERY",
  "ENT",
  "MINOR",
  "ENDOSCOPY",
  "GYNECOLOGY",
];
const date = (v: any) => (v ? new Date(v).toLocaleString("en-US") : "Not available");
const num = (v: any, d = 1) =>
  typeof v === "number" && Number.isFinite(v)
    ? v.toLocaleString("en-US", { maximumFractionDigits: d })
    : "Insufficient data";
const localTime = (v: any) => {
  const d = v ? new Date(v) : new Date(Date.now() + 3600000);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
const core = ["ANESTHESIA_MACHINE", "PATIENT_MONITOR", "SURGICAL_TABLE"];
function useResource(url: string | null, refreshKey = 0) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let disposed = false,
      timer: number;
    setData(null);
    setError("");
    async function load() {
      try {
        const result = await api(url!);
        if (!disposed) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        if (!disposed) timer = window.setTimeout(load, 5000);
      }
    }
    if (url) void load();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [url, refreshKey]);
  return { data, error };
}
function Field({
  name,
  label,
  value = "",
  type = "text",
  options,
  required = true,
  min,
  max,
  step,
}: {
  name: string;
  label: string;
  value?: any;
  type?: string;
  options?: { value: string; label: string }[];
  required?: boolean;
  min?: number;
  max?: number;
  step?: string;
}) {
  return (
    <label>
      {label}
      {options ? (
        <select name={name} defaultValue={value} required={required}>
          {!value && <option value="">Select…</option>}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : type === "textarea" ? (
        <textarea
          name={name}
          defaultValue={value}
          required={required}
          maxLength={1000}
        />
      ) : (
        <input
          name={name}
          type={type}
          defaultValue={value ?? ""}
          required={required}
          min={min}
          max={max}
          step={step || (type === "number" ? "any" : undefined)}
          maxLength={type === "password" ? 256 : 300}
        />
      )}
    </label>
  );
}
const opts = (v: string[]) => v.map((value) => ({ value, label: value }));
function Check({
  name,
  label,
  value = false,
  optionValue,
}: {
  name: string;
  label: string;
  value?: boolean;
  optionValue?: string;
}) {
  return (
    <label className="hw-check">
      <input
        name={name}
        type="checkbox"
        defaultChecked={value}
        value={optionValue}
      />
      {label}
    </label>
  );
}
function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: any;
  detail?: string;
}) {
  return (
    <div className="hw-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="hw-table-wrap">
      <table>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
function Pager({
  page,
  total,
  onPage,
}: {
  page: number;
  total: number;
  onPage: (v: number) => void;
}) {
  return (
    <div className="hw-pager">
      <span>
        {total}  records · Page {page + 1}/{Math.max(1, Math.ceil(total / 20))}
      </span>
      <button disabled={!page} onClick={() => onPage(page - 1)}>
        
        Previous
      </button>
      <button
        disabled={(page + 1) * 20 >= total}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </div>
  );
}
function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = previous;
    };
  }, []);
  return createPortal(
    <div className="hw hw-overlay" role="presentation">
      <section
        className="hw-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="hw-heading">
          <h2>{title}</h2>
          <button onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </section>
    </div>,
    document.fullscreenElement ?? document.body,
  );
}

export default function HospitalWorkspace({
  view,
  onView,
  rooms: rawRooms,
  cases: rawCases,
  sendCommand,
  online,
  mode,
}: Props) {
  const rooms = rawRooms as Row[],
    cases = rawCases as Row[],
    user = useIdentity();
  const [refresh, setRefresh] = useState(0),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [people, setPeople] = useState("patients");
  const [filter, setFilter] = useState("ALL"),
    [modal, setModal] = useState<{ kind: string; record: Row } | null>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [scope, setScope] = useState("facility"),
    [energySource, setEnergySource] = useState("CURRENT"),
    [resolution, setResolution] = useState("hour"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [caseId, setCaseId] = useState("");
  const [windows, setWindows] = useState<Row[]>([]),
    [windowStart, setWindowStart] = useState(""),
    [windowEnd, setWindowEnd] = useState("");
  const hospital = useResource(
    view === "operations" ? null : "/api/hospital",
    refresh,
  );
  const intelligence = useResource(
    view === "intelligence" ? "/api/intelligence" : null,
    refresh,
  );
  const archive = useResource(
    view === "cases" && filter === "ARCHIVE"
      ? `/api/cases/archive?limit=20&offset=${page * 20}&q=${encodeURIComponent(query)}`
      : null,
    refresh,
  );
  const params = new URLSearchParams({
    scope,
    resolution,
    source: energySource === "CURRENT" ? mode : energySource,
  });
  if (start) params.set("start", new Date(start).toISOString());
  if (end) params.set("end", new Date(end).toISOString());
  const energy = useResource(
    view === "energy" ? "/api/energy?" + params : null,
    refresh,
  );
  const audit = useResource(
    view === "settings" && ["ADMIN", "CLINICIAN"].includes(user?.role || "")
      ? "/api/audit?limit=50&offset=" + page * 50
      : null,
    refresh,
  );
  const users = useResource(
    view === "settings" && user?.role === "ADMIN" ? "/api/users" : null,
    refresh,
  );
  const h = hospital.data || {
    patients: [],
    staff: [],
    devices: [],
    config: {},
    integration: { actuator_receipts: [] },
  };
  const admin = user?.role === "ADMIN",
    clinician = admin || user?.role === "CLINICIAN";
  const canWrite = online && !hospital.error && !!hospital.data && !busy;
  const roomName = (id: string) =>
    rooms.find((r) => r.id === id)?.name || id || "No room assigned";
  const patientName = (id: string) =>
    h.patients.find((p: Row) => p.id === id)?.name || "No patient assigned";
  function open(kind: string, record: Row = {}) {
    setNotice("");
    setWindows(record.unavailable || []);
    setModal({ kind, record });
  }
  function switchView(v: string) {
    onView(v);
    setPage(0);
    setQuery("");
    setFilter("ALL");
    setNotice("");
  }
  async function command(payload: Row, close = true) {
    setBusy(true);
    try {
      const result = await sendCommand(payload);
      setNotice(result.message);
      if (result.ok) {
        setRefresh((v) => v + 1);
        if (close) setModal(null);
      }
      return result;
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!modal) return;
    const form = new FormData(event.currentTarget),
      r = modal.record,
      kind = modal.kind;
    const v: Row = Object.fromEntries(form);
    const bool = (key: string) => form.has(key);
    const numeric = (keys: string[]) =>
      keys.forEach((k) => {
        v[k] = v[k] === "" ? null : Number(v[k]);
      });
    try {
      if (kind === "patients") {
        numeric(["asa_class"]);
        await command({
          action: "UPSERT_PATIENT",
          record: {
            ...v,
            ...(r.id ? { id: r.id } : {}),
            active: bool("active"),
          },
        });
      }
      if (kind === "staff") {
        await command({
          action: "UPSERT_STAFF",
          record: {
            ...v,
            ...(r.id ? { id: r.id } : {}),
            specialties: form.getAll("specialties"),
            active: bool("active"),
            unavailable: windows,
          },
        });
      }
      if (kind === "devices") {
        numeric([
          "design_life_hours",
          "runtime_hours",
          "maintenance_interval_hours",
          "last_service_hours",
        ]);
        await command({
          action: "UPSERT_DEVICE",
          record: { ...v, ...(r.id ? { id: r.id } : {}) },
        });
      }
      if (kind === "service") {
        numeric(["efficiency_percent", "cost_vnd"]);
        await command({
          action: "SERVICE_DEVICE",
          device_id: r.id,
          ...v,
          inspection_passed: bool("inspection_passed"),
        });
      }
      if (kind === "newcase") {
        numeric(["estimated_duration_min", "prep_minutes", "recovery_minutes"]);
        await command({ action: "ADD_EXTERNAL_CASE", ...v });
      }
      if (kind === "case") {
        numeric(["estimated_duration_min"]);
        await command({
          action: "UPDATE_CASE",
          case_id: r.id,
          patient_id: v.patient_id,
          estimated_duration_min: v.estimated_duration_min,
          notes: v.notes,
          staff_ids: form.getAll("staff_ids"),
          required_device_types: [
            ...new Set([
              ...core,
              ...String(v.extra_devices || "")
                .split(",")
                .map((s) => s.trim().toUpperCase())
                .filter(Boolean),
            ]),
          ],
          consent_confirmed: bool("consent_confirmed"),
          preop_complete: bool("preop_complete"),
        });
      }
      if (kind === "schedule")
        await command({
          action: "MANUAL_SCHEDULE_CASE",
          case_id: r.id,
          room_id: v.room_id,
          start: new Date(v.start).toISOString(),
        });
      if (kind === "cancel")
        await command({
          action: "CANCEL_CASE",
          case_id: r.id,
          reason: v.reason,
        });
      if (kind === "estimate") {
        numeric(["percent"]);
        await command({
          action: "RECORD_CLINICAL_ESTIMATE",
          case_id: r.id,
          ...v,
        });
      }
      if (kind === "outcome")
        await command({
          action: "RECORD_OUTCOME",
          case_id: r.id,
          success: v.success === "true",
          notes: v.notes,
        });
      if (kind === "config") {
        numeric([
          "tariff_vnd_kwh",
          "emission_kg_kwh",
          "capex_vnd",
          "annual_opex_vnd",
          "sensor_timeout_seconds",
        ]);
        await command({
          action: "SET_HOSPITAL_CONFIG",
          config: { ...v, auto_assign_team: bool("auto_assign_team") },
        });
      }
      if (kind === "user") {
        setBusy(true);
        await api("/api/users", v);
        setRefresh((x) => x + 1);
        setModal(null);
        setNotice("Account created.");
      }
    } catch (e) {
      setNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  let list: Row[] =
    view === "cases"
      ? cases
      : view === "people"
        ? h[people]
        : view === "devices"
          ? h.devices
          : [];
  list = list.filter(
    (r) =>
      JSON.stringify(r).toLowerCase().includes(query.toLowerCase()) &&
      (view !== "cases" || filter === "ALL" || r.status === filter),
  );
  const total =
    filter === "ARCHIVE" && view === "cases"
      ? archive.data?.total || 0
      : list.length;
  const shown =
    filter === "ARCHIVE" && view === "cases"
      ? archive.data?.items || []
      : list.slice(page * 20, page * 20 + 20);
  const selected =
    cases.find((c) => c.id === caseId) ||
    cases.find((c) => c.status === "SCHEDULED") ||
    cases[0];
  const assessment = intelligence.data?.case_assessments?.find(
    (a: Row) => a.case_id === selected?.id,
  );
  const r = modal?.record || {},
    kind = modal?.kind;
  return (
    <div className="hw">
      <nav className="hw-nav" aria-label="Hospital workspace">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            className={view === key ? "selected" : ""}
            onClick={() => switchView(key)}
          >
            {label}
          </button>
        ))}
        <span
          className={"hw-mode " + (mode === "CONNECTED" ? "connected" : "")}
        >
          {mode === "CONNECTED" ? "CONNECTED BMS" : "SIMULATION"}
        </span>
      </nav>
      {view !== "operations" && (
        <main className="hw-content">
          <div className="hw-heading">
            <div>
              <span className="hw-eyebrow">BEAM / {mode}</span>
              <h1>{TABS.find((t) => t[0] === view)?.[1]}</h1>
            </div>
            <span className="hw-note">
              {online
                ? "Live updates"
                : "Disconnected or stale data; commands are locked"}
            </span>
          </div>
          {mode === "SIMULATION" && (
            <p className="hw-note">
              
              Demo records and simulated energy are illustrative. Display times follow this device; the energy ledger uses {h.config.timezone || "Asia/Ho_Chi_Minh"}.
            </p>
          )}
          {h.demo?.active && (
            <p className="v11-notice" role="status">
              <strong>ENGLISH DEMO</strong> · {h.demo.operating_rooms} operating rooms · {h.demo.equipment} devices · {h.demo.models} ready-to-run models · {h.demo.energy_history.days} days of synthetic energy history. All clinical and operating records are simulated.
            </p>
          )}
          {(hospital.error ||
            energy.error ||
            intelligence.error ||
            archive.error ||
            audit.error ||
            users.error) && (
            <p className="hw-error" role="alert">
              {hospital.error ||
                energy.error ||
                intelligence.error ||
                archive.error ||
                audit.error ||
                users.error}{" "}
              
              · Displayed data may be out of date.
            </p>
          )}
          {notice && !modal && (
            <p className="hw-note" role="status">
              {notice}
            </p>
          )}
          {!hospital.data && !hospital.error && (
            <p>Loading hospital data…</p>
          )}
          {view === "rooms" && (
            <RoomWorkspace
              telemetryRooms={rooms}
              online={canWrite}
              mode={mode}
              sendCommand={sendCommand}
              cases={cases}
              onOpen={open}
              onView={switchView}
              onEnergy={(id) => {
                setScope(id);
                switchView("energy");
              }}
            />
          )}
          {view === "models" && (
            <ClinicalWorkspace online={canWrite} sendCommand={sendCommand} />
          )}
          {["cases", "people", "devices"].includes(view) && (
            <section className="hw-panel">
              <div className="hw-toolbar">
                <input
                  aria-label="Search records"
                  placeholder="Search name, ID or specialty…"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setPage(0);
                  }}
                />
                {view === "cases" && (
                  <select
                    aria-label="Case status"
                    value={filter}
                    onChange={(e) => {
                      setFilter(e.target.value);
                      setPage(0);
                    }}
                  >
                    {opts([
                      "ALL",
                      "UNSCHEDULED",
                      "SCHEDULED",
                      "IN_PROGRESS",
                      "COMPLETED",
                      "CANCELLED",
                      "ARCHIVE",
                    ]).map((o) => (
                      <option key={o.value}>{o.value}</option>
                    ))}
                  </select>
                )}
                {view === "people" && (
                  <select
                    aria-label="Record type"
                    value={people}
                    onChange={(e) => {
                      setPeople(e.target.value);
                      setPage(0);
                    }}
                  >
                    <option value="patients">Patients</option>
                    <option value="staff">Clinicians & nurses</option>
                  </select>
                )}
                <button
                  className="hw-primary"
                  disabled={
                    !canWrite ||
                    (view === "cases" ||
                    (people === "patients" && view === "people")
                      ? !clinician
                      : !admin)
                  }
                  onClick={() =>
                    open(
                      view === "cases"
                        ? "newcase"
                        : view === "people"
                          ? people
                          : "devices",
                    )
                  }
                >
                  
                  + Add{" "}
                  {view === "cases"
                    ? "surgical case"
                    : view === "devices"
                      ? "device"
                      : "record"}
                </button>
              </div>
              {view === "cases" && (
                <Table
                  head={[
                    "Case / patient",
                    "Schedule & resources",
                    "Status",
                    "Actions",
                  ]}
                >
                  {shown.map((c: Row) => (
                    <tr key={c.id}>
                      <td>
                        <strong>{c.case_label}</strong>
                        <small>
                          {c.procedure} · {c.specialty}
                        </small>
                        <small>{patientName(c.patient_id)}</small>
                      </td>
                      <td>
                        {roomName(c.scheduled_room_id)}
                        <small>
                          {date(c.scheduled_start)} · {c.estimated_duration_min}{" "}
                          
                          min
                        </small>
                        <small>
                          {(c.staff_ids || [])
                            .map(
                              (id: string) =>
                                h.staff.find((p: Row) => p.id === id)?.name ||
                                id,
                            )
                            .join(", ") || "No team assigned"}
                        </small>
                        <small>
                          
                          Preparation: {roomName(c.prep_room_id)}  · Recovery:{" "}
                          {roomName(c.recovery_room_id)}
                        </small>
                      </td>
                      <td>
                        <span className="hw-tag">{c.status}</span>
                        <small>
                          {c.urgency} · {c.source}
                        </small>
                        <small>{c.constraint_reason || c.notes}</small>
                      </td>
                      <td>
                        <div className="hw-actions">
                          {["UNSCHEDULED", "SCHEDULED"].includes(c.status) && (
                            <>
                              <button
                                disabled={!canWrite || !clinician}
                                onClick={() => open("case", c)}
                              >
                                
                                Assign
                              </button>
                              <button
                                disabled={!canWrite || !clinician}
                                onClick={() => open("schedule", c)}
                              >
                                
                                Schedule
                              </button>
                              <button
                                disabled={!canWrite || !clinician}
                                onClick={() => open("cancel", c)}
                              >
                                
                                Cancel
                              </button>
                            </>
                          )}
                          {c.status === "SCHEDULED" && (
                            <button
                              disabled={!canWrite || !clinician}
                              onClick={() =>
                                void command(
                                  { action: "START_CASE", case_id: c.id },
                                  false,
                                )
                              }
                            >
                              
                              Confirm start
                            </button>
                          )}
                          {c.status === "IN_PROGRESS" && (
                            <button
                              disabled={!canWrite || !clinician}
                              onClick={() =>
                                void command(
                                  { action: "COMPLETE_CASE", case_id: c.id },
                                  false,
                                )
                              }
                            >
                              
                              Complete
                            </button>
                          )}
                          <button
                            disabled={!canWrite || !clinician}
                            onClick={() => open("estimate", c)}
                          >
                            
                            Clinician estimate
                          </button>
                          {c.status === "COMPLETED" && (
                            <button
                              disabled={!canWrite || !clinician}
                              onClick={() => open("outcome", c)}
                            >
                              
                              30-day outcome
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </Table>
              )}
              {view === "people" && (
                <Table head={["Record", "Details", "Status", "Actions"]}>
                  {shown.map((p: Row) => (
                    <tr key={p.id}>
                      <td>
                        <strong>{p.name}</strong>
                        <small>
                          {p.mrn || p.staff_code}
                          {p.is_demo ? " · DEMO" : ""}
                        </small>
                      </td>
                      <td>
                        {people === "patients"
                          ? `${p.date_of_birth} · ${p.sex} · ASA ${p.asa_class || "not recorded"}`
                          : p.role}
                        <small>
                          {people === "patients"
                            ? `Allergies: ${p.allergies || "not recorded"} · Conditions: ${p.conditions || "not recorded"}`
                            : (p.specialties || []).join(", ")}
                        </small>
                        {people === "staff" && (
                          <small>
                            {p.unavailable?.length || 0}  registered unavailability periods
                          </small>
                        )}
                      </td>
                      <td>{p.active ? "Active" : "Inactive"}</td>
                      <td>
                        <button
                          disabled={
                            !canWrite ||
                            (people === "patients" ? !clinician : !admin)
                          }
                          onClick={() => open(people, p)}
                        >
                          
                          View / edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </Table>
              )}
              {view === "devices" && (
                <Table
                  head={[
                    "Equipment",
                    "Room & status",
                    "Remaining service life",
                    "Measured performance",
                    "Actions",
                  ]}
                >
                  {shown.map((d: Row) => (
                    <tr key={d.id}>
                      <td>
                        <strong>{d.name}</strong>
                        <small>
                          {d.asset_tag} · {d.type}
                          {d.is_demo ? " · DEMO" : ""}
                        </small>
                      </td>
                      <td>
                        {roomName(d.room_id)}
                        <small>
                          {d.status} ·{" "}
                          {d.ready ? "Ready" : "Not ready"}
                        </small>
                      </td>
                      <td>
                        {num(d.remaining_life_hours)}  hours /{" "}
                        {num(d.remaining_life_percent)}%
                        <progress max={100} value={d.remaining_life_percent} />
                        <small>
                          
                          Runtime {num(d.runtime_hours)}h · Service due in{" "}
                          {num(d.maintenance_in_hours)}h
                        </small>
                      </td>
                      <td>
                        {d.inspection_efficiency_percent == null
                          ? "Not measured"
                          : num(d.inspection_efficiency_percent) + "%"}
                        <small>
                          {date(d.inspected_at)} ·{" "}
                          {d.inspection_passed === true
                            ? "Passed"
                            : d.inspection_passed === false
                              ? "Failed"
                              : "Not inspected"}
                        </small>
                      </td>
                      <td>
                        <div className="hw-actions">
                          <button
                            disabled={!canWrite || !admin}
                            onClick={() => open("devices", d)}
                          >
                            
                            Edit
                          </button>
                          <button
                            disabled={!canWrite || !admin}
                            onClick={() => open("service", d)}
                          >
                            
                            Service / inspect
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </Table>
              )}
              {!shown.length && (
                <p className="hw-empty">
                  
                  No matching records. Add a record or change the filters.
                </p>
              )}
              <Pager page={page} total={total} onPage={setPage} />
            </section>
          )}
          {view === "intelligence" && (
            <>
              <div className="hw-metrics">
                {(intelligence.data?.room_traits || []).map((t: Row) => (
                  <Metric
                    key={t.room_id}
                    label={t.room_name}
                    value={
                      t.ready_eta_minutes == null
                        ? "Learning"
                        : num(t.ready_eta_minutes) + " min"
                    }
                    detail={`${t.samples} cooling samples · ${num(t.cooling_c_per_min, 3)} °C/min · ${t.source}`}
                  />
                ))}
              </div>
              <div className="hw-columns">
                <section className="hw-panel">
                  <h2>Surgical readiness check</h2>
                  <select
                    aria-label="Case to assess"
                    value={selected?.id || ""}
                    onChange={(e) => setCaseId(e.target.value)}
                  >
                    {cases.map((c) => (
                      <option value={c.id} key={c.id}>
                        {c.case_label} · {c.procedure}
                      </option>
                    ))}
                  </select>
                  {assessment ? (
                    <>
                      <h3>{assessment.readiness.score}% of checks passed</h3>
                      <p className="hw-note">
                        
                        This is operational readiness, not a surgical outcome probability. Demo thresholds require local approval before real use.
                      </p>
                      {assessment.readiness.checks.map((c: Row, i: number) => (
                        <p className={c.ok ? "hw-pass" : "hw-fail"} key={i}>
                          {c.ok ? "✓" : "!"} {c.label}
                        </p>
                      ))}
                    </>
                  ) : (
                    <p>Select a pending case to assess readiness.</p>
                  )}
                </section>
                <section className="hw-panel">
                  <h2>Clinical outcome</h2>
                  <span className="hw-tag">
                    {assessment?.clinical?.prediction_status ||
                      "NO ASSESSMENT"}
                  </span>
                  <p>
                    {assessment?.clinical?.reason ||
                      "Select a case to view prediction eligibility."}
                  </p>
                  {assessment?.clinical?.predicted_success_percent != null && (
                    <h3>
                      {num(assessment.clinical.predicted_success_percent)}% probability of no major complication within 30 days
                    </h3>
                  )}
                  {clinician && (
                    <button onClick={() => switchView("models")}>
                      
                      View models and evaluation results
                    </button>
                  )}
                  {assessment?.clinical?.clinician_estimate && (
                    <p>
                      {num(assessment.clinical.clinician_estimate.percent)}% ·{" "}
                      {assessment.clinical.clinician_estimate.endpoint}
                      <small>
                        {assessment.clinical.clinician_estimate.source} ·{" "}
                        {date(
                          assessment.clinical.clinician_estimate.recorded_at,
                        )}
                      </small>
                    </p>
                  )}
                  <button
                    disabled={!canWrite || !clinician || !selected}
                    onClick={() => open("estimate", selected)}
                  >
                    
                    Record a sourced estimate
                  </button>
                  <p>
                    <a
                      href="https://riskcalculator.facs.org/RiskCalculator/"
                      target="_blank"
                      rel="noreferrer"
                    >
                      
                      Open the official ACS NSQIP calculator ↗
                    </a>
                  </p>
                  <h3>{h.demo?.active ? "Synthetic same-procedure cohort" : "Same-procedure cohort"}</h3>
                  {assessment?.clinical?.cohort ? (
                    <p>
                      {assessment.clinical.cohort.cases} cases ·{" "}
                      {num(assessment.clinical.cohort.observed_rate_percent)}% without major complications within 30 days · 95% Wilson interval:{" "}
                      {assessment.clinical.cohort.interval_95_percent.join(
                        " to ",
                      )}
                      %.
                    </p>
                  ) : (
                    <p>
                      
                      At least 30 real outcomes with complete 30-day follow-up are required. Available:{" "}
                      {assessment?.clinical?.cohort_count || 0} cases.
                    </p>
                  )}
                  <p className="hw-note">
                    
                    Unadjusted cohort statistics are not individual patient predictions.
                  </p>
                </section>
              </div>
              <section className="hw-panel">
                <h2>Duration traits from completed cases</h2>
                <p className="hw-note">
                  
                  {h.demo?.active ? "Synthetic completed cases populate these duration traits immediately. Suggestions remain editable in the case record." : "At least 5 confirmed cases are needed for an 80th-percentile suggestion. Clinicians confirm duration changes; suggestions do not overwrite the schedule."}
                </p>
                <Table
                  head={["Procedure", "Cases", "Median", "Buffered suggestion"]}
                >
                  {(intelligence.data?.duration_traits || []).map((t: Row) => (
                    <tr key={t.procedure}>
                      <td>{t.procedure}</td>
                      <td>{t.cases}</td>
                      <td>{num(t.median_minutes)}  min</td>
                      <td>
                        {t.eligible
                          ? num(t.suggested_buffered_minutes) + " min"
                          : "Insufficient data"}
                      </td>
                    </tr>
                  ))}
                </Table>
              </section>
            </>
          )}
          {view === "energy" && (
            <>
              <section className="hw-panel">
                <div className="hw-toolbar">
                  <select
                    aria-label="Energy scope"
                    value={scope}
                    onChange={(e) => setScope(e.target.value)}
                  >
                    <option value="facility">Entire facility</option>
                    {rooms.map((r) => (
                      <option value={r.id} key={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Resolution"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value)}
                  >
                    {[
                      ["second", "Second"],
                      ["minute", "Minute"],
                      ["hour", "Hour"],
                      ["day", "Day"],
                      ["month", "Month"],
                      ["year", "Year"],
                    ].map(([v, label]) => (
                      <option value={v} key={v}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Energy source"
                    value={energySource}
                    onChange={(e) => setEnergySource(e.target.value)}
                  >
                    <option value="CURRENT">Current mode</option>
                    <option value="CONNECTED">Measured only</option>
                    <option value="SIMULATION">Simulation only</option>
                    <option value="LEGACY_MIXED">Mixed-source v10 history</option>
                  </select>
                  <label>
                    
                    From
                    <input
                      type="datetime-local"
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                    />
                  </label>
                  <label>
                    
                    To
                    <input
                      type="datetime-local"
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                    />
                  </label>
                  <a
                    className="hw-button"
                    href={"/api/energy?" + params + "&format=csv"}
                    download
                  >
                    
                    Export CSV
                  </a>
                  <button
                    disabled={!canWrite || !admin}
                    onClick={() => open("config", h.config)}
                  >
                    
                    Tariff / investment
                  </button>
                </div>
                <div className="hw-metrics">
                  <Metric
                    label="Signed energy savings"
                    value={num(energy.data?.totals?.saved_kwh) + " kWh"}
                    detail="Negative values mean consumption exceeds baseline"
                  />
                  <Metric
                    label="Electricity cost savings"
                    value={num(energy.data?.totals?.savings_vnd, 0) + " ₫"}
                  />
                  <Metric
                    label="Observed time"
                    value={
                      num(
                        (energy.data?.totals?.observed_seconds || 0) / 3600,
                        3,
                      ) + " hours"
                    }
                    detail={`${num(energy.data?.coverage_percent)}% of report interval`}
                  />
                  <Metric
                    label="Meter coverage"
                    value={
                      num(
                        (100 * (energy.data?.totals?.measured_seconds || 0)) /
                          Math.max(
                            1,
                            energy.data?.totals?.observed_seconds || 0,
                          ),
                      ) + "%"
                    }
                  />
                </div>
                <div className="hw-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={energy.data?.points || []}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                      <XAxis
                        dataKey="period"
                        minTickGap={70}
                        tick={{ fontSize: 10 }}
                      />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Legend />
                      <Line
                        type="linear"
                        dataKey="baseline_kw"
                        name="Baseline kW TB"
                        stroke="#94a3b8"
                        dot={false}
                      />
                      <Line
                        type="linear"
                        dataKey="average_kw"
                        name="Actual / simulated mean kW"
                        stroke="#06b6d4"
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="hw-note">
                  
                  Missing connected data is not filled with simulation. Lines connect available periods; gaps may have no readings. Seconds are retained for 1 hour, minutes for 3 days, and hourly totals for long-term reports. Room baselines are allocated models; the facility baseline is an OpenStudio reference, without local weather or activity normalization.
                </p>
                {energy.data?.truncated && (
                  <p className="hw-error">
                    
                    Showing the latest 5,000 periods. Choose a shorter interval for a complete export.
                  </p>
                )}
                <Table
                  head={[
                    "Period",
                    "Baseline kWh",
                    "Consumption kWh",
                    "Savings kWh",
                    "Cost savings VND",
                  ]}
                >
                  {(energy.data?.points || []).slice(-100).map((p: Row) => (
                    <tr key={p.period}>
                      <td>{p.period}</td>
                      <td>{num(p.baseline_kwh, 4)}</td>
                      <td>{num(p.actual_kwh, 4)}</td>
                      <td>{num(p.saved_kwh, 4)}</td>
                      <td>{num(p.savings_vnd, 0)}</td>
                    </tr>
                  ))}
                </Table>
              </section>
              <section className="hw-panel">
                <h2>
                  ROI {scope === "facility" ? "entire facility" : roomName(scope)} ·{" "}
                  {start || end ? "Selected interval" : "All retained data"}
                </h2>
                <div className="hw-metrics">
                  <Metric
                    label="Initial investment"
                    value={num(energy.data?.finance?.capex_vnd, 0) + " ₫"}
                  />
                  <Metric
                    label="Net operating savings"
                    value={
                      num(energy.data?.finance?.net_operating_savings_vnd, 0) +
                      " ₫"
                    }
                    detail="Electricity savings less OPEX and incremental BMS costs"
                  />
                  <Metric
                    label="ROI after investment"
                    value={
                      energy.data?.finance?.roi_percent == null
                        ? "Enter CAPEX to calculate ROI"
                        : num(energy.data.finance.roi_percent) + "%"
                    }
                  />
                  <Metric
                    label="Projected payback"
                    value={
                      energy.data?.finance?.projected_payback_years == null
                        ? "Insufficient evidence"
                        : num(energy.data.finance.projected_payback_years) +
                          " years"
                    }
                  />
                </div>
                <p className="hw-note">
                  
                  ROI = (net savings − CAPEX) / CAPEX. Projections require 24 hours of observations and are not a guarantee of returns. Tariff changes apply to new samples only; historical samples retain their recorded tariff.
                </p>
              </section>
            </>
          )}
          {view === "settings" && (
            <>
              <section className="hw-panel">
                <div className="hw-heading">
                  <h2>Operating mode & policies</h2>
                  <button
                    disabled={!canWrite || !admin}
                    onClick={() => open("config", h.config)}
                  >
                    
                    Edit settings
                  </button>
                </div>
                <div className="hw-metrics">
                  <Metric label="Mode" value={h.config.mode} />
                  <Metric label="Reporting timezone" value={h.config.timezone} />
                  <Metric
                    label="Sensor timeout"
                    value={h.config.sensor_timeout_seconds + " seconds"}
                  />
                  <Metric
                    label="Automatic team assignment"
                    value={h.config.auto_assign_team ? "On" : "Off"}
                  />
                </div>
                <p className="hw-note">
                  
                  CONNECTED does not replace missing sensors with simulated data. Register real patients, staff and equipment, complete inspections and connect a gateway. Mode changes are blocked during active cases.
                </p>
              </section>
              <section className="hw-panel">
                <h2>HIS / BMS integrations</h2>
                <p>
                  
                  BMS gateways use BEAM_INTEGRATION_TOKEN. HIS uses a separate BEAM_HIS_INTEGRATION_TOKEN. Keep tokens out of the frontend. API setup is documented in the release guide.
                </p>
                <Table head={["Channel", "Endpoint", "Role"]}>
                  {[
                    [
                      "Sensor",
                      "POST /api/integrations/telemetry",
                      "Power, temperature, humidity, airflow and pressure difference",
                    ],
                    [
                      "Setpoint",
                      "GET /api/integrations/targets",
                      "Revisioned targets; issuance does not confirm PLC application",
                    ],
                    [
                      "Acknowledgement",
                      "POST /api/integrations/actuation",
                      "Gateway receipt with application status, revision and evidence",
                    ],
                    [
                      "Device runtime",
                      "POST /api/integrations/device-hours",
                      "Cumulative runtime counter; decreases are rejected",
                    ],
                    [
                      "HIS",
                      "POST /api/integrations/his/commands",
                      "Case records, scheduling and lifecycle with command_id",
                    ],
                  ].map((row) => (
                    <tr key={row[0]}>
                      {row.map((cell) => (
                        <td key={cell}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </Table>
                <h3>Gateway acknowledgements</h3>
                {!(h.integration.actuator_receipts || []).length && (
                  <p>No setpoint application has been acknowledged.</p>
                )}
                {(h.integration.actuator_receipts || []).map((r: Row) => (
                  <p key={r.room_id}>
                    {roomName(r.room_id)} · revision {r.revision} ·{" "}
                    {r.applied ? "Applied" : "Rejected"} · {date(r.at)} ·{" "}
                    {r.detail}
                  </p>
                ))}
              </section>
              {admin && (
                <section className="hw-panel">
                  <div className="hw-heading">
                    <h2>Accounts & permissions</h2>
                    <button onClick={() => open("user")} disabled={!canWrite}>
                      
                      + Account
                    </button>
                  </div>
                  <Table head={["Username", "Role", "Status"]}>
                    {(users.data || []).map((u: Row) => (
                      <tr key={u.id}>
                        <td>{u.username}</td>
                        <td>{u.role}</td>
                        <td>{u.active ? "Enabled" : "Locked"}</td>
                      </tr>
                    ))}
                  </Table>
                </section>
              )}
              {clinician && (
                <section className="hw-panel">
                  <h2>Persistent audit log</h2>
                  <Table
                    head={[
                      "Timestamp",
                      "Actor",
                      "Command",
                      "Result",
                      "Details",
                    ]}
                  >
                    {(audit.data || []).map((a: Row) => (
                      <tr key={a.id}>
                        <td>{date(a.at)}</td>
                        <td>{a.actor}</td>
                        <td>{a.action}</td>
                        <td>{a.ok ? "Accepted" : "Rejected"}</td>
                        <td>{a.detail}</td>
                      </tr>
                    ))}
                  </Table>
                  <div className="hw-pager">
                    <button disabled={!page} onClick={() => setPage(page - 1)}>
                      
                      Previous 50
                    </button>
                    <span>Trang {page + 1}</span>
                    <button
                      disabled={audit.data?.length !== 50}
                      onClick={() => setPage(page + 1)}
                    >
                      50 sau
                    </button>
                  </div>
                </section>
              )}
            </>
          )}
        </main>
      )}
      {modal && (
        <Dialog
          title={
            {
              patients: "Patient record",
              staff: "Team & availability",
              devices: "Equipment record",
              service: "Service and performance inspection",
              newcase: "Create surgical case",
              case: "Assignment & preoperative checks",
              schedule: "Manual scheduling",
              cancel: "Cancel case",
              estimate: "Clinician-provided estimate",
              outcome: "30-day follow-up outcome",
              config: "Hospital settings",
              user: "Create account",
            }[kind!] || ""
          }
          onClose={() => {
            if (!busy) setModal(null);
          }}
        >
          <form onSubmit={submit} key={kind + "-" + r.id}>
            <div className="hw-form-grid">
              {kind === "patients" && (
                <>
                  <Field name="mrn" label="Medical record number" value={r.mrn} />
                  <Field name="name" label="Patient name" value={r.name} />
                  <Field
                    name="date_of_birth"
                    label="Date of birth"
                    type="date"
                    value={r.date_of_birth}
                  />
                  <Field
                    name="sex"
                    label="Sex"
                    value={r.sex || "UNKNOWN"}
                    options={opts(["UNKNOWN", "FEMALE", "MALE", "OTHER"])}
                  />
                  <Field
                    name="asa_class"
                    label="Clinician-recorded ASA class (optional)"
                    type="number"
                    min={1}
                    max={6}
                    step="1"
                    value={r.asa_class}
                    required={false}
                  />
                  <Check
                    name="active"
                    label="Active patient record"
                    value={r.active ?? true}
                  />
                  <Field
                    name="allergies"
                    label="Allergies"
                    type="textarea"
                    value={r.allergies}
                    required={false}
                  />
                  <Field
                    name="conditions"
                    label="Medical conditions"
                    type="textarea"
                    value={r.conditions}
                    required={false}
                  />
                  <Field
                    name="notes"
                    label="Notes"
                    type="textarea"
                    value={r.notes}
                    required={false}
                  />
                </>
              )}
              {kind === "staff" && (
                <>
                  <Field
                    name="staff_code"
                    label="Staff ID"
                    value={r.staff_code}
                  />
                  <Field name="name" label="Full name" value={r.name} />
                  <Field
                    name="role"
                    label="Role"
                    value={r.role || "SURGEON"}
                    options={opts(["SURGEON", "ANESTHESIOLOGIST", "NURSE"])}
                  />
                  <Check
                    name="active"
                    label="Active staff member"
                    value={r.active ?? true}
                  />
                  <fieldset className="hw-wide">
                    <legend>Specialties</legend>
                    <div className="hw-checks">
                      {SPECIALTIES.map((s) => (
                        <Check
                          key={s}
                          name="specialties"
                          label={s}
                          optionValue={s}
                          value={(r.specialties || []).includes(s)}
                        />
                      ))}
                    </div>
                    <p className="hw-note">
                      
                      Recorded specialties:{" "}
                      {(r.specialties || []).join(", ") || "none"}.
                    </p>
                  </fieldset>
                  <div className="hw-wide">
                    <h3>Unavailable periods</h3>
                    {windows.map((w, i) => (
                      <p key={i}>
                        {date(w.start)}  to {date(w.end)}{" "}
                        <button
                          type="button"
                          onClick={() =>
                            setWindows(windows.filter((_, j) => j !== i))
                          }
                        >
                          
                          Remove
                        </button>
                      </p>
                    ))}
                    <div className="hw-toolbar">
                      <input
                        aria-label="Unavailable from"
                        type="datetime-local"
                        value={windowStart}
                        onChange={(e) => setWindowStart(e.target.value)}
                      />
                      <input
                        aria-label="Unavailable until"
                        type="datetime-local"
                        value={windowEnd}
                        onChange={(e) => setWindowEnd(e.target.value)}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          if (
                            windowStart &&
                            windowEnd &&
                            new Date(windowEnd) > new Date(windowStart)
                          ) {
                            setWindows([
                              ...windows,
                              {
                                start: new Date(windowStart).toISOString(),
                                end: new Date(windowEnd).toISOString(),
                              },
                            ]);
                            setWindowStart("");
                            setWindowEnd("");
                          } else setNotice("Choose a valid unavailability interval.");
                        }}
                      >
                        
                        Add unavailability
                      </button>
                    </div>
                  </div>
                </>
              )}
              {kind === "devices" && (
                <>
                  <Field
                    name="asset_tag"
                    label="Asset tag"
                    value={r.asset_tag}
                  />
                  <Field name="name" label="Equipment name" value={r.name} />
                  <Field
                    name="room_id"
                    label="Rooms"
                    value={r.room_id}
                    options={rooms.map((r) => ({ value: r.id, label: r.name }))}
                  />
                  <Field
                    name="type"
                    label="Equipment type (UPPERCASE code)"
                    value={r.type || "PATIENT_MONITOR"}
                  />
                  <Field
                    name="status"
                    label="Status"
                    value={r.status || "AVAILABLE"}
                    options={opts([
                      "AVAILABLE",
                      "MAINTENANCE",
                      "OFFLINE",
                      "RETIRED",
                    ])}
                  />
                  <Field
                    name="commissioned_on"
                    label="Commissioning date"
                    type="date"
                    value={
                      r.commissioned_on || new Date().toISOString().slice(0, 10)
                    }
                  />
                  <Field
                    name="design_life_hours"
                    label="Design life (hours, manufacturer specification)"
                    type="number"
                    min={1}
                    value={r.design_life_hours || 20000}
                  />
                  <Field
                    name="runtime_hours"
                    label="Cumulative runtime hours"
                    type="number"
                    min={r.runtime_hours || 0}
                    value={r.runtime_hours || 0}
                  />
                  <Field
                    name="maintenance_interval_hours"
                    label="Maintenance interval (hours)"
                    type="number"
                    min={1}
                    value={r.maintenance_interval_hours || 1000}
                  />
                  <Field
                    name="last_service_hours"
                    label="Runtime at last service"
                    type="number"
                    min={0}
                    value={r.last_service_hours || 0}
                  />
                  <p className="hw-note hw-wide">
                    
                    Remaining life uses declared design life and runtime; it is not a failure probability. Performance requires a recorded inspection.
                  </p>
                </>
              )}
              {kind === "service" && (
                <>
                  <Field
                    name="efficiency_percent"
                    label="Measured performance (%)"
                    type="number"
                    min={0}
                    max={100}
                  />
                  <Field
                    name="cost_vnd"
                    label="Service cost (VND)"
                    type="number"
                    min={0}
                    value={0}
                  />
                  <Field
                    name="notes"
                    label="Inspection report, method and result"
                    type="textarea"
                  />
                  <Check
                    name="inspection_passed"
                    label="Technician confirms inspection passed"
                  />
                  <div className="hw-wide">
                    <h3>History</h3>
                    {(r.service_history || []).map((s: Row, i: number) => (
                      <p key={i}>
                        {date(s.at)} · {num(s.efficiency_percent)}% ·{" "}
                        {s.inspection_passed ? "Passed" : "Failed"} · {s.notes}
                      </p>
                    ))}
                  </div>
                </>
              )}
              {kind === "newcase" && (
                <>
                  <Field name="case_label" label="Case ID / label" />
                  <Field name="procedure" label="Procedure name" />
                  <Field
                    name="patient_id"
                    label="Registered patient"
                    options={h.patients
                      .filter(
                        (p: Row) =>
                          p.active && (mode !== "CONNECTED" || !p.is_demo),
                      )
                      .map((p: Row) => ({
                        value: p.id,
                        label: p.mrn + " · " + p.name,
                      }))}
                  />
                  <Field
                    name="specialty"
                    label="Specialties"
                    value="GENERAL"
                    options={opts(SPECIALTIES)}
                  />
                  <Field
                    name="urgency"
                    label="Priority"
                    value="ELECTIVE"
                    options={opts(["STAT", "EMERGENCY", "URGENT", "ELECTIVE"])}
                  />
                  <Field
                    name="estimated_duration_min"
                    label="Estimated duration (min)"
                    type="number"
                    min={15}
                    max={480}
                    step="1"
                    value={90}
                  />
                  <Field
                    name="prep_minutes"
                    label="Preparation (min)"
                    type="number"
                    min={5}
                    max={90}
                    step="1"
                    value={20}
                  />
                  <Field
                    name="recovery_minutes"
                    label="Recovery (min)"
                    type="number"
                    min={15}
                    max={240}
                    step="1"
                    value={45}
                  />
                  <p className="hw-note hw-wide">
                    
                    Automatic scheduling requires a patient, team, equipment and support rooms. Starting a real case still requires confirmed preoperative checks.
                  </p>
                </>
              )}
              {kind === "case" && (
                <>
                  <Field
                    name="patient_id"
                    label="Patients"
                    value={r.patient_id}
                    options={h.patients
                      .filter(
                        (p: Row) =>
                          p.active && (mode !== "CONNECTED" || !p.is_demo),
                      )
                      .map((p: Row) => ({
                        value: p.id,
                        label: p.mrn + " · " + p.name,
                      }))}
                  />
                  <Field
                    name="estimated_duration_min"
                    label="Duration (min)"
                    type="number"
                    min={15}
                    max={480}
                    step="1"
                    value={r.estimated_duration_min}
                  />
                  <Check
                    name="consent_confirmed"
                    label="Surgical consent confirmed"
                    value={r.consent_confirmed}
                  />
                  <Check
                    name="preop_complete"
                    label="Preoperative checks completed"
                    value={r.preop_complete}
                  />
                  <fieldset className="hw-wide">
                    <legend>
                      
                      Team; missing roles are assigned automatically when the policy is enabled
                    </legend>
                    <div className="hw-checks">
                      {h.staff
                        .filter(
                          (p: Row) =>
                            p.active && (mode !== "CONNECTED" || !p.is_demo),
                        )
                        .map((p: Row) => (
                          <label key={p.id} className="hw-check">
                            <input
                              name="staff_ids"
                              type="checkbox"
                              value={p.id}
                              defaultChecked={(r.staff_ids || []).includes(
                                p.id,
                              )}
                            />
                            {p.name} · {p.role}
                          </label>
                        ))}
                    </div>
                  </fieldset>
                  <Field
                    name="extra_devices"
                    label="Additional device types, comma-separated"
                    value={(r.required_device_types || [])
                      .filter((s: string) => !core.includes(s))
                      .join(", ")}
                    required={false}
                  />
                  <Field
                    name="notes"
                    label="Notes"
                    value={r.notes}
                    required={false}
                  />
                  <p className="hw-note hw-wide">
                    
                    Every case requires an anesthesia machine, patient monitor and surgical table.
                  </p>
                </>
              )}
              {kind === "schedule" && (
                <>
                  <Field
                    name="room_id"
                    label="Operating rooms"
                    value={r.scheduled_room_id}
                    options={rooms
                      .filter((r) => r.category === "OPERATING_ROOM")
                      .map((r) => ({ value: r.id, label: r.name }))}
                  />
                  <Field
                    name="start"
                    label="Start time in this device's timezone"
                    type="datetime-local"
                    value={localTime(r.scheduled_start)}
                  />
                  <p className="hw-note hw-wide">
                    
                    Schedule within 48 hours with enough preparation time. The backend checks case, team, equipment, recovery and turnover conflicts.
                  </p>
                </>
              )}
              {kind === "cancel" && (
                <Field
                  name="reason"
                  label="Cancellation reason (required)"
                  type="textarea"
                />
              )}
              {kind === "estimate" && (
                <>
                  <p className="hw-note hw-wide">
                    
                    This records a clinician or external-model estimate; it does not establish local clinical validation.
                  </p>
                  <Field
                    name="percent"
                    label="Clinician estimate (%)"
                    type="number"
                    min={0}
                    max={100}
                  />
                  <Field name="endpoint" label="Outcome definition and follow-up period" />
                  <Field
                    name="source"
                    label="Source, model, version / evidence"
                  />
                </>
              )}
              {kind === "outcome" && (
                <>
                  <p className="hw-note hw-wide">
                    
                    Record only after 30 days from confirmed completion. The endpoint is no major complication within 30 days; the clinician verifies follow-up evidence.
                  </p>
                  <Field
                    name="success"
                    label="Verified outcome"
                    value="true"
                    options={[
                      {
                        value: "true",
                        label: "No major complication within 30 days",
                      },
                      {
                        value: "false",
                        label: "Major complication within 30 days",
                      },
                    ]}
                  />
                  <Field
                    name="notes"
                    label="Follow-up evidence"
                    type="textarea"
                  />
                </>
              )}
              {kind === "config" && (
                <>
                  <Field
                    name="mode"
                    label="Mode"
                    value={r.mode}
                    options={opts(["SIMULATION", "CONNECTED"])}
                  />
                  <Field
                    name="timezone"
                    label="IANA timezone"
                    value={r.timezone}
                  />
                  <Field
                    name="tariff_vnd_kwh"
                    label="Electricity tariff (VND/kWh)"
                    type="number"
                    min={0}
                    value={r.tariff_vnd_kwh}
                  />
                  <Field
                    name="emission_kg_kwh"
                    label="CO₂ factor (kg/kWh)"
                    type="number"
                    min={0}
                    value={r.emission_kg_kwh}
                  />
                  <Field
                    name="capex_vnd"
                    label="Project CAPEX (VND)"
                    type="number"
                    min={0}
                    value={r.capex_vnd}
                  />
                  <Field
                    name="annual_opex_vnd"
                    label="Annual OPEX (VND)"
                    type="number"
                    min={0}
                    value={r.annual_opex_vnd}
                  />
                  <Field
                    name="sensor_timeout_seconds"
                    label="Sensor timeout (seconds)"
                    type="number"
                    min={1}
                    max={300}
                    value={r.sensor_timeout_seconds}
                  />
                  <Check
                    name="auto_assign_team"
                    label="Automatically assign qualified staff without schedule conflicts"
                    value={r.auto_assign_team}
                  />
                  <p className="hw-note hw-wide">
                    
                    Switching mode archives pending demo cases and clears sensor buffers. Historical data is retained.
                  </p>
                </>
              )}
              {kind === "user" && (
                <>
                  <Field name="username" label="Username" />
                  <Field
                    name="password"
                    label="Password (at least 12 characters)"
                    type="password"
                  />
                  <Field
                    name="role"
                    label="Role"
                    value="VIEWER"
                    options={opts(["ADMIN", "CLINICIAN", "OPERATOR", "VIEWER"])}
                  />
                </>
              )}
            </div>
            {notice && (
              <p className="hw-error" role="alert">
                {notice}
              </p>
            )}
            <div className="hw-footer">
              <button
                type="button"
                disabled={busy}
                onClick={() => setModal(null)}
              >
                
                Close
              </button>
              <button className="hw-primary" disabled={!canWrite}>
                {busy ? "Processing…" : "Save and confirm"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}
