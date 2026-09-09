import { useState, type FormEvent } from "react";
import {
  Activity,
  ArrowRight,
  CalendarClock,
  CircleCheck,
  Gauge,
  SlidersHorizontal,
  Users,
  Zap,
} from "lucide-react";
import { useIdentity } from "./AuthGate";
import {
  useLive,
  Metric,
  Modal,
  Input,
  fmt,
  time,
  localDate,
  stageName,
  type Row,
  type Send,
} from "./v11-ui";
import "./v11.css";

type Props = {
  telemetryRooms: Row[];
  online: boolean;
  mode: string;
  sendCommand: Send;
  cases: Row[];
  onOpen: (kind: string, record?: Row) => void;
  onView: (view: string) => void;
  onEnergy: (id: string) => void;
};

export default function RoomWorkspace({
  telemetryRooms,
  online,
  mode,
  sendCommand,
  cases,
  onOpen,
  onView,
  onEnergy,
}: Props) {
  const user = useIdentity();
  const admin = user?.role === "ADMIN",
    clinician = admin || user?.role === "CLINICIAN",
    operator = user?.role !== "VIEWER";
  const [selected, setSelected] = useState(""),
    [filter, setFilter] = useState("OPERATING_ROOM"),
    [search, setSearch] = useState("");
  const [refresh, setRefresh] = useState(0),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [modal, setModal] = useState<{ kind: string; record: Row } | null>(
    null,
  );
  const overview = useLive("/api/rooms/overview", refresh);
  const allRooms: Row[] = overview.data?.rooms || [];
  const visible = allRooms.filter(
    (r) =>
      (filter === "ALL" || r.category === filter) &&
      `${r.name} ${r.id}`.toLowerCase().includes(search.toLowerCase()),
  );
  const roomId = visible.some((r) => r.id === selected)
    ? selected
    : visible[0]?.id;
  const detail = useLive(
    roomId ? "/api/rooms/" + encodeURIComponent(roomId) : null,
    refresh,
  );
  const raw = detail.data;
  const live = telemetryRooms.find((room) => room.id === roomId);
  const fresh =
    mode === "SIMULATION" || live?.telemetry_source === "BMS_MEASURED";
  const d =
    raw && live
      ? {
          ...raw,
          room: { ...raw.room, ...live },
          control: {
            ...raw.control,
            status: live.status,
            reason: live.control_source,
            target_temp_c: live.target_temp_c,
            target_humidity: live.target_humidity,
            target_airflow_m3h: live.target_airflow_m3h,
          },
          instant_energy: {
            ...raw.instant_energy,
            actual_kw: fresh ? live.power_kw : null,
            baseline_kw:
              live.reference_power_kw ?? raw.instant_energy.baseline_kw,
            saved_kw: fresh
              ? (live.reference_power_kw ?? raw.instant_energy.baseline_kw) -
                live.power_kw
              : null,
          },
        }
      : raw;
  const r = d?.room,
    current = d?.current_case,
    c = current?.case;
  const write = online && !!d && !overview.error && !detail.error && !busy;
  const [plan, setPlan] = useState<Row | null>(null),
    [planCases, setPlanCases] = useState<string[]>([]);
  const pending = cases.filter((c) => c.status === "UNSCHEDULED");

  async function act(payload: Row, close = true) {
    setBusy(true);
    setNotice("");
    try {
      const result = await sendCommand(payload);
      setNotice(result.message);
      if (result.ok) {
        setRefresh((n) => n + 1);
        if (close) setModal(null);
      }
      return result;
    } catch (e) {
      setNotice((e as Error).message);
      return { ok: false, message: (e as Error).message };
    } finally {
      setBusy(false);
    }
  }
  function open(kind: string, record: Row = {}) {
    setNotice("");
    setModal({ kind, record });
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!modal || !write) return;
    const f = Object.fromEntries(new FormData(e.currentTarget)),
      v: Row = f,
      m = modal.record;
    try {
      if (modal.kind === "controls")
        await act({
          action: "SET_ROOM_MANUAL_TARGETS",
          room_id: m.id,
          temp_c: Number(v.temp_c),
          humidity: Number(v.humidity),
          airflow_percent: Number(v.airflow_percent),
        });
      if (modal.kind === "finance")
        await act({
          action: "SET_ROOM_FINANCE",
          room_id: m.id,
          allocation_percent: Number(v.allocation_percent),
        });
      if (modal.kind === "cost")
        await act({
          action: "RECORD_BMS_COST",
          room_id: m.id,
          cost_vnd: Number(v.cost_vnd),
          evidence: v.evidence,
        });
      if (modal.kind === "engineering")
        await act({
          action: "SET_DEVICE_ENGINEERING",
          device_id: m.id,
          minimum_performance_percent: Number(v.minimum_performance_percent),
          replacement_cost_vnd: Number(v.replacement_cost_vnd),
          retire_on: v.retire_on ? new Date(v.retire_on).toISOString() : null,
          evidence: v.evidence,
        });
      if (modal.kind === "inspection")
        await act({
          action: "RECORD_DEVICE_INSPECTION",
          device_id: m.id,
          observed_at: new Date(v.observed_at).toISOString(),
          runtime_hours: Number(v.runtime_hours),
          performance_percent: Number(v.performance_percent),
          evidence: v.evidence,
        });
      if (modal.kind === "clinical") {
        const features: Row = {};
        for (const key of [
          "asa_class",
          "emergency",
          "bmi",
          "hemoglobin_g_dl",
          "albumin_g_dl",
          "creatinine_mg_dl",
        ])
          if (v[key] !== "") features[key] = Number(v[key]);
        await act({
          action: "SET_CASE_CLINICAL_INPUTS",
          case_id: m.case.id,
          observed_at: new Date(v.observed_at).toISOString(),
          source: v.source,
          features,
        });
      }
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  const m = modal?.record || {};
  return (
    <div className="v11">
      <div className="v11-topbar">
        <div>
          <h2>Room command center</h2>
          <p>Room conditions, surgical teams and equipment in one operational view.</p>
        </div>
        <div className="v11-buttons">
          <button onClick={() => onView("operations")}>
            <Activity size={16} /> Digital twin & Command Center
          </button>
          {clinician && (
            <button
              className="hw-primary"
              onClick={() => {
                setPlan(null);
                setPlanCases(pending.slice(0, 16).map((c) => c.id));
                open("plan");
              }}
              disabled={!online || busy}
            >
              <CalendarClock size={16} />  Propose schedule
            </button>
          )}
        </div>
      </div>
      {(overview.error || detail.error) && (
        <p role="alert" className="hw-error">
          {overview.error || detail.error}. Displayed data may be out of date.
        </p>
      )}
      {notice && !modal && (
        <p role="status" className="v11-notice">
          {notice}
        </p>
      )}
      <div className="v11-layout">
        <aside className="v11-room-list hw-panel">
          <label>
            
            Room type
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setSelected("");
              }}
            >
              <option value="OPERATING_ROOM">Operating rooms</option>
              <option value="ALL">All conditioned rooms</option>
              <option value="RECOVERY">Recovery</option>
              <option value="PREOP">Preoperative</option>
              <option value="PREP">Preparation</option>
            </select>
          </label>
          <label>
            
            Find a room
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Room name or ID"
            />
          </label>
          <div className="v11-room-scroll">
            {visible.map((room) => (
              <button
                key={room.id}
                className={
                  roomId === room.id ? "v11-room selected" : "v11-room"
                }
                onClick={() => setSelected(room.id)}
                aria-pressed={roomId === room.id}
              >
                <span>
                  <strong>{room.name}</strong>
                  <i
                    className={room.sensor_fresh ? "v11-dot" : "v11-dot stale"}
                  />
                </span>
                <small>
                  {stageName[room.status] || room.status} · {fmt(room.power_kw)}{" "}
                  kW
                </small>
                <small>{room.case_label || "No case booked"}</small>
              </button>
            ))}
            {!visible.length && (
              <p className="hw-empty">
                {overview.data ? "No matching rooms." : "Loading rooms…"}
              </p>
            )}
          </div>
        </aside>
        <div className="v11-room-content">
          {!d && (
            <div className="hw-panel hw-empty">
              {roomId
                ? "Synchronizing room details…"
                : "Select a room to manage."}
            </div>
          )}
          {d && r && (
            <>
              <div className="v11-room-heading">
                <div>
                  <span className="hw-eyebrow">
                    {r.id} / {mode === "CONNECTED" ? "MEASURED" : "SIMULATION"}
                  </span>
                  <h2>{r.name}</h2>
                  <p>
                    {stageName[d.control.status] || d.control.status} ·{" "}
                    {d.control.reason}
                  </p>
                </div>
                <div className="v11-buttons">
                  <button
                    disabled={!write || !operator}
                    onClick={() => open("controls", r)}
                  >
                    <SlidersHorizontal size={16} />  Room controls
                  </button>
                  <button
                    disabled={!write || !operator}
                    onClick={() =>
                      act({ action: "RELEASE_ROOM_AUTOMATION", room_id: r.id })
                    }
                  >
                    
                    Schedule & AI
                  </button>
                </div>
              </div>
              {d.alerts.length > 0 && (
                <div className="v11-alerts" role="status">
                  {d.alerts.map((a: Row, i: number) => (
                    <p
                      key={i}
                      className={
                        a.level === "critical" ? "hw-error" : "v11-warning"
                      }
                    >
                      {a.message}
                    </p>
                  ))}
                </div>
              )}
              <div className="v11-metrics">
                <Metric
                  label="Temperature"
                  value={<>{fmt(r.temp_c)} °C</>}
                  detail={`Target ${fmt(d.control.target_temp_c)} °C`}
                />
                <Metric
                  label="Humidity / airflow"
                  value={<>{fmt(r.humidity)} %RH</>}
                  detail={`${fmt(r.airflow_m3h, 0)} / ${fmt(d.control.target_airflow_m3h, 0)} m³/h target`}
                />
                <Metric
                  label="Room power"
                  value={<>{fmt(d.instant_energy.actual_kw, 2)} kW</>}
                  detail={`Baseline ${fmt(d.instant_energy.baseline_kw, 2)} kW`}
                />
                <Metric
                  label="Instant savings"
                  value={<>{fmt(d.instant_energy.saved_kw, 2)} kW</>}
                  detail="Negative when consumption exceeds baseline"
                />
              </div>
              <div className="v11-columns">
                <section className="hw-panel">
                  <div className="hw-heading">
                    <h2>
                      <Users size={19} />  Surgical case & team
                    </h2>
                    {clinician && (
                      <button
                        disabled={!write}
                        onClick={() => onOpen("newcase")}
                      >
                        
                        Add case
                      </button>
                    )}
                  </div>
                  {!current ? (
                    <p className="hw-empty">
                      
                      No active or upcoming case in this room.
                    </p>
                  ) : (
                    <>
                      <div className="v11-case-name">
                        <strong>{c.case_label}</strong>
                        <span className="hw-tag">{c.status}</span>
                        <span className="hw-tag">{c.urgency}</span>
                      </div>
                      <h3>{c.procedure}</h3>
                      <p>
                        {time(c.scheduled_start)} ·{" "}
                        {fmt(c.estimated_duration_min, 0)}  estimated min
                      </p>
                      <div className="v11-patient">
                        <strong>
                          {current.patient?.name || "No patient assigned"}
                        </strong>
                        <p>
                          {current.patient?.mrn} ·{" "}
                          {current.patient?.date_of_birth}{" "}
                          {current.patient?.is_demo && "· DEMO RECORD"}
                        </p>
                        <p>
                          
                          Allergies:{" "}
                          {current.patient?.allergies ||
                            "Not recorded"}
                        </p>
                        <p>
                          
                          Conditions:{" "}
                          {current.patient?.conditions ||
                            "Not recorded"}
                        </p>
                      </div>
                      <div className="v11-team">
                        {current.team.map((p: Row) => (
                          <div key={p.id}>
                            <span>{p.role}</span>
                            <strong>{p.name}</strong>
                          </div>
                        ))}
                      </div>
                      <p className="hw-note">
                        
                        Assigned personnel; this is not a measured occupancy count.
                      </p>
                      <div className="v11-buttons">
                        {clinician &&
                          ["UNSCHEDULED", "SCHEDULED"].includes(c.status) && (
                            <>
                              <button
                                disabled={!write}
                                onClick={() => onOpen("case", c)}
                              >
                                
                                Record & assignment
                              </button>
                              <button
                                disabled={!write}
                                onClick={() => onOpen("schedule", c)}
                              >
                                
                                Reschedule
                              </button>
                              <button
                                disabled={!write}
                                onClick={() => onOpen("cancel", c)}
                              >
                                
                                Cancel case
                              </button>
                            </>
                          )}
                        {clinician && c.status === "SCHEDULED" && (
                          <button
                            className="hw-primary"
                            disabled={!write || !current.readiness.ready}
                            onClick={() =>
                              act({ action: "START_CASE", case_id: c.id })
                            }
                          >
                            
                            Confirm start
                          </button>
                        )}
                        {clinician && c.status === "IN_PROGRESS" && (
                          <button
                            className="hw-primary"
                            disabled={!write}
                            onClick={() =>
                              act({ action: "COMPLETE_CASE", case_id: c.id })
                            }
                          >
                            
                            Confirm completion
                          </button>
                        )}
                      </div>
                      <h3>Start readiness · {current.readiness.score}%</h3>
                      <ul className="v11-checklist">
                        {current.readiness.checks.map(
                          (check: Row, i: number) => (
                            <li key={i} className={check.ok ? "pass" : "fail"}>
                              <CircleCheck size={16} />
                              {check.label}
                            </li>
                          ),
                        )}
                      </ul>
                    </>
                  )}
                </section>
                <section className="hw-panel">
                  <h2>
                    <CalendarClock size={19} />  What happens next in this room?
                  </h2>
                  <div className="v11-prediction">
                    <strong>{fmt(d.forecast.thermal.eta_minutes)}  min</strong>
                    <span>until temperature and humidity reach target range</span>
                    <small>
                      {d.forecast.thermal.eligible
                        ? `Slower response estimate: ${fmt(d.forecast.thermal.upper_eta_minutes)} min`
                        : "Collecting samples; control uses the fallback preparation time."}
                    </small>
                  </div>
                  <div className="v11-traits">
                    {d.forecast.thermal.dimensions.map((x: Row) => (
                      <div key={x.dimension}>
                        <span>
                          {x.dimension === "temp_c" ? "Temperature" : "Humidity"}
                        </span>
                        <strong>{fmt(x.eta_minutes)}  min</strong>
                        <small>
                          {x.samples}  samples · {x.direction}
                        </small>
                      </div>
                    ))}
                  </div>
                  <ol className="v11-timeline">
                    {d.forecast.timeline.map((t: Row, i: number) => (
                      <li
                        key={t.case_id + t.stage + i}
                        className={t.stage.toLowerCase()}
                      >
                        <span className="v11-timeline-mark" />
                        <div>
                          <strong>{stageName[t.stage]}</strong>
                          <p>{t.case_label}</p>
                          <small>
                            {time(t.start)} → {time(t.end)}
                          </small>
                          {t.requires_actual_confirmation && (
                            <small>
                              
                              Planned time; real cases require confirmation to change lifecycle state.
                            </small>
                          )}
                        </div>
                      </li>
                    ))}
                    {!d.forecast.timeline.length && (
                      <li>No scheduled activity in the next 24 hours.</li>
                    )}
                  </ol>
                  <p className="hw-note">
                    
                    AI adjusts preparation lead time. Pressure interlocks and active-case conditions take priority; forecasts depend on actual loads.
                  </p>
                </section>
              </div>
              {current && (
                <section className="hw-panel">
                  <div className="hw-heading">
                    <h2>
                      <Activity size={19} />  Case outcome prediction
                    </h2>
                    <div className="v11-buttons">
                      {clinician && (
                        <>
                          <button
                            disabled={
                              !write ||
                              !["UNSCHEDULED", "SCHEDULED"].includes(c.status)
                            }
                            onClick={() => open("clinical", current)}
                          >
                            
                            Preoperative inputs
                          </button>
                          <button onClick={() => onView("models")}>
                            
                            Manage models
                          </button>
                          <button
                            disabled={!write}
                            onClick={() => onOpen("estimate", c)}
                          >
                            
                            Record clinician estimate
                          </button>
                          <button
                            disabled={
                              !write ||
                              current.clinical.predicted_success_percent ==
                                null ||
                              !["UNSCHEDULED", "SCHEDULED"].includes(c.status)
                            }
                            onClick={() =>
                              act({
                                action: "RUN_CASE_PREDICTION",
                                case_id: c.id,
                              })
                            }
                          >
                            
                            Save prediction record
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="v11-prognosis">
                    <Metric
                      label={d.demo?.active ? "Demo probability: no major complication within 30 days" : "No major complication within 30 days"}
                      value={
                        current.clinical.predicted_success_percent == null
                          ? "Not ready"
                          : `${fmt(current.clinical.predicted_success_percent)}%`
                      }
                      detail={current.clinical.prediction_status}
                    />
                    <div>
                      <p>{current.clinical.reason}</p>
                      {(current.clinical.recorded_predictions || [])
                        .slice(-3)
                        .map((prediction: Row) => (
                          <p key={prediction.id}>
                            
                            Recorded {time(prediction.at)}:{" "}
                            {fmt(prediction.predicted_success_percent)}% ·{" "}
                            {prediction.model_id} · {prediction.status}
                          </p>
                        ))}
                      {current.clinical.model_id && (
                        <p>
                          
                          Model: {current.clinical.model_id} ·{" "}
                          {current.clinical.model_version}
                        </p>
                      )}
                      {current.clinical.evaluation && (
                        <p>
                          AUC {fmt(current.clinical.evaluation.auc, 3)} · Brier{" "}
                          {fmt(current.clinical.evaluation.brier, 3)} ·{" "}
                          {current.clinical.evaluation.cases} evaluation cases
                        </p>
                      )}
                      {current.clinical.cohort && (
                        <p>
                          
                          {d.demo?.active ? "Synthetic cohort: " : "Same-procedure cohort: "}
                          {fmt(current.clinical.cohort.observed_rate_percent)}%
                          / {current.clinical.cohort.cases}  cases; this is an aggregate observed rate.
                        </p>
                      )}
                      {current.clinical.clinician_estimate && (
                        <p>
                          
                          Clinician estimate:{" "}
                          {fmt(current.clinical.clinician_estimate.percent)}% ·{" "}
                          {current.clinical.clinician_estimate.source}
                        </p>
                      )}
                    </div>
                  </div>
                </section>
              )}
              <section className="hw-panel">
                <div className="hw-heading">
                  <h2>
                    <Gauge size={19} />  Equipment & lifecycle
                  </h2>
                  {admin && (
                    <button
                      disabled={!write}
                      onClick={() => onOpen("devices", { room_id: r.id })}
                    >
                      
                      Add equipment
                    </button>
                  )}
                </div>
                <div className="hw-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Equipment</th>
                        <th>Service life</th>
                        <th>Measured performance / limit</th>
                        <th>Forecast to performance limit</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.devices.map((asset: Row) => (
                        <tr key={asset.id}>
                          <td>
                            <strong>{asset.name}</strong>
                            <small>
                              {asset.asset_tag} ·{" "}
                              {asset.ready ? "Ready" : "Action needed"}
                            </small>
                          </td>
                          <td>
                            {fmt(asset.remaining_life_hours, 0)}  hours remaining
                            <progress
                              max={100}
                              value={asset.remaining_life_percent}
                            />
                            <small>
                              {fmt(asset.remaining_life_percent)}% · Service due in{" "}
                              {fmt(asset.maintenance_in_hours)}  hours
                            </small>
                          </td>
                          <td>
                            {fmt(
                              asset.engineering.measured_performance_percent,
                            )}
                            % /{" "}
                            {fmt(asset.engineering.minimum_performance_percent)}
                            %
                            <small>
                              
                              Life × performance:{" "}
                              {fmt(
                                asset.engineering.life_x_performance_percent,
                              )}
                              %
                            </small>
                          </td>
                          <td>
                            {fmt(asset.engineering.performance_rul_hours, 0)}{" "}
                            
                            hours
                            <small>
                              {asset.engineering.trend_samples}  samples since last service
                            </small>
                          </td>
                          <td>
                            <div className="v11-buttons">
                              <button
                                onClick={() => open("asset-history", asset)}
                              >
                                
                                History
                              </button>
                              {admin && (
                                <>
                                  <button
                                    disabled={!write}
                                    onClick={() => open("engineering", asset)}
                                  >
                                    
                                    Engineering limits
                                  </button>
                                  <button
                                    disabled={!write}
                                    onClick={() => open("inspection", asset)}
                                  >
                                    
                                    Record inspection
                                  </button>
                                  <button
                                    disabled={!write}
                                    onClick={() => onOpen("service", asset)}
                                  >
                                    
                                    Service
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!d.devices.length && (
                        <tr>
                          <td colSpan={5}>
                            
                            No equipment is registered in this room.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="hw-note">
                  
                  Life × performance is an engineering indicator. Trend forecasts need at least 5 distinct runtime observations and an adequate fit; limits come from equipment specifications.
                </p>
              </section>
              <section className="hw-panel">
                <div className="hw-heading">
                  <h2>
                    <Zap size={19} />  Room investment performance
                  </h2>
                  <div className="v11-buttons">
                    <button onClick={() => onEnergy(r.id)}>
                      
                      Second / hour / day / month / year <ArrowRight size={16} />
                    </button>
                    {admin && (
                      <>
                        <button
                          disabled={!write}
                          onClick={() =>
                            open("finance", { id: r.id, ...d.room_finance })
                          }
                        >
                          
                          Allocate investment
                        </button>
                        <button
                          disabled={!write}
                          onClick={() => open("cost", r)}
                        >
                          
                          Record BMS cost
                        </button>
                      </>
                    )}
                  </div>
                </div>
                <div className="v11-metrics">
                  <Metric
                    label="Cumulative energy savings"
                    value={`${fmt(d.finance.saved_kwh, 3)} kWh`}
                    detail={`${fmt(d.finance.observed_seconds, 0)} observed seconds · ${d.finance.source}`}
                  />
                  <Metric
                    label="Net operating savings"
                    value={`${fmt(d.finance.net_operating_savings_vnd, 0)} ₫`}
                    detail={`Incremental costs: ${fmt(d.finance.service_cost_vnd, 0)} ₫`}
                  />
                  <Metric
                    label="ROI after investment"
                    value={
                      d.finance.roi_percent == null
                        ? "No capital allocated"
                        : `${fmt(d.finance.roi_percent)}%`
                    }
                    detail={`${fmt(d.finance.allocation_percent)}% of facility investment`}
                  />
                  <Metric
                    label="Projected payback"
                    value={
                      d.finance.projected_payback_years == null
                        ? "Insufficient data"
                        : `${fmt(d.finance.projected_payback_years, 2)} years`
                    }
                    detail="Requires at least 24 observed hours and positive cash flow"
                  />
                </div>
                <p className="hw-note">
                  
                  Baseline is a model reference. Missing readings remain gaps; ROI is not weather-normalized measurement and verification.
                </p>
              </section>
              <section className="hw-panel">
                <h2>Control acknowledgement</h2>
                {d.control.virtual_bms ? (
                  <p><strong>Virtual BMS active</strong> · The simulated room responds to {fmt(d.control.target_temp_c)} °C, {fmt(d.control.target_humidity)}% RH and {fmt(d.control.target_airflow_m3h, 0)} m³/h. Room readings update live as the controller approaches these targets.</p>
                ) : d.control.receipt ? (
                  <p>
                    {d.control.receipt.applied
                      ? "Gateway applied and read back the setpoints"
                      : "Gateway rejected application"}{" "}
                    · {time(d.control.receipt.at)} · {d.control.receipt.detail}
                  </p>
                ) : (
                  <p>
                    
                    No gateway receipt for this room. Displayed setpoints are BEAM control targets.
                  </p>
                )}
              </section>
            </>
          )}
        </div>
      </div>
      {modal && (
        <Modal
          title={
            {
              controls: "Room controls",
              finance: "Allocate CAPEX and OPEX",
              cost: "Incremental BMS cost",
              engineering: "Equipment lifecycle settings",
              inspection: "Record performance inspection",
              clinical: "Preoperative inputs",
              plan: "Proposed schedule",
              "asset-history": "Equipment history",
            }[modal.kind] || modal.kind
          }
          onClose={() => setModal(null)}
        >
          {notice && (
            <p role="status" className="v11-notice">
              {notice}
            </p>
          )}
          {modal.kind === "plan" ? (
            <>
              <p>
                
                Select up to 16 unscheduled cases. Proposals expire after 90 seconds; record or schedule changes require a new proposal.
              </p>
              <div className="v11-plan-cases">
                {pending.map((c) => (
                  <label className="hw-check" key={c.id}>
                    <input
                      type="checkbox"
                      checked={planCases.includes(c.id)}
                      onChange={(e) => {
                        setPlan(null);
                        setPlanCases((ids) =>
                          e.target.checked
                            ? [...ids, c.id].slice(0, 16)
                            : ids.filter((id) => id !== c.id),
                        );
                      }}
                    />
                    {c.case_label} · {c.procedure}
                  </label>
                ))}
                {!pending.length && (
                  <p>No unscheduled cases. Add a case in Surgical cases.</p>
                )}
              </div>
              <button
                disabled={!online || busy || !planCases.length}
                onClick={async () => {
                  const result = await act(
                    { action: "PREVIEW_SCHEDULE", case_ids: planCases },
                    false,
                  );
                  if (result.ok) setPlan(result.plan);
                }}
              >
                
                Calculate feasible schedule
              </button>
              {plan && (
                <>
                  <div className="v11-plan-results">
                    {plan.items.map((row: Row) => (
                      <p key={row.id}>
                        <strong>{row.case_label}</strong> ·{" "}
                        {allRooms.find((r) => r.id === row.scheduled_room_id)
                          ?.name || row.scheduled_room_id}
                        <br />
                        {time(row.scheduled_start)} → {time(row.scheduled_end)}
                      </p>
                    ))}
                    {plan.blocked.map((row: Row) => (
                      <p className="v11-warning" key={row.case_id}>
                        {row.case_id}: {row.reason}
                      </p>
                    ))}
                  </div>
                  <p>Expires: {time(plan.expires_at)}</p>
                  <button
                    className="hw-primary"
                    disabled={
                      !online ||
                      busy ||
                      !plan.items.length ||
                      Date.now() >= new Date(plan.expires_at).getTime()
                    }
                    onClick={() =>
                      act({ action: "APPLY_SCHEDULE_PLAN", plan_id: plan.id })
                    }
                  >
                    
                    Apply {plan.items.length}  cases in the proposal
                  </button>
                </>
              )}
            </>
          ) : modal.kind === "asset-history" ? (
            <>
              <p>
                {m.name}  · Fit R²: {fmt(m.engineering.trend?.r_squared, 3)}
              </p>
              <div className="hw-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Inspection time</th>
                      <th>Runtime hours</th>
                      <th>Performance</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.engineering.history.map((x: Row) => (
                      <tr key={x.id || x.at}>
                        <td>{time(x.at)}</td>
                        <td>{fmt(x.runtime_hours)}</td>
                        <td>{fmt(x.performance_percent)}%</td>
                        <td>{x.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>Service</h3>
              {m.service_history.map((x: Row, i: number) => (
                <p key={i}>
                  {time(x.at)} · {fmt(x.runtime_hours)}  hours · {x.notes}
                </p>
              ))}
            </>
          ) : (
            <form onSubmit={submit}>
              <div className="hw-form-grid">
                {modal.kind === "controls" && (
                  <>
                    <Input
                      name="temp_c"
                      label="Target temperature (°C)"
                      type="number"
                      min={18}
                      max={26}
                      value={m.target_temp_c}
                    />
                    <Input
                      name="humidity"
                      label="Target humidity (%RH)"
                      type="number"
                      min={45}
                      max={60}
                      value={m.target_humidity}
                    />
                    <Input
                      name="airflow_percent"
                      label="Airflow (% of design)"
                      type="number"
                      min={30}
                      max={100}
                      value={70}
                    />
                    <p>
                      
                      Manual control remains subject to safety interlocks. Select Schedule & AI to release manual targets.
                    </p>
                  </>
                )}
                {modal.kind === "finance" && (
                  <>
                    <Input
                      name="allocation_percent"
                      label="Facility CAPEX and OPEX allocated to this room (%)"
                      type="number"
                      min={0}
                      max={100}
                      value={m.allocation_percent}
                    />
                    <p>
                      
                      Room allocations total at most 100%; unallocated amounts remain in facility ROI.
                    </p>
                  </>
                )}
                {modal.kind === "cost" && (
                  <>
                    <Input
                      name="cost_vnd"
                      label="Incremental cost (VND)"
                      type="number"
                      min={0}
                    />
                    <Input
                      name="evidence"
                      label="Invoice / source; exclude costs already included in OPEX"
                      type="textarea"
                    />
                  </>
                )}
                {modal.kind === "engineering" && (
                  <>
                    <Input
                      name="minimum_performance_percent"
                      label="Minimum specified performance (%)"
                      type="number"
                      min={0}
                      max={100}
                      value={m.engineering.minimum_performance_percent ?? ""}
                    />
                    <Input
                      name="replacement_cost_vnd"
                      label="Estimated replacement cost (VND)"
                      type="number"
                      min={0}
                      value={m.engineering.replacement_cost_vnd}
                    />
                    <Input
                      name="retire_on"
                      label="Calendar retirement date (optional)"
                      type="datetime-local"
                      required={false}
                    />
                    <Input
                      name="evidence"
                      label="Specification source / manufacturer document"
                      type="textarea"
                    />
                  </>
                )}
                {modal.kind === "inspection" && (
                  <>
                    <Input
                      name="observed_at"
                      label="Observed time"
                      type="datetime-local"
                      value={localDate()}
                    />
                    <Input
                      name="runtime_hours"
                      label="Runtime at inspection"
                      type="number"
                      min={0}
                      max={m.runtime_hours}
                      value={m.runtime_hours}
                    />
                    <Input
                      name="performance_percent"
                      label="Measured performance (%)"
                      type="number"
                      min={0}
                      max={100}
                    />
                    <Input
                      name="evidence"
                      label="Measurement method / inspection report"
                      type="textarea"
                    />
                  </>
                )}
                {modal.kind === "clinical" && (
                  <>
                    <Input
                      name="observed_at"
                      label="Preoperative observation time"
                      type="datetime-local"
                      value={localDate(m.clinical_inputs?.observed_at)}
                    />
                    <Input
                      name="source"
                      label="Clinical record / laboratory source"
                      value={m.clinical_inputs?.source || ""}
                    />
                    {[
                      ["asa_class", "ASA (1–6)", 1, 6],
                      ["emergency", "Emergency case (0 or 1)", 0, 1],
                      ["bmi", "BMI (kg/m²)", 8, 100],
                      ["hemoglobin_g_dl", "Hemoglobin (g/dL)", 1, 30],
                      ["albumin_g_dl", "Albumin (g/dL)", 0.1, 10],
                      ["creatinine_mg_dl", "Creatinine (mg/dL)", 0.1, 30],
                    ].map(([key, label, min, max]) => (
                      <Input
                        key={key}
                        name={String(key)}
                        label={String(label)}
                        type="number"
                        min={Number(min)}
                        max={Number(max)}
                        required={false}
                        value={
                          m.clinical_inputs?.features?.[String(key)] ??
                          (key === "asa_class" ? m.patient?.asa_class : "") ??
                          ""
                        }
                      />
                    ))}
                    <p>
                      
                      Leave unavailable values blank; the engine reports missing inputs. Age comes from date of birth; preoperative observations remain valid for 72 hours.
                    </p>
                  </>
                )}
              </div>
              <div className="hw-footer">
                <button type="button" onClick={() => setModal(null)}>
                  
                  Close
                </button>
                <button className="hw-primary" type="submit" disabled={!write}>
                  {busy ? "Saving…" : "Save and synchronize"}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}
    </div>
  );
}
