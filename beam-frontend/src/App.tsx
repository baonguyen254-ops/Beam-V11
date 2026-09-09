import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import HospitalWorkspace from "./HospitalWorkspace";
import {api} from "./api";
import {
  Activity,
  AlertTriangle,
  Brain,
  CalendarClock,
  ChevronRight,
  CircleDot,
  Clock,
  DoorOpen,
  Gauge,
  Droplets,
  LayoutGrid,
  Lightbulb,
  Maximize2,
  Minimize2,
  Moon,
  Plus,
  RotateCcw,
  SlidersHorizontal,
  Sun,
  Power,
  Route,
  Settings,
  Thermometer,
  ToggleLeft,
  ToggleRight,
  UserRound,
  Wind,
  X,
  Zap,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";


type RoomStatus = "ACTIVE" | "SETBACK" | "PRECOOLING" | "ALARM";
type ConnectionState = "CONNECTING" | "LIVE" | "OFFLINE" | "STALE" | "MISMATCH";
type CaseStatus = "UNSCHEDULED" | "SCHEDULED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
type Urgency = "STAT" | "EMERGENCY" | "URGENT" | "ELECTIVE";
type FloorLayer = "STATUS" | "TEMPERATURE" | "HUMIDITY" | "ENERGY";
type AlarmSeverity = "NORMAL" | "ADVISORY" | "WARNING" | "CRITICAL";
type BeamTheme = "light" | "dark";
type FloorplanPresentation = "OVERVIEW" | "COMMAND_CENTER";
const FRONTEND_VERSION = "11.1.0";
const TELEMETRY_CONTRACT = "beam-final-v11";

interface RoomTrendPoint {
  time: string;
  temp_c: number;
  humidity: number;
  airflow_m3h: number;
  power_kw: number;
}

interface Room {
  id: string;
  name: string;
  source_name: string;
  category: string;
  area_m2: number;
  conditioned: boolean;
  capabilities: string[];
  status: RoomStatus;
  occupancy: number;
  surgeons: string[];
  power_kw: number;
  temp_c: number;
  humidity: number;
  airflow_m3h: number;
  max_airflow_m3h: number;
  max_airflow_source?: string;
  calibrated_min_airflow_m3h?: number;
  lighting_design_w_m2?: number;
  equipment_design_w_m2?: number;
  fan_design_kw?: number;
  fan_power_source?: string;
  design_people_capacity?: number;
  openstudio_space_calibration?: {
    matched?: boolean;
    zone_name?: string;
    space_type?: string;
    openstudio_conditioned?: boolean;
    calibration_method?: string;
    [key: string]: unknown;
  };
  damper_position: number;
  manual_mode: string | null;
  manual_targets: { temp_c: number; humidity: number; airflow_percent: number } | null;
  control_source: string;
  target_temp_c: number;
  target_humidity: number;
  target_airflow_m3h: number;
  active_case_id: string | null;
  telemetry_source: string;
  power_density_w_m2: number;
  session_utilization_percent: number;
  session_observed_seconds: number;
  alarm_severity: AlarmSeverity;
  alarm_reasons: string[];
  trend: RoomTrendPoint[];
}

interface FloorplanRoom {
  id: string;
  source_space_id: string;
  source_face_id: string;
  openstudio_handle: string | null;
  source_name: string;
  name: string;
  category: string;
  area_m2: number;
  polygon: [number, number][];
  centroid: [number, number];
  conditioned: boolean;
  capabilities: string[];
  capability_source: string | null;
}

interface FloorplanDoor {
  id: string;
  source_door_id: string;
  edge_id: string;
  point: [number, number];
  room_ids: string[];
}

interface FloorplanModel {
  story: {
    id: string;
    name: string;
    source_name: string;
    floor_to_ceiling_height_m: number;
    space_count: number;
  };
  bounds: { min_x: number; max_x: number; min_y: number; max_y: number };
  rooms: FloorplanRoom[];
  doors: FloorplanDoor[];
  adjacency: Record<string, string[]>;
  capability_source: string;
}

interface HISCase {
  id: string;
  case_label: string;
  source: "HIS_RANDOM" | "EXTERNAL";
  procedure: string;
  specialty: string;
  urgency: Urgency;
  estimated_duration_min: number;
  prep_minutes: number;
  recovery_minutes: number;
  created_at: string;
  latest_start_at: string;
  status: CaseStatus;
  scheduled_room_id: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  prep_room_id: string | null;
  recovery_room_id: string | null;
  constraint_reason: string | null;
  notes: string;
  priority_score: number;
  manual_action_required: boolean;
  eligible_room_ids: string[];
  circulation_path: string[];
}

interface HISState {
  generator: {
    enabled: boolean;
    mode: string;
    next_case_at: string;
    total_generated: number;
    total_external: number;
    bounded_live_case_limit: number;
  };
  scheduler: {
    autopilot: boolean;
    health: "HEALTHY" | "DEGRADED" | "CRITICAL";
    unscheduled_count: number;
    urgent_unscheduled_count: number;
    sla_risk_count: number;
    turnover_minutes: number;
    capability_source: string;
  };
  cases: HISCase[];
}

interface Controls {
  tempSetpoint: number;
  rhSetpoint: number;
  fanSpeed: number;
}

interface RoiPoint {
  time_label: string;
  beam_load_kw: number;
  baseline_kw: number;
}

interface EnergyMonthlyPoint {
  month: string;
  electricity_kwh: number | null;
  mean_kw: number | null;
  peak_kw: number | null;
  peak_timestamp?: string | null;
  cooling_mbtu: number | null;
  outdoor_temp_c: number | null;
}

interface EnergyEndUsePoint {
  end_use: string;
  kwh: number;
  peak_kw?: number;
}

interface EnergyBaselineProvenance {
  calibrated: boolean;
  source: string;
  calibration_tier: string;
  reference_resolution: string;
  floor_area_m2: number | null;
  conditioned_floor_area_m2: number | null;
  annual_site_energy_kwh: number | null;
  annual_electricity_kwh: number | null;
  annual_source_energy_kwh: number | null;
  site_eui_kwh_m2_year: number | null;
  source_eui_kwh_m2_year: number | null;
  conditioned_site_eui_kwh_m2_year: number | null;
  conditioned_source_eui_kwh_m2_year: number | null;
  annual_peak_electric_kw: number | null;
  annual_peak_timestamp?: string | null;
  simulation_hours?: number | null;
  has_hourly_profile: boolean;
  has_monthly_profile: boolean;
  control_eligible_end_use_fraction?: number | null;
  control_eligible_end_uses?: string[];
  monthly: EnergyMonthlyPoint[];
  end_uses_electricity: EnergyEndUsePoint[];
  monthly_end_use_electricity_kwh?: Record<string, number[]>;
  monthly_peak_end_use_kw?: Record<string, number[]>;
  hvac_design?: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

interface RoiState {
  total_kwh_saved: number;
  financial_savings_vnd: number;
  co2_reduction_kg: number;
  beam_load_kw: number;
  baseline_kw: number;
  modeled_controlled_load_kw: number;
  modeled_reference_load_kw: number;
  calibration_method: string;
  applied_control_delta_kw: number;
  raw_modeled_delta_kw: number;
  modeled_control_fraction: number;
  control_eligible_end_use_fraction: number | null;
  instant_savings_percent: number;
  peak_reduction_percent: number;
  total_beam_kwh: number;
  total_reference_kwh: number;
  session_seconds: number;
  conditioned_floor_area_m2: number;
  baseline_provenance: EnergyBaselineProvenance;
  history: RoiPoint[];
}

interface EnergyAIState {
  enabled: boolean;
  mode: string;
  status: string;
  score: number;
  last_evaluation: string | null;
  actions: Array<{ room_id: string; room: string; action: string; reason: string }>;
  estimated_avoided_kw: number;
  guardrails: string[];
}

interface PressureTrendPoint {
  time: string;
  delta_p_pa: number;
  target_delta_p_pa: number;
}

interface SterilityState {
  delta_p_pa: number;
  target_delta_p_pa: number;
  pressure_alarm: boolean;
  safety_threshold_pa: number;
  control_source: string;
  positive_pressure_policy: "STANDARD" | "ENHANCED";
  trend: PressureTrendPoint[];
}

interface IncidentEvent {
  id: string;
  timestamp: string;
  type: string;
  user: string;
  status: "INFO" | "ACTION" | "ALARM";
}

interface Notice {
  id: string;
  ok: boolean;
  message: string;
}

interface CommandResult {
  ok: boolean;
  message: string;
  command_id?: string;
  action?: string;
}

const EMPTY_HIS: HISState = {
  generator: { enabled: true, mode: "OS_ENTROPY_STOCHASTIC_STREAM", next_case_at: new Date().toISOString(), total_generated: 0, total_external: 0, bounded_live_case_limit: 320 },
  scheduler: { autopilot: true, health: "HEALTHY", unscheduled_count: 0, urgent_unscheduled_count: 0, sla_risk_count: 0, turnover_minutes: 18, capability_source: "BEAM_DEMO_CONFIG_NOT_OPENSTUDIO" },
  cases: [],
};

const EMPTY_ROI: RoiState = {
  total_kwh_saved: 0,
  financial_savings_vnd: 0,
  co2_reduction_kg: 0,
  beam_load_kw: 0,
  baseline_kw: 0,
  modeled_controlled_load_kw: 0,
  modeled_reference_load_kw: 0,
  calibration_method: "COUNTERFACTUAL_STANDARD_OPS_MODEL",
  applied_control_delta_kw: 0,
  raw_modeled_delta_kw: 0,
  modeled_control_fraction: 0,
  control_eligible_end_use_fraction: null,
  instant_savings_percent: 0,
  peak_reduction_percent: 0,
  total_beam_kwh: 0,
  total_reference_kwh: 0,
  session_seconds: 0,
  conditioned_floor_area_m2: 0,
  baseline_provenance: { calibrated: false, source: "COUNTERFACTUAL_STANDARD_OPS_MODEL", calibration_tier: "NONE", reference_resolution: "MODELED_ONLY", floor_area_m2: null, conditioned_floor_area_m2: null, annual_site_energy_kwh: null, annual_electricity_kwh: null, annual_source_energy_kwh: null, site_eui_kwh_m2_year: null, source_eui_kwh_m2_year: null, conditioned_site_eui_kwh_m2_year: null, conditioned_source_eui_kwh_m2_year: null, annual_peak_electric_kw: null, annual_peak_timestamp: null, simulation_hours: null, has_hourly_profile: false, has_monthly_profile: false, monthly: [], end_uses_electricity: [], metadata: {} },
  history: [],
};

const EMPTY_ENERGY_AI: EnergyAIState = {
  enabled: true,
  mode: "CONSTRAINT_AWARE_ENERGY_SUPERVISOR",
  status: "INITIALIZING",
  score: 100,
  last_evaluation: null,
  actions: [],
  estimated_avoided_kw: 0,
  guardrails: [],
};

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

const ROOM_MODES = [
  ["MAXIMUM_RUNNING", "Maximum Running"],
  ["BALANCE", "Auto / Balance"],
  ["MINIMUM_RUNNING", "Minimum Running"],
  ["SHUTDOWN", "Shutdown / Maintenance"],
] as const;

const statusStyle: Record<RoomStatus, { fill: string; stroke: string; label: string }> = {
  ACTIVE: { fill: "#7f1d1d", stroke: "#e11d48", label: "Active" },
  SETBACK: { fill: "#164e63", stroke: "#0891b2", label: "Setback" },
  PRECOOLING: { fill: "#4c1d95", stroke: "#7c3aed", label: "Pre-cooling" },
  ALARM: { fill: "#78350f", stroke: "#e11d48", label: "Alarm" },
};
const statusLightFill: Record<RoomStatus, string> = { ACTIVE: "#fff1f2", SETBACK: "#ecfeff", PRECOOLING: "#f5f3ff", ALARM: "#fff7ed" };

const clinicalCategories = new Set(["OPERATING_ROOM", "PREP", "RECOVERY", "PREOP", "CORRIDOR"]);

const alarmStroke: Record<AlarmSeverity, string> = {
  NORMAL: "#334155",
  ADVISORY: "#facc15",
  WARNING: "#fb923c",
  CRITICAL: "#fb7185",
};

const floorplanTheme = {
  light: {
    background: "#fbfdff", grid: "#e8eef5", supportFill: "#f5f8fc", voidFill: "#fbfdff", stairsFill: "#e8eef5",
    roomBoundary: "#7b8ba0", corridorBoundary: "#46566b", clinicalText: "#111827", supportText: "#475569", labelHalo: "#ffffff",
    selected: "#0369a1", route: "#7c3aed", routeOpacity: 0.52, routeGlow: false, alarmHalo: "#ffffff",
    occupancyBg: "#ffffff", occupancyBorder: "#cbd5e1", occupancyText: "#334155",
    liveBg: "#ecfdf5", liveBorder: "#059669", liveText: "#065f46", spark: "#0284c7",
  },
  dark: {
    background: "#020617", grid: "#0f2740", supportFill: "#0b1527", voidFill: "#020617", stairsFill: "#111827",
    roomBoundary: "#26364d", corridorBoundary: "#07111f", clinicalText: "#f8fafc", supportText: "#a8b3c7", labelHalo: "#020617",
    selected: "#f8fafc", route: "#e879f9", routeOpacity: 0.94, routeGlow: true, alarmHalo: "#020617",
    occupancyBg: "#020617", occupancyBorder: "#475569", occupancyText: "#f8fafc",
    liveBg: "#052e2b", liveBorder: "#34d399", liveText: "#d1fae5", spark: "#67e8f9",
  },
} as const;

function heatColor(layer: FloorLayer, live: Room | undefined, theme: BeamTheme): string {
  if (!live || !live.conditioned) return theme === "light" ? "#f5f8fc" : "#08111f";
  if (layer === "STATUS") return theme === "dark" ? statusStyle[live.status].fill : statusLightFill[live.status];
  if (layer === "TEMPERATURE") {
    const t = Math.max(0, Math.min(1, (live.temp_c - 18) / 8));
    const hue = 215 - 215 * t;
    return theme === "light"
      ? `hsl(${hue.toFixed(0)} 48% ${Math.round(94 - 7 * t)}%)`
      : `hsl(${hue.toFixed(0)} 72% ${Math.round(31 + 8 * t)}%)`;
  }
  if (layer === "HUMIDITY") {
    const t = Math.max(0, Math.min(1, (live.humidity - 35) / 30));
    const hue = 35 + 205 * t;
    return theme === "light"
      ? `hsl(${hue.toFixed(0)} 43% ${Math.round(94 - 6 * Math.abs(t - 0.5) * 2)}%)`
      : `hsl(${hue.toFixed(0)} 65% 34%)`;
  }
  const t = Math.max(0, Math.min(1, live.power_density_w_m2 / 160));
  const hue = 195 - 180 * t;
  return theme === "light"
    ? `hsl(${hue.toFixed(0)} 48% ${Math.round(94 - 8 * t)}%)`
    : `hsl(${hue.toFixed(0)} 78% ${Math.round(29 + 7 * t)}%)`;
}

function floorLayerLegend(layer: FloorLayer, theme: BeamTheme): { title: string; min: string; max: string; gradient: string } | null {
  if (layer === "STATUS") return null;
  const light = theme === "light";
  if (layer === "TEMPERATURE") return { title: "Temperature", min: "18°C", max: "26°C", gradient: light ? "linear-gradient(90deg,hsl(215 48% 94%),hsl(108 42% 91%),hsl(0 48% 87%))" : "linear-gradient(90deg,hsl(215 72% 31%),hsl(108 72% 35%),hsl(0 72% 39%))" };
  if (layer === "HUMIDITY") return { title: "Relative Humidity", min: "35%", max: "65%", gradient: light ? "linear-gradient(90deg,hsl(35 43% 90%),hsl(137 40% 94%),hsl(240 43% 90%))" : "linear-gradient(90deg,hsl(35 65% 34%),hsl(137 65% 34%),hsl(240 65% 34%))" };
  return { title: "Power Density", min: "0 W/m²", max: "160+ W/m²", gradient: light ? "linear-gradient(90deg,hsl(195 48% 94%),hsl(105 45% 91%),hsl(15 50% 86%))" : "linear-gradient(90deg,hsl(195 78% 29%),hsl(105 78% 33%),hsl(15 78% 36%))" };
}

function shortRoomLabel(room: FloorplanRoom): string {
  if (room.name.startsWith("Operating Room ")) return room.name.replace("Operating Room ", "OR ");
  if (room.name.startsWith("Preparation Room ")) return room.name.replace("Preparation Room ", "Prep ");
  if (room.name.startsWith("Corridor ")) return room.name.replace("Corridor ", "Corr. ");
  if (room.name === "Recovery Room") return "Recovery";
  if (room.name === "Pre-op Area") return "Pre-op";
  if (room.name.length > 20) return room.name.slice(0, 18) + "…";
  return room.name;
}

function prettyCategory(category: string): string {
  return category.toLowerCase().split("_").map((x) => x.charAt(0).toUpperCase() + x.slice(1)).join(" ");
}

function prettySpecialty(s: string): string {
  return s.toLowerCase().split("_").map((x) => x.charAt(0).toUpperCase() + x.slice(1)).join(" ");
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}

function localDateTimeInput(date: Date): string {
  const p = (n: number) => n.toString().padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
}

function makeCommandId(): string {
  // crypto.randomUUID is absent in some non-secure/LAN browser contexts. A
  // fallback keeps every control functional instead of throwing before ws.send.
  const cryptoObj = globalThis.crypto as Crypto | undefined;
  if (cryptoObj && typeof cryptoObj.randomUUID === "function") return cryptoObj.randomUUID();
  if (cryptoObj && typeof cryptoObj.getRandomValues === "function") {
    const bytes = new Uint32Array(4);
    cryptoObj.getRandomValues(bytes);
    return `cmd-${Date.now().toString(36)}-${Array.from(bytes).map((x) => x.toString(36)).join("")}`;
  }
  return `cmd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function wsUrl(): string {
  const configured = import.meta.env.VITE_BEAM_WS_URL as string | undefined;
  if (configured) return configured;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws`;
}

function App() {
  const [theme, setTheme] = useState<BeamTheme>(() => {
    try { return localStorage.getItem("beam-theme") === "dark" ? "dark" : "light"; } catch { return "light"; }
  });
  const [workspace, setWorkspace] = useState("rooms");
  const [systemMode, setSystemMode] = useState("SIMULATION");
  const liveRef = useRef<ConnectionState>("CONNECTING");
  const lastMessageRef = useRef(0);
  const [connection, setConnection] = useState<ConnectionState>("CONNECTING");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [floorplan, setFloorplan] = useState<FloorplanModel | null>(null);
  const [his, setHis] = useState<HISState>(EMPTY_HIS);
  const [autopilot, setAutopilot] = useState(true);
  const [emergencyMode, setEmergencyMode] = useState<string | null>(null);
  const [controls, setControls] = useState<Controls>({ tempSetpoint: 20, rhSetpoint: 50, fanSpeed: 70 });
  const [lightingLevel, setLightingLevel] = useState(70);
  const [sterility, setSterility] = useState<SterilityState>({ delta_p_pa: 3.2, target_delta_p_pa: 3.2, pressure_alarm: false, safety_threshold_pa: 2.5, control_source: "NORMAL", positive_pressure_policy: "STANDARD", trend: [] });
  const [roi, setRoi] = useState<RoiState>(EMPTY_ROI);
  const [energyAI, setEnergyAI] = useState<EnergyAIState>(EMPTY_ENERGY_AI);
  const [incidents, setIncidents] = useState<IncidentEvent[]>([]);
  const [serverTimestamp, setServerTimestamp] = useState<string>(new Date().toISOString());
  const [backendVersion, setBackendVersion] = useState<string | null>(null);
  const [backendContract, setBackendContract] = useState<string | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [showCirculation, setShowCirculation] = useState(true);
  const [showDoors, setShowDoors] = useState(false);
  const [floorLayer, setFloorLayer] = useState<FloorLayer>("STATUS");
  const [commandCenter, setCommandCenter] = useState(false);
  const [externalOpen, setExternalOpen] = useState(false);
  const [manualCase, setManualCase] = useState<HISCase | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number | null>(null);
  const retryCount = useRef(0);
  const pendingCommandsRef = useRef(new Map<string, { action: string; resolve: (result: CommandResult) => void; timer: number; payload: Record<string, unknown>; reconciling?: boolean }>());
  const [pendingActions, setPendingActions] = useState<Record<string, number>>({});
  const commandCenterNativeRef = useRef(false);

  useEffect(() => {
    document.documentElement.dataset.beamTheme = theme;
    document.body.dataset.beamTheme = theme;
    document.documentElement.style.colorScheme = theme;
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    themeMeta?.setAttribute("content", theme === "light" ? "#f4f7fb" : "#020617");
    try { localStorage.setItem("beam-theme", theme); } catch { /* privacy mode may block storage */ }
  }, [theme]);

  function settle(commandId: string, result: CommandResult) {
    const pending = pendingCommandsRef.current.get(commandId);
    if (!pending) return;
    window.clearTimeout(pending.timer); pendingCommandsRef.current.delete(commandId);
    setPendingActions(prev => { const next = {...prev}; next[pending.action] = Math.max(0,(next[pending.action] ?? 1)-1); return next; });
    setNotice({id: commandId, ok: result.ok, message: result.message}); pending.resolve(result);
  }
  async function reconcile(commandId: string) {
    const pending = pendingCommandsRef.current.get(commandId);
    if (!pending || pending.reconciling) return;
    pending.reconciling = true;
    try { const result = await api('/api/commands',pending.payload); settle(commandId,result); }
    catch(e) {settle(commandId,{ok:false,command_id:commandId,action:pending.action,message:`Command not confirmed ${commandId}: ${(e as Error).message}. Check the current data and audit log before submitting a new command.`});}
  }
  useEffect(() => {
    let cancelled = false;
    const status = (value: ConnectionState) => {liveRef.current=value;setConnection(value);};
    const connect = () => {
      if (cancelled) return;
      status("CONNECTING"); let lastRevision = -1;
      const ws = new WebSocket(wsUrl()); wsRef.current = ws;
      ws.onopen = () => { retryCount.current = 0; };
      ws.onmessage = event => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "STATE_INIT" || msg.type === "STATE_UPDATE") {
            const p = msg.payload;
            if (p?.system?.telemetry_contract !== TELEMETRY_CONTRACT || p?.system?.version !== FRONTEND_VERSION) {setBackendVersion(p?.system?.version ?? null);setBackendContract(p?.system?.telemetry_contract ?? null);status("MISMATCH");return;}
            if (!Array.isArray(p.rooms) || !p.his || !Array.isArray(p.his.cases) || !p.controls || !p.sterility || !p.roi || !p.energy_ai || !Number.isFinite(Date.parse(p.timestamp)) || !Number.isInteger(p.system.revision) || typeof p.autopilot !== 'boolean') {status("STALE");return;}
            if (p.system.revision < lastRevision) return;
            lastRevision = p.system.revision; lastMessageRef.current = performance.now(); status("LIVE");
            setSystemMode(p.system.mode);setServerTimestamp(p.timestamp);setBackendVersion(p.system.version);setBackendContract(p.system.telemetry_contract);
            setAutopilot(p.autopilot);setEmergencyMode(p.emergency_mode ?? null);setRooms(p.rooms);
            if (p.floorplan) setFloorplan(p.floorplan);
            setHis(p.his);setControls({tempSetpoint:p.controls.temp_setpoint,rhSetpoint:p.controls.rh_setpoint,fanSpeed:p.controls.fan_speed});
            if (p.lighting) setLightingLevel(p.lighting.level_percent);
            setSterility(p.sterility);setRoi(p.roi);setEnergyAI(p.energy_ai);setIncidents(p.incident_log ?? []);
          } else if (msg.type === "COMMAND_ACK" || msg.type === "COMMAND_REJECTED") {
            if (typeof msg.command_id === 'string') settle(msg.command_id,{...msg,ok:msg.type === 'COMMAND_ACK',message:msg.message ?? 'Command processed'});
          }
        } catch {status("STALE");}
      };
      ws.onerror = () => ws.close();
      ws.onclose = () => {
        if (cancelled) return;
        status("OFFLINE");
        for (const id of pendingCommandsRef.current.keys()) void reconcile(id);
        retryCount.current += 1;
        retryRef.current = window.setTimeout(connect, Math.min(12000,600*2**Math.min(5,retryCount.current)));
      };
    };
    connect();
    const watchdog = window.setInterval(() => {if (liveRef.current === 'LIVE' && performance.now()-lastMessageRef.current > 6000) status('STALE');},1000);
    return () => {
      cancelled=true;window.clearInterval(watchdog);
      if (retryRef.current !== null) window.clearTimeout(retryRef.current);
      wsRef.current?.close();
      for (const [id,pending] of pendingCommandsRef.current) {window.clearTimeout(pending.timer);pending.resolve({ok:false,command_id:id,message:'View closed; check audit before repeating the command.'});}
      pendingCommandsRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 4500);
    return () => window.clearTimeout(t);
  }, [notice]);

  useEffect(() => {
    if (!commandCenter) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.fullscreenElement) setCommandCenter(false);
    };
    const onFullscreenChange = () => {
      if (commandCenterNativeRef.current && !document.fullscreenElement) {
        commandCenterNativeRef.current = false;
        setCommandCenter(false);
      }
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
    };
  }, [commandCenter]);

  const sendCommand = (payload: Record<string, unknown>): Promise<CommandResult> => {
    const ws = wsRef.current; const action = String(payload.action ?? "UNKNOWN");
    if (!ws || ws.readyState !== WebSocket.OPEN || liveRef.current !== 'LIVE') {
      const result = {ok:false,message:"Live data is unavailable; the command has not been sent.",action};
      setNotice({id:`${Date.now()}`,ok:false,message:result.message});return Promise.resolve(result);
    }
    const commandId = makeCommandId(); const command = {...payload,command_id:commandId};
    return new Promise<CommandResult>(resolve => {
      const timer = window.setTimeout(() => {
        // No acknowledgement for ${action} within 8 seconds: reconcile the SAME ID over HTTP.
        void reconcile(commandId);
      },8000);
      pendingCommandsRef.current.set(commandId,{action,resolve,timer,payload:command});
      setPendingActions(prev => ({...prev,[action]:(prev[action] ?? 0)+1}));
      try {
        const encoded = JSON.stringify(command);
        if (new TextEncoder().encode(encoded).length > 60000) void reconcile(commandId);
        else ws.send(encoded);
      } catch {void reconcile(commandId);}
    });
  };

  const openCommandCenter = () => {
    setCommandCenter(true);
    const target = document.body;
    if (!document.fullscreenElement && typeof target.requestFullscreen === "function") {
      commandCenterNativeRef.current = true;
      void target.requestFullscreen({ navigationUI: "hide" }).catch((error) => {
        commandCenterNativeRef.current = false;
        console.warn("Command Center native fullscreen unavailable; using viewport takeover fallback.", error);
        setNotice({ id: `${Date.now()}`, ok: true, message: "Command Center opened in viewport takeover mode because native fullscreen is unavailable." });
      });
    }
  };

  const closeCommandCenter = () => {
    setCommandCenter(false);
    commandCenterNativeRef.current = false;
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch((error) => console.warn("Unable to exit fullscreen cleanly", error));
    }
  };

  const isPending = (action: string) => (pendingActions[action] ?? 0) > 0;

  const roomMap = useMemo(() => Object.fromEntries(rooms.map((r) => [r.id, r])), [rooms]);
  const selectedRoom = selectedRoomId ? roomMap[selectedRoomId] ?? null : null;
  const selectedCase = selectedCaseId ? his.cases.find((c) => c.id === selectedCaseId) ?? null : null;
  const activeFlowCase = selectedCase ?? his.cases.find((c) => c.status === "IN_PROGRESS") ?? his.cases.find((c) => c.status === "SCHEDULED") ?? null;
  const unscheduledCases = his.cases.filter((c) => c.status === "UNSCHEDULED").sort((a, b) => b.priority_score - a.priority_score);
  const upcomingCases = his.cases.filter((c) => ["SCHEDULED", "IN_PROGRESS"].includes(c.status)).sort((a, b) => new Date(a.scheduled_start ?? 0).getTime() - new Date(b.scheduled_start ?? 0).getTime());
  const nextCaseSeconds = Math.max(0, Math.floor((new Date(his.generator.next_case_at).getTime() - Date.now()) / 1000));
  const caseMap = useMemo(() => Object.fromEntries(his.cases.map((c) => [c.id, c])), [his.cases]);
  const roomAlarmSummary = useMemo(() => rooms.reduce((acc, room) => { acc[room.alarm_severity] = (acc[room.alarm_severity] ?? 0) + 1; return acc; }, {} as Record<AlarmSeverity, number>), [rooms]);

  return (
    <div className="beam-app min-h-screen bg-slate-950 text-slate-100" data-theme={theme}>
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-[2200px] flex-col items-stretch justify-between gap-2 px-3 py-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3 sm:px-4 sm:py-3 lg:px-6">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-emerald-400" />
              <h1 className="text-base font-semibold tracking-wide">B.E.A.M. Surgical Digital Twin</h1>
              <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[9px] font-mono text-slate-400">{`v${FRONTEND_VERSION.split(".")[0]}`}</span>
            </div>
            <p className="mt-0.5 text-[10px] text-slate-500">OpenStudio floorplan · live digital-twin telemetry · stochastic HIS · constraint-aware scheduling + energy AI</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <ConnectionBadge state={connection} />
            {roi.baseline_provenance.calibrated && (
              <div className="rounded-md border border-emerald-500/40 bg-emerald-500/5 px-2.5 py-1.5 font-mono text-emerald-300" title="Imported OpenStudio annual/monthly baseline provenance">
                OS {roi.baseline_provenance.calibration_tier.replace("_", "+")} · {roi.baseline_provenance.reference_resolution === "HOURLY" ? "Hourly" : roi.baseline_provenance.reference_resolution === "MONTHLY_MEAN" ? "Monthly mean" : "Annual"}
              </div>
            )}
            <div className="rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1.5 font-mono text-slate-400">
              {new Date(serverTimestamp).toLocaleString("en-GB", { hour12: false })}
            </div>
            <button
              type="button"
              disabled={connection !== "LIVE" || isPending("TOGGLE_AUTOPILOT")}
              onClick={() => { void sendCommand({ action: "TOGGLE_AUTOPILOT", value: !autopilot }); }}
              className={`flex items-center gap-2 rounded-md border px-3 py-1.5 font-medium disabled:cursor-not-allowed disabled:opacity-50 ${autopilot ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300" : "border-rose-500/70 bg-rose-500/10 text-rose-300"}`}
            >
              {autopilot ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
              {isPending("TOGGLE_AUTOPILOT") ? "Scheduler…" : `AI Scheduler ${autopilot ? "ON" : "OFF"}`}
            </button>
            <button
              type="button"
              disabled={connection !== "LIVE" || isPending("TOGGLE_ENERGY_AI")}
              onClick={() => { void sendCommand({ action: "TOGGLE_ENERGY_AI", value: !energyAI.enabled }); }}
              className={`flex items-center gap-2 rounded-md border px-3 py-1.5 font-medium disabled:cursor-not-allowed disabled:opacity-50 ${energyAI.enabled ? "border-violet-500/60 bg-violet-500/10 text-violet-200" : "border-slate-700 bg-slate-900 text-slate-400"}`}
              title="Constraint-aware room/HVAC energy supervisor. Safety and manual overrides remain higher priority."
            >
              <Brain className="h-4 w-4" />
              {isPending("TOGGLE_ENERGY_AI") ? "Energy AI…" : `Energy AI ${energyAI.enabled ? "ON" : "OFF"}`}
            </button>
            <button
              type="button"
              onClick={() => setTheme((current) => current === "light" ? "dark" : "light")}
              className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 font-medium text-slate-300 hover:border-cyan-500/40"
              title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            >
              {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              <span className="hidden sm:inline">{theme === "light" ? "Dark" : "Light"}</span>
            </button>
            <button
              type="button"
              onClick={openCommandCenter}
              className="flex items-center gap-2 rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 font-medium text-cyan-200 hover:bg-cyan-500/15"
              title="Open Command Center and request native fullscreen"
            >
              <Maximize2 className="h-4 w-4" /><span className="hidden sm:inline">Command Center</span><span className="sm:hidden">CC</span>
            </button>
          </div>
        </div>
      </header>

      {connection === "MISMATCH" && (
        <div className="border-b border-rose-500/70 bg-rose-950/80 px-4 py-2 text-xs text-rose-100">
          <div className="mx-auto flex max-w-[2200px] items-center gap-2"><AlertTriangle className="h-4 w-4"/><strong>VERSION MISMATCH:</strong><span>Frontend {FRONTEND_VERSION}/{TELEMETRY_CONTRACT} is connected to backend {backendVersion ?? "unknown"}/{backendContract ?? "unknown"}. Run the matched v11 backend and hard-refresh the browser. Controls remain locked until versions match.</span></div>
        </div>
      )}

      {his.scheduler.health === "CRITICAL" && (
        <div className="border-b border-rose-500/60 bg-rose-950/75 px-4 py-2 text-xs text-rose-200">
          <div className="mx-auto flex max-w-[2200px] items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <strong>MANUAL HIS ACTION REQUIRED:</strong>
            <span>{his.scheduler.urgent_unscheduled_count} urgent case(s) are waiting for OR allocation while AI scheduling is disabled.</span>
          </div>
        </div>
      )}

      {notice && createPortal(
        <div className={`fixed right-4 top-20 z-[400] max-w-md rounded-lg border px-4 py-3 text-xs shadow-2xl ${notice.ok ? "border-emerald-500/70 bg-emerald-950 text-emerald-100" : "border-rose-500/70 bg-rose-950 text-rose-100"}`}>
          {notice.message}
        </div>, document.fullscreenElement ?? document.body
      )}

      <HospitalWorkspace view={workspace} onView={setWorkspace} rooms={rooms} cases={his.cases} sendCommand={sendCommand} online={connection === "LIVE"} mode={systemMode} />
      {workspace === "operations" && <main className="mx-auto max-w-[2200px] space-y-3 px-2 py-3 sm:px-4 sm:py-4 lg:px-6">
        <section className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div className="xl:col-span-8 rounded-xl border border-slate-800 bg-slate-900/65 p-2 sm:p-3 shadow-xl shadow-black/20">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <LayoutGrid className="h-4 w-4 text-cyan-400" />
                <div>
                  <h2 className="text-sm font-semibold">OpenStudio Surgical Floorplan</h2>
                  <p className="text-[10px] text-slate-500">Adaptive zoom labels · collision-aware telemetry · click any space for controls</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                <div className="flex overflow-hidden rounded border border-slate-700 bg-slate-950/60" title="Floorplan visualization layer">
                  {(["STATUS", "TEMPERATURE", "HUMIDITY", "ENERGY"] as FloorLayer[]).map((layer) => (
                    <button key={layer} type="button" onClick={() => setFloorLayer(layer)} className={`px-2 py-1 ${floorLayer === layer ? "bg-cyan-500/15 text-cyan-200" : "text-slate-500 hover:text-slate-300"}`}>{layer === "TEMPERATURE" ? "Temp" : layer === "HUMIDITY" ? "RH" : layer === "ENERGY" ? "Energy" : "Status"}</button>
                  ))}
                </div>
                <button type="button" onClick={() => setShowDoors((v) => !v)} className={`flex items-center gap-1 rounded border px-2 py-1 ${showDoors ? "border-cyan-500/60 text-cyan-300" : "border-slate-700 text-slate-400"}`}>
                  <DoorOpen className="h-3 w-3" /> Doors
                </button>
                <button type="button" onClick={() => setShowCirculation((v) => !v)} className={`flex items-center gap-1 rounded border px-2 py-1 ${showCirculation ? "border-violet-500/60 text-violet-300" : "border-slate-700 text-slate-400"}`}>
                  <Route className="h-3 w-3" /> Clinical Flow
                </button>
              </div>
            </div>

            {floorplan ? (
              <FloorplanTwin
                floorplan={floorplan}
                rooms={roomMap}
                selectedRoomId={selectedRoomId}
                selectedCase={activeFlowCase}
                showDoors={showDoors}
                showCirculation={showCirculation}
                layer={floorLayer}
                cases={caseMap}
                presentation="OVERVIEW"
                theme={theme}
                onSelectRoom={(id) => setSelectedRoomId(id)}
              />
            ) : (
              <div className="flex h-[560px] items-center justify-center rounded-lg border border-dashed border-slate-700 text-sm text-slate-500">Waiting for floorplan geometry from backend…</div>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-slate-400">
              {floorLayer === "STATUS" ? (["ACTIVE", "PRECOOLING", "SETBACK", "ALARM"] as RoomStatus[]).map((status) => (
                <div key={status} className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: theme === "light" ? statusLightFill[status] : statusStyle[status].fill, border: `1px solid ${statusStyle[status].stroke}` }} />
                  {statusStyle[status].label}
                </div>
              )) : (() => { const legend = floorLayerLegend(floorLayer, theme); return legend ? <div className="flex min-w-[240px] items-center gap-2"><span>{legend.title}</span><span>{legend.min}</span><span className="h-2 w-28 rounded-full border border-slate-700" style={{background: legend.gradient}}/><span>{legend.max}</span></div> : null; })()}
              <div className="flex flex-wrap items-center gap-2"><span className="text-yellow-300">● {roomAlarmSummary.ADVISORY ?? 0} advisory</span><span className="text-orange-300">● {roomAlarmSummary.WARNING ?? 0} warning</span><span className="text-rose-300">● {roomAlarmSummary.CRITICAL ?? 0} critical</span></div>
              <span className="ml-auto">{floorplan?.story.space_count ?? 0} spaces · {floorplan?.doors.length ?? 0} doors · {rooms.filter((r) => r.category === "OPERATING_ROOM").length} ORs</span>
            </div>
          </div>

          <div className="xl:col-span-4">
            <HISPanel
              his={his}
              rooms={roomMap}
              autopilot={autopilot}
              nextCaseSeconds={nextCaseSeconds}
              unscheduled={unscheduledCases}
              upcoming={upcomingCases}
              selectedCaseId={selectedCaseId}
              onSelectCase={(id) => setSelectedCaseId(id)}
              onAddExternal={() => setExternalOpen(true)}
              onManualSchedule={(c) => setManualCase(c)}
            />
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <ControlPanel
            className="lg:col-span-6"
            controls={controls}
            lightingLevel={lightingLevel}
            rooms={rooms}
            energyAI={energyAI}
            pending={isPending}
            onProfile={(profile) => { void sendCommand({ action: "APPLY_CONTROL_PROFILE", profile }); }}
            onControl={(field, value) => {
              const action = field === "tempSetpoint" ? "SET_TEMPERATURE_SETPOINT" : field === "rhSetpoint" ? "SET_HUMIDITY_SETPOINT" : "SET_FAN_SPEED";
              void sendCommand({ action, value });
            }}
            onLighting={(value) => { void sendCommand({ action: "SET_LIGHTING", value }); }}
          />

          <SterilityPanel
            className="lg:col-span-6"
            sterility={sterility}
            emergencyMode={emergencyMode}
            rooms={rooms}
            pending={isPending}
            onCommand={(payload) => { void sendCommand(payload); }}
          />

        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <EnergyPanel className="lg:col-span-8" roi={roi} />
          <div className="lg:col-span-4"><EnergyAISupervisorPanel state={energyAI} /></div>
        </section>

        <AuditPanel incidents={incidents} />
      </main>}

      {commandCenter && floorplan && (
        <CommandCenterView
          floorplan={floorplan}
          rooms={roomMap}
          his={his}
          roi={roi}
          energyAI={energyAI}
          autopilot={autopilot}
          nextCaseSeconds={nextCaseSeconds}
          cases={caseMap}
          layer={floorLayer}
          showDoors={showDoors}
          showCirculation={showCirculation}
          selectedRoomId={selectedRoomId}
          selectedCase={activeFlowCase}
          controls={controls}
          lightingLevel={lightingLevel}
          sterility={sterility}
          emergencyMode={emergencyMode}
          pending={isPending}
          onLayer={setFloorLayer}
          onSelectRoom={setSelectedRoomId}
          onSelectCase={setSelectedCaseId}
          onAddExternal={() => setExternalOpen(true)}
          onManualSchedule={(c) => setManualCase(c)}
          onToggleDoors={() => setShowDoors((v) => !v)}
          onToggleFlow={() => setShowCirculation((v) => !v)}
          onProfile={(profile) => { void sendCommand({ action: "APPLY_CONTROL_PROFILE", profile }); }}
          onControl={(field, value) => {
            const action = field === "tempSetpoint" ? "SET_TEMPERATURE_SETPOINT" : field === "rhSetpoint" ? "SET_HUMIDITY_SETPOINT" : "SET_FAN_SPEED";
            void sendCommand({ action, value });
          }}
          onLighting={(value) => { void sendCommand({ action: "SET_LIGHTING", value }); }}
          onSterilityCommand={(payload) => { void sendCommand(payload); }}
          onClose={closeCommandCenter}
          theme={theme}
        />
      )}

      {selectedRoom && (
        <RoomControlModal
          room={selectedRoom}
          onClose={() => setSelectedRoomId(null)}
          modePending={isPending("SET_ROOM_MODE")}
          targetsPending={isPending("SET_ROOM_MANUAL_TARGETS") || isPending("RESET_ROOM_MANUAL_TARGETS")}
          onMode={(mode) => { void sendCommand({ action: "SET_ROOM_MODE", room_id: selectedRoom.id, mode }); }}
          onTargets={(targets) => sendCommand({ action: "SET_ROOM_MANUAL_TARGETS", room_id: selectedRoom.id, ...targets })}
          onResetTargets={() => sendCommand({ action: "RESET_ROOM_MANUAL_TARGETS", room_id: selectedRoom.id })}
        />
      )}

      {externalOpen && (
        <ExternalCaseModal
          onClose={() => setExternalOpen(false)}
          pending={isPending("ADD_EXTERNAL_CASE")}
          onSubmit={async (payload) => {
            const result = await sendCommand({ action: "ADD_EXTERNAL_CASE", ...payload });
            if (result.ok) setExternalOpen(false);
          }}
        />
      )}

      {manualCase && (
        <ManualScheduleModal
          caseItem={his.cases.find(c => c.id === manualCase.id) ?? manualCase}
          rooms={roomMap}
          onClose={() => setManualCase(null)}
          pending={isPending("MANUAL_SCHEDULE_CASE")}
          onSubmit={async (roomId, start) => {
            const result = await sendCommand({ action: "MANUAL_SCHEDULE_CASE", case_id: manualCase.id, room_id: roomId, start: new Date(start).toISOString() });
            if (result.ok) setManualCase(null);
          }}
        />
      )}
    </div>
  );
}

function ConnectionBadge({ state }: { state: ConnectionState }) {
  const cls = state === "LIVE" ? "border-emerald-500/60 text-emerald-300" : state === "CONNECTING" ? "border-amber-500/60 text-amber-300" : "border-rose-500/60 text-rose-300";
  return (
    <div className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 ${cls}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {state === "LIVE" ? "Live backend" : state === "CONNECTING" ? "Connecting" : state === "STALE" ? "Stale telemetry · controls locked" : state === "MISMATCH" ? "Version mismatch · reload required" : "Offline / retrying"}
    </div>
  );
}

interface FloorplanTwinProps {
  floorplan: FloorplanModel;
  rooms: Record<string, Room>;
  cases: Record<string, HISCase>;
  layer: FloorLayer;
  selectedRoomId: string | null;
  selectedCase: HISCase | null;
  showDoors: boolean;
  showCirculation: boolean;
  presentation: FloorplanPresentation;
  theme: BeamTheme;
  onSelectRoom: (id: string) => void;
}

function compactSupportLabel(name: string): string {
  return name
    .replace("Female Doctors' Changing Room", "Female Dr. Change")
    .replace("Male Doctors' Changing Room", "Male Dr. Change")
    .replace("Female Doctors' Room", "Female Dr. Room")
    .replace("Male Doctors' Room", "Male Dr. Room")
    .replace("Doctors' Room", "Dr. Room")
    .replace("Equipment Room", "Equip.")
    .replace("Nurse Station", "Nurse Stn.")
    .replace("Sterilization Room", "Sterile")
    .replace("Clean Wash Room", "Clean Wash")
    .replace("Restroom", "WC");
}

function wrapLabel(text: string, maxChars: number, maxLines = 2): string[] {
  if (text.length <= maxChars) return [text];
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length <= maxChars || !line) {
      line = candidate;
    } else {
      lines.push(line);
      line = word;
      if (lines.length === maxLines - 1) break;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  const consumed = lines.join(" ").length;
  if (consumed < text.length - 1 && lines.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, Math.max(3, maxChars - 1))}…`;
  }
  return lines.slice(0, maxLines);
}

function floorplanLabelPriority(room: FloorplanRoom, selected: boolean, inRoute: boolean): number {
  if (selected) return 1000;
  if (inRoute) return 900;
  const priority: Record<string, number> = {
    OPERATING_ROOM: 800,
    RECOVERY: 760,
    PREOP: 750,
    PREP: 740,
    CORRIDOR: 640,
    SCRUB: 520,
    STERILIZATION: 510,
    NURSE_STATION: 440,
    CONTROL: 430,
    EQUIPMENT: 420,
    DOCTORS: 330,
    STAFF: 300,
    MEETING: 270,
    OFFICE: 260,
    STORAGE: 210,
    TOILET: 180,
    STAIRS: 130,
    SUPPORT: 120,
    VOID: 0,
  };
  return (priority[room.category] ?? 100) + Math.min(80, room.area_m2 / 4);
}

function formatFloorplanFlow(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${Math.round(value)}`;
}

function boxesOverlap(a: { x1: number; y1: number; x2: number; y2: number }, b: { x1: number; y1: number; x2: number; y2: number }, pad: number): boolean {
  return !(a.x2 + pad < b.x1 || a.x1 - pad > b.x2 || a.y2 + pad < b.y1 || a.y1 - pad > b.y2);
}

function pointInPolygon(point: [number, number], polygon: [number, number][]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]; const [xj, yj] = polygon[j];
    const intersect = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / Math.max(1e-9, (yj - yi)) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function pointSegmentDistance(point: [number, number], a: [number, number], b: [number, number]): number {
  const [px, py] = point; const [ax, ay] = a; const [bx, by] = b;
  const dx = bx - ax; const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  if (len2 <= 1e-12) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function polygonClearance(point: [number, number], polygon: [number, number][]): number {
  if (!pointInPolygon(point, polygon)) return -1;
  let best = Number.POSITIVE_INFINITY;
  for (let i = 0; i < polygon.length; i++) best = Math.min(best, pointSegmentDistance(point, polygon[i], polygon[(i + 1) % polygon.length]));
  return best;
}

function interiorLabelPoint(room: FloorplanRoom): [number, number] {
  const polygon = room.polygon;
  if (polygon.length < 3) return room.centroid;
  const xs = polygon.map((p) => p[0]); const ys = polygon.map((p) => p[1]);
  const bounds = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
  let best: [number, number] = pointInPolygon(room.centroid, polygon) ? room.centroid : [(bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2];
  let bestScore = polygonClearance(best, polygon);
  // Coarse-to-fine point-on-surface search. This is intentionally computed from
  // the true polygon, so concave corridor names cannot drift into another room.
  let minX = bounds.minX; let maxX = bounds.maxX; let minY = bounds.minY; let maxY = bounds.maxY;
  for (let round = 0; round < 4; round++) {
    const steps = round === 0 ? 18 : 10;
    for (let ix = 0; ix <= steps; ix++) for (let iy = 0; iy <= steps; iy++) {
      const candidate: [number, number] = [minX + (ix / steps) * (maxX - minX), minY + (iy / steps) * (maxY - minY)];
      const score = polygonClearance(candidate, polygon);
      if (score > bestScore) { best = candidate; bestScore = score; }
    }
    const spanX = Math.max(0.05, (maxX - minX) / 4); const spanY = Math.max(0.05, (maxY - minY) / 4);
    minX = best[0] - spanX / 2; maxX = best[0] + spanX / 2; minY = best[1] - spanY / 2; maxY = best[1] + spanY / 2;
  }
  return bestScore >= 0 ? best : room.centroid;
}

function sparklinePoints(values: number[], x: number, y: number, w: number, h: number): string {
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(0.001, max - min);
  return values.map((value, index) => {
    const px = x + (index / Math.max(1, values.length - 1)) * w;
    const py = y + h - ((value - min) / range) * h;
    return `${px.toFixed(3)},${py.toFixed(3)}`;
  }).join(" ");
}

function MiniSparkline({ points, field, className = "" }: { points: RoomTrendPoint[]; field: keyof Pick<RoomTrendPoint, "temp_c" | "humidity" | "airflow_m3h" | "power_kw">; className?: string }) {
  if (points.length < 2) return <div className={`h-8 rounded border border-slate-800 bg-slate-950/50 ${className}`} />;
  const values = points.map((p) => Number(p[field]));
  const poly = sparklinePoints(values, 1, 1, 98, 28);
  return <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={`h-8 w-full overflow-visible ${className}`} aria-label={`${field} trend`}><polyline points={poly} fill="none" stroke="currentColor" strokeWidth="1.6" vectorEffect="non-scaling-stroke" /></svg>;
}

function FloorplanTwin({ floorplan, rooms, cases, layer, selectedRoomId, selectedCase, showDoors, showCirculation, presentation, theme, onSelectRoom }: FloorplanTwinProps) {
  const { min_x, max_x, min_y, max_y } = floorplan.bounds;
  const width = max_x - min_x;
  const height = max_y - min_y;
  const pad = 2.2;
  const baseX = -pad;
  const baseY = -pad;
  const baseWidth = width + pad * 2;
  const baseHeight = height + pad * 2;
  const tx = (x: number) => x - min_x;
  const ty = (y: number) => max_y - y;
  const modelRoomMap = useMemo(() => Object.fromEntries(floorplan.rooms.map((r) => [r.id, r])), [floorplan.rooms]);
  const labelAnchorMap = useMemo(() => Object.fromEntries(floorplan.rooms.map((room) => [room.id, interiorLabelPoint(room)])), [floorplan.rooms]);
  const activePath = showCirculation && selectedCase ? selectedCase.circulation_path : [];
  const activePathSet = useMemo(() => new Set(activePath), [activePath]);
  const selectedModelRoom = selectedRoomId ? modelRoomMap[selectedRoomId] ?? null : null;
  const selectedLiveRoom = selectedRoomId ? rooms[selectedRoomId] ?? null : null;
  const viz = floorplanTheme[theme];
  // Corridors are painted first, then enclosed rooms, so a corridor fill can
  // never visually wash over a room even if source geometry shares boundaries.
  const renderRooms = useMemo(
    () => [...floorplan.rooms].sort((a, b) => Number(a.category !== "CORRIDOR") - Number(b.category !== "CORRIDOR")),
    [floorplan.rooms],
  );

  const shellRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pseudoFullscreen, setPseudoFullscreen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState({ x: baseX + baseWidth / 2, y: baseY + baseHeight / 2 });
  const dragRef = useRef<{ pointerId: number; x: number; y: number; centerX: number; centerY: number; moved: boolean; roomId: string | null } | null>(null);
  const pinchRef = useRef<{ distance: number; zoom: number } | null>(null);
  const touchPointsRef = useRef<Map<number, { x: number; y: number }>>(new Map());

  useEffect(() => {
    setZoom(1);
    setCenter({ x: baseX + baseWidth / 2, y: baseY + baseHeight / 2 });
  }, [baseX, baseY, baseWidth, baseHeight]);

  useEffect(() => {
    const sync = () => setIsFullscreen(document.fullscreenElement === shellRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && pseudoFullscreen) {
        setPseudoFullscreen(false);
        document.body.style.overflow = "";
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [pseudoFullscreen]);

  const clampZoom = (value: number) => Math.max(1, Math.min(6, value));
  const viewWidth = baseWidth / zoom;
  const viewHeight = baseHeight / zoom;
  const minCenterX = baseX + viewWidth / 2;
  const maxCenterX = baseX + baseWidth - viewWidth / 2;
  const minCenterY = baseY + viewHeight / 2;
  const maxCenterY = baseY + baseHeight - viewHeight / 2;
  const clampedCenter = {
    x: Math.max(minCenterX, Math.min(maxCenterX, center.x)),
    y: Math.max(minCenterY, Math.min(maxCenterY, center.y)),
  };
  const view = { x: clampedCenter.x - viewWidth / 2, y: clampedCenter.y - viewHeight / 2, w: viewWidth, h: viewHeight };

  const setZoomAt = (nextZoomRaw: number, anchor?: { x: number; y: number }) => {
    const nextZoom = clampZoom(nextZoomRaw);
    if (Math.abs(nextZoom - zoom) < 0.001) return;
    const oldView = view;
    const newW = baseWidth / nextZoom;
    const newH = baseHeight / nextZoom;
    let nextCenter = { ...clampedCenter };
    if (anchor) {
      const rx = (anchor.x - oldView.x) / oldView.w;
      const ry = (anchor.y - oldView.y) / oldView.h;
      const newX = anchor.x - rx * newW;
      const newY = anchor.y - ry * newH;
      nextCenter = { x: newX + newW / 2, y: newY + newH / 2 };
    }
    const nextMinX = baseX + newW / 2;
    const nextMaxX = baseX + baseWidth - newW / 2;
    const nextMinY = baseY + newH / 2;
    const nextMaxY = baseY + baseHeight - newH / 2;
    setCenter({ x: Math.max(nextMinX, Math.min(nextMaxX, nextCenter.x)), y: Math.max(nextMinY, Math.min(nextMaxY, nextCenter.y)) });
    setZoom(nextZoom);
  };

  const fit = () => {
    setZoom(1);
    setCenter({ x: baseX + baseWidth / 2, y: baseY + baseHeight / 2 });
  };

  const toggleFullscreen = async () => {
    try {
      if (pseudoFullscreen) {
        setPseudoFullscreen(false);
        document.body.style.overflow = "";
        return;
      }
      if (document.fullscreenElement === shellRef.current) {
        await document.exitFullscreen();
      } else if (shellRef.current?.requestFullscreen) {
        await shellRef.current.requestFullscreen({ navigationUI: "hide" });
        fit();
      } else {
        // iOS/embedded-browser fallback: emulate a true viewport takeover.
        setPseudoFullscreen(true);
        document.body.style.overflow = "hidden";
        fit();
      }
    } catch (error) {
      console.error("Fullscreen request failed", error);
      setPseudoFullscreen(true);
      document.body.style.overflow = "hidden";
    }
  };

  const pairDoor = (a: string, b: string) => floorplan.doors.find((d) => d.room_ids.length === 2 && d.room_ids.includes(a) && d.room_ids.includes(b));
  const detail = zoom < 1.35 ? 0 : zoom < 2.1 ? 1 : zoom < 3.2 ? 2 : 3;

  const labels = useMemo(() => {
    const candidates = floorplan.rooms.map((modelRoom) => {
      const live = rooms[modelRoom.id];
      const isClinical = clinicalCategories.has(modelRoom.category);
      const isSelected = selectedRoomId === modelRoom.id;
      const inRoute = activePathSet.has(modelRoom.id);
      const priority = floorplanLabelPriority(modelRoom, isSelected, inRoute);
      const visible = isSelected || (presentation === "OVERVIEW"
        ? modelRoom.category !== "VOID"
        : (detail === 0 ? ["OPERATING_ROOM", "RECOVERY", "PREOP", "PREP", "CORRIDOR"].includes(modelRoom.category) :
          detail === 1 ? (isClinical || modelRoom.area_m2 >= 35) :
            detail === 2 ? (modelRoom.category !== "VOID" && modelRoom.area_m2 >= 10) : modelRoom.category !== "VOID"));
      if (!visible) return null;
      const fullName = presentation === "OVERVIEW" ? false : (isSelected || detail >= 3);
      const text = fullName ? modelRoom.name : (isClinical ? shortRoomLabel(modelRoom) : compactSupportLabel(modelRoom.name));
      const maxChars = Math.max(7, Math.min(24, Math.floor(Math.sqrt(Math.max(4, modelRoom.area_m2)) * (1.35 + zoom * 0.18))));
      const lines = wrapLabel(text, maxChars, detail >= 2 ? 2 : 1);
      const baseFont = presentation === "OVERVIEW" ? (isClinical ? 1.16 : 0.86) : (isClinical ? 1.05 : 0.78);
      const fontSize = baseFont / zoom;
      const telemetry = Boolean(presentation === "COMMAND_CENTER" && live && isClinical && (detail >= 1 || isSelected) && modelRoom.area_m2 >= (detail >= 2 ? 8 : 20));
      const telemetrySize = 0.64 / zoom;
      const anchor = labelAnchorMap[modelRoom.id] ?? modelRoom.centroid;
      const x = tx(anchor[0]);
      const y = ty(anchor[1]);
      const maxLen = Math.max(...lines.map((line) => line.length), 4);
      const boxWidth = Math.max(2.0 / zoom, maxLen * fontSize * 0.56, telemetry ? 9.2 / zoom : 0);
      const boxHeight = lines.length * fontSize * 1.12 + (telemetry ? telemetrySize * 1.55 : 0);
      return { id: modelRoom.id, live, modelRoom, isClinical, isSelected, inRoute, priority, x, y, lines, fontSize, telemetry, telemetrySize, box: { x1: x - boxWidth / 2, x2: x + boxWidth / 2, y1: y - boxHeight / 2, y2: y + boxHeight / 2 } };
    }).filter(Boolean) as Array<any>;
    candidates.sort((a, b) => b.priority - a.priority);
    const accepted: typeof candidates = [];
    const padding = 0.28 / zoom;
    for (const candidate of candidates) {
      const collision = accepted.some((other) => boxesOverlap(candidate.box, other.box, padding));
      if (!collision || candidate.isSelected || candidate.inRoute) accepted.push(candidate);
    }
    return new Map(accepted.map((item) => [item.id, item]));
  }, [activePathSet, floorplan.rooms, labelAnchorMap, presentation, rooms, selectedRoomId, zoom]);

  useEffect(() => {
    const shell = shellRef.current;
    const svg = svgRef.current;
    if (!shell || !svg) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const rect = svg.getBoundingClientRect();
      const anchor = {
        x: view.x + ((event.clientX - rect.left) / Math.max(1, rect.width)) * view.w,
        y: view.y + ((event.clientY - rect.top) / Math.max(1, rect.height)) * view.h,
      };
      const factor = event.deltaY < 0 ? 1.16 : 1 / 1.16;
      setZoomAt(zoom * factor, anchor);
    };
    shell.addEventListener("wheel", wheel, { passive: false, capture: true });
    return () => shell.removeEventListener("wheel", wheel, true);
  }, [zoom, view.x, view.y, view.w, view.h]);

  const startPan = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    touchPointsRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* browser may decline capture during gesture transition */ }
    if (touchPointsRef.current.size === 2) {
      const pts = [...touchPointsRef.current.values()];
      pinchRef.current = { distance: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y), zoom };
      dragRef.current = null;
      return;
    }
    const roomTarget = (event.target as Element | null)?.closest?.("[data-beam-room-id]") as SVGGElement | null;
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, centerX: clampedCenter.x, centerY: clampedCenter.y, moved: false, roomId: roomTarget?.dataset.beamRoomId ?? null };
  };

  const movePan = (event: React.PointerEvent<SVGSVGElement>) => {
    if (touchPointsRef.current.has(event.pointerId)) touchPointsRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (touchPointsRef.current.size === 2 && pinchRef.current) {
      event.preventDefault();
      const pts = [...touchPointsRef.current.values()];
      const distance = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      setZoomAt(pinchRef.current.zoom * (distance / Math.max(1, pinchRef.current.distance)));
      return;
    }
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const pixelDx = event.clientX - drag.x;
    const pixelDy = event.clientY - drag.y;
    if (Math.hypot(pixelDx, pixelDy) > 4) drag.moved = true;
    const dx = pixelDx * (view.w / Math.max(1, rect.width));
    const dy = pixelDy * (view.h / Math.max(1, rect.height));
    setCenter({ x: drag.centerX - dx, y: drag.centerY - dy });
  };

  const endPan = (event: React.PointerEvent<SVGSVGElement>) => {
    touchPointsRef.current.delete(event.pointerId);
    if (touchPointsRef.current.size < 2) pinchRef.current = null;
    const drag = dragRef.current;
    if (drag?.pointerId === event.pointerId) {
      if (drag.moved) {
      } else if (drag.roomId) {
        onSelectRoom(drag.roomId);
      }
      dragRef.current = null;
    }
  };

  const statItems = selectedLiveRoom ? [
    { icon: Thermometer, label: "Temperature", value: `${selectedLiveRoom.temp_c.toFixed(1)}°C` },
    { icon: Droplets, label: "Humidity", value: `${selectedLiveRoom.humidity.toFixed(0)}% RH` },
    { icon: Wind, label: "Airflow", value: `${Math.round(selectedLiveRoom.airflow_m3h)} m³/h` },
    { icon: Power, label: "Power", value: `${selectedLiveRoom.power_kw.toFixed(2)} kW` },
  ] : [];

  return (
    <div ref={shellRef} className={`beam-floorplan-shell relative overflow-hidden rounded-lg border border-slate-800 ${(isFullscreen || pseudoFullscreen) ? "beam-floorplan-fullscreen" : ""} ${pseudoFullscreen ? "fixed inset-0 z-[100] rounded-none border-0" : ""}` }>
      <div className="absolute right-2 top-2 z-30 flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950/90 p-1 shadow-xl backdrop-blur">
        <button type="button" onClick={() => setZoomAt(zoom / 1.35)} disabled={zoom <= 1.001} className="rounded p-2 text-slate-300 hover:bg-slate-800 disabled:opacity-30" title="Zoom out"><ZoomOut className="h-4 w-4" /></button>
        <div className="hidden w-12 text-center font-mono text-[9px] text-cyan-300 sm:block">{Math.round(zoom * 100)}%</div>
        <button type="button" onClick={() => setZoomAt(zoom * 1.35)} disabled={zoom >= 5.99} className="rounded p-2 text-slate-300 hover:bg-slate-800 disabled:opacity-30" title="Zoom in"><ZoomIn className="h-4 w-4" /></button>
        <button type="button" onClick={fit} className="rounded p-2 text-slate-300 hover:bg-slate-800" title="Fit floorplan"><Maximize2 className="h-4 w-4" /></button>
        <button type="button" onClick={() => { void toggleFullscreen(); }} className="rounded p-2 text-cyan-300 hover:bg-cyan-500/10" title={(isFullscreen || pseudoFullscreen) ? "Exit fullscreen" : "Open floorplan fullscreen"}>{(isFullscreen || pseudoFullscreen) ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}</button>
      </div>
      <div className="absolute left-2 top-2 z-20 hidden rounded border border-slate-800 bg-slate-950/80 px-2 py-1 text-[9px] text-slate-500 pointer-events-none md:block">Pinch/wheel over map to zoom · drag to pan · Fit resets view</div>
      <svg ref={svgRef} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} preserveAspectRatio="xMidYMid meet" aria-label="Interactive OpenStudio hospital floorplan" className="beam-floorplan-canvas block w-full select-none touch-none overscroll-contain" onPointerDown={startPan} onPointerMove={movePan} onPointerUp={endPan} onPointerCancel={endPan}>
        <defs>
          <filter id="beamGlow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="0.7" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
          <pattern id="beamGrid" width="2" height="2" patternUnits="userSpaceOnUse"><path d="M 2 0 L 0 0 0 2" fill="none" stroke={viz.grid} strokeWidth="0.035"/></pattern>
          <symbol id="beamIconTemp" viewBox="0 0 24 24"><path d="M9 4a3 3 0 0 1 6 0v8.2a5 5 0 1 1-6 0V4Z" fill="none" stroke="currentColor" strokeWidth="2"/><path d="M12 7v8" stroke="currentColor" strokeWidth="2"/></symbol>
          <symbol id="beamIconDrop" viewBox="0 0 24 24"><path d="M12 3s6 6.2 6 11a6 6 0 1 1-12 0c0-4.8 6-11 6-11Z" fill="none" stroke="currentColor" strokeWidth="2"/></symbol>
          <symbol id="beamIconWind" viewBox="0 0 24 24"><path d="M3 8h11c2.8 0 2.8-4 0-4-1.4 0-2.3.7-2.7 1.5M3 12h16M3 16h11c2.8 0 2.8 4 0 4-1.4 0-2.3-.7-2.7-1.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></symbol>
          <symbol id="beamIconPerson" viewBox="0 0 24 24"><circle cx="12" cy="7" r="3" fill="none" stroke="currentColor" strokeWidth="2"/><path d="M5 21c.7-5 3-7.5 7-7.5S18.3 16 19 21" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></symbol>
        </defs>
        <rect data-pan-surface="true" x={baseX} y={baseY} width={baseWidth} height={baseHeight} fill={viz.background} />
        <rect data-pan-surface="true" x={baseX} y={baseY} width={baseWidth} height={baseHeight} fill="url(#beamGrid)" opacity="0.38" />
        {renderRooms.map((modelRoom) => {
          const live = rooms[modelRoom.id];
          const status = live?.status ?? "SETBACK";
          const palette = statusStyle[status];
          const isClinical = clinicalCategories.has(modelRoom.category);
          const isSelected = selectedRoomId === modelRoom.id;
          const inRoute = activePathSet.has(modelRoom.id);
          const points = modelRoom.polygon.map(([x, y]) => `${tx(x)},${ty(y)}`).join(" ");
          const baseFill = layer === "STATUS"
            ? (isClinical ? heatColor("STATUS", live, theme) : modelRoom.category === "VOID" ? viz.voidFill : modelRoom.category === "STAIRS" ? viz.stairsFill : viz.supportFill)
            : heatColor(layer, live, theme);
          const severity = live?.alarm_severity ?? "NORMAL";
          const stroke = isSelected ? viz.selected : inRoute ? viz.route : severity !== "NORMAL" ? alarmStroke[severity] : isClinical ? (theme === "light" ? "#718096" : palette.stroke) : viz.roomBoundary;
          const label = labels.get(modelRoom.id) as any;
          const activeCase = live?.active_case_id ? cases[live.active_case_id] : undefined;
          const cx = tx(modelRoom.centroid[0]);
          const cy = ty(modelRoom.centroid[1]);
          const sparkValues = live?.trend?.map((point) => point.temp_c) ?? [];
          return (
            <g key={modelRoom.id} data-beam-room-id={modelRoom.id} className="cursor-pointer" role="button" aria-label={`Open controls for ${modelRoom.name}`} tabIndex={-1}>
              <title>{`${modelRoom.name} · ${modelRoom.area_m2.toFixed(1)} m²${live ? ` · ${live.temp_c.toFixed(1)}°C · ${live.humidity.toFixed(0)}% RH · ${Math.round(live.airflow_m3h)} m³/h · ${live.power_kw.toFixed(2)} kW · ${live.session_utilization_percent.toFixed(0)}% session utilization${live.alarm_reasons.length ? ` · ${live.alarm_reasons.join("; ")}` : ""}` : ""}`}</title>
              <polygon points={points} fill={baseFill} fillOpacity={modelRoom.category === "VOID" ? 0.24 : layer === "STATUS" ? (isClinical ? 0.9 : 0.78) : 0.88} stroke={stroke} strokeWidth={isSelected ? 1.8 : inRoute ? 1.55 : severity === "CRITICAL" ? 1.6 : severity === "WARNING" ? 1.3 : 0.45} vectorEffect="non-scaling-stroke" filter={(theme === "dark" && (isSelected || inRoute || severity === "CRITICAL")) ? "url(#beamGlow)" : undefined} />
              {presentation === "COMMAND_CENTER" && severity !== "NORMAL" && <circle cx={cx} cy={cy - 1.15 / zoom} r={0.28 / zoom} fill={alarmStroke[severity]} stroke={viz.alarmHalo} strokeWidth={0.09 / zoom} pointerEvents="none" />}
              {label && <g pointerEvents="none">
                {label.lines.map((line: string, idx: number) => {
                  const totalNameHeight = label.lines.length * label.fontSize * 1.05;
                  const nameStart = label.y - totalNameHeight / 2 + label.fontSize * 0.5 - (label.telemetry ? label.telemetrySize * 0.52 : 0);
                  return <text key={`${modelRoom.id}-line-${idx}`} x={label.x} y={nameStart + idx * label.fontSize * 1.08} textAnchor="middle" dominantBaseline="middle" fill={label.isClinical ? viz.clinicalText : viz.supportText} fontSize={label.fontSize} fontWeight={label.isClinical ? 700 : 560} stroke={viz.labelHalo} strokeWidth={0.18 / zoom} paintOrder="stroke">{line}</text>;
                })}
                {label.telemetry && label.live && <g transform={`translate(${label.x},${label.y + label.lines.length * label.fontSize * 0.56 + label.telemetrySize})`} color="#cbd5e1">
                  <use href="#beamIconTemp" x={-4.55 / zoom} y={-0.38 / zoom} width={0.76 / zoom} height={0.76 / zoom} color="#fb7185"/>
                  <text x={-3.68 / zoom} y="0" textAnchor="start" dominantBaseline="middle" fill={viz.clinicalText} fontSize={label.telemetrySize} fontFamily="ui-monospace, monospace">{label.live.temp_c.toFixed(1)}°</text>
                  <use href="#beamIconDrop" x={-1.42 / zoom} y={-0.38 / zoom} width={0.76 / zoom} height={0.76 / zoom} color="#22d3ee"/>
                  <text x={-0.55 / zoom} y="0" textAnchor="start" dominantBaseline="middle" fill={viz.clinicalText} fontSize={label.telemetrySize} fontFamily="ui-monospace, monospace">{label.live.humidity.toFixed(0)}%</text>
                  <use href="#beamIconWind" x={1.45 / zoom} y={-0.38 / zoom} width={0.76 / zoom} height={0.76 / zoom} color="#34d399"/>
                  <text x={2.32 / zoom} y="0" textAnchor="start" dominantBaseline="middle" fill={viz.clinicalText} fontSize={label.telemetrySize} fontFamily="ui-monospace, monospace">{formatFloorplanFlow(label.live.airflow_m3h)}</text>
                </g>}
              </g>}
              {presentation === "COMMAND_CENTER" && live && detail >= 1 && live.occupancy > 0 && <g transform={`translate(${cx + 0.45 / zoom},${cy - 0.82 / zoom})`} pointerEvents="none" color={viz.occupancyText}><rect x={-0.55 / zoom} y={-0.35 / zoom} width={1.55 / zoom} height={0.72 / zoom} rx={0.28 / zoom} fill={viz.occupancyBg} fillOpacity={theme === "light" ? 0.94 : 0.82} stroke={viz.occupancyBorder} strokeWidth={0.06 / zoom}/><use href="#beamIconPerson" x={-0.43 / zoom} y={-0.27 / zoom} width={0.55 / zoom} height={0.55 / zoom}/><text x={0.25 / zoom} y="0" dominantBaseline="middle" fontSize={0.5 / zoom} fill={viz.occupancyText} fontFamily="ui-monospace, monospace">{live.occupancy}</text></g>}
              {presentation === "COMMAND_CENTER" && live && detail >= 2 && modelRoom.category === "OPERATING_ROOM" && <text x={cx} y={cy + 1.65 / zoom} textAnchor="middle" dominantBaseline="middle" fill={viz.supportText} fontSize={0.52 / zoom} fontFamily="ui-monospace, monospace" pointerEvents="none">UTIL {live.session_utilization_percent.toFixed(0)}%</text>}
              {presentation === "COMMAND_CENTER" && activeCase && modelRoom.category === "OPERATING_ROOM" && detail >= 1 && <g transform={`translate(${cx},${cy - 1.72 / zoom})`} pointerEvents="none"><rect x={-2.75 / zoom} y={-0.42 / zoom} width={5.5 / zoom} height={0.84 / zoom} rx={0.25 / zoom} fill={viz.liveBg} stroke={viz.liveBorder} strokeWidth={0.08 / zoom}/><circle cx={-2.25 / zoom} cy="0" r={0.15 / zoom} fill={viz.liveBorder}/><text x={-1.9 / zoom} y="0" dominantBaseline="middle" fill={viz.liveText} fontSize={0.45 / zoom} fontWeight="700">LIVE · {activeCase.procedure.length > 18 ? `${activeCase.procedure.slice(0, 17)}…` : activeCase.procedure}</text></g>}
              {presentation === "COMMAND_CENTER" && live && isClinical && detail >= 3 && modelRoom.area_m2 >= 14 && sparkValues.length >= 3 && (Math.max(...sparkValues) - Math.min(...sparkValues) >= 0.05) && <polyline pointerEvents="none" points={sparklinePoints(sparkValues, cx - 2.12 / zoom, cy + 2.12 / zoom, 4.24 / zoom, 0.55 / zoom)} fill="none" stroke={viz.spark} strokeWidth={1.15} strokeLinecap="round" strokeLinejoin="round" opacity="0.8" vectorEffect="non-scaling-stroke"/>}
            </g>
          );
        })}
        {/* Hard architectural boundary pass: fills never define topology.  A
            second, non-scaling outline pass keeps every room/corridor boundary
            crisp at every zoom level and on high-DPI displays. */}
        {renderRooms.map((modelRoom) => {
          const points = modelRoom.polygon.map(([x, y]) => `${tx(x)},${ty(y)}`).join(" ");
          return <polygon key={`boundary-${modelRoom.id}`} points={points} fill="none" stroke={modelRoom.category === "CORRIDOR" ? viz.corridorBoundary : viz.roomBoundary} strokeWidth={modelRoom.category === "CORRIDOR" ? 2.15 : 1.55} strokeLinejoin="round" vectorEffect="non-scaling-stroke" pointerEvents="none" />;
        })}
        {renderRooms.map((modelRoom) => {
          const live = rooms[modelRoom.id];
          const isSelected = selectedRoomId === modelRoom.id;
          const inRoute = activePathSet.has(modelRoom.id);
          const severity = live?.alarm_severity ?? "NORMAL";
          if (!isSelected && !inRoute && severity === "NORMAL") return null;
          const points = modelRoom.polygon.map(([x, y]) => `${tx(x)},${ty(y)}`).join(" ");
          const hi = isSelected ? viz.selected : inRoute ? viz.route : alarmStroke[severity];
          return <polygon key={`highlight-${modelRoom.id}`} points={points} fill="none" stroke={hi} strokeWidth={isSelected ? 2.4 : 2.0} strokeLinejoin="round" vectorEffect="non-scaling-stroke" pointerEvents="none" filter={(theme === "dark" && (isSelected || inRoute || severity === "CRITICAL")) ? "url(#beamGlow)" : undefined} />;
        })}
        {showDoors && floorplan.doors.map((door) => <circle key={door.id} cx={tx(door.point[0])} cy={ty(door.point[1])} r={0.22 / zoom} fill="#67e8f9" stroke="#083344" strokeWidth={0.08 / zoom} pointerEvents="none" />)}
        {showCirculation && activePath.length > 1 && activePath.slice(0, -1).map((roomId, idx) => {
          const nextId = activePath[idx + 1]; const a = modelRoomMap[roomId]; const b = modelRoomMap[nextId]; if (!a || !b) return null;
          const door = pairDoor(roomId, nextId);
          const pts = door ? `${tx(a.centroid[0])},${ty(a.centroid[1])} ${tx(door.point[0])},${ty(door.point[1])} ${tx(b.centroid[0])},${ty(b.centroid[1])}` : `${tx(a.centroid[0])},${ty(a.centroid[1])} ${tx(b.centroid[0])},${ty(b.centroid[1])}`;
          return <polyline key={`${roomId}-${nextId}-${idx}`} points={pts} fill="none" stroke={viz.route} strokeWidth={0.34 / zoom} strokeDasharray={`${0.72 / zoom} ${0.52 / zoom}`} opacity={viz.routeOpacity} filter={viz.routeGlow ? "url(#beamGlow)" : undefined} pointerEvents="none" />;
        })}
      </svg>
      {selectedCase && showCirculation && <div className="beam-route-label absolute bottom-2 left-2 max-w-[72%] rounded-md border px-2.5 py-1.5 text-[10px] shadow-lg"><span className="font-semibold">Clinical route:</span> {selectedCase.case_label} · {selectedCase.procedure}</div>}
      {presentation === "COMMAND_CENTER" && selectedModelRoom && <div className="beam-room-hud absolute bottom-2 right-2 max-w-[min(94%,620px)] rounded-xl border border-slate-700/90 bg-slate-950/95 px-3 py-2.5 shadow-2xl backdrop-blur pointer-events-none">
        <div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-slate-100">{selectedModelRoom.name}</div><div className="text-[9px] text-slate-500">{prettyCategory(selectedModelRoom.category)}{selectedLiveRoom ? ` · ${selectedLiveRoom.control_source}` : ""}</div></div><div className="text-right text-[9px] text-slate-500"><div>{selectedModelRoom.area_m2.toFixed(1)} m²</div>{selectedLiveRoom && <div className="mt-1 font-mono text-cyan-300">{selectedLiveRoom.session_utilization_percent.toFixed(0)}% session util.</div>}</div></div>
        {selectedLiveRoom && <>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">{statItems.map(({icon: Icon,label,value}) => <div key={label} className="rounded-md border border-slate-800 bg-slate-900/80 px-2 py-1.5"><div className="flex items-center gap-1 text-[8px] uppercase tracking-wide text-slate-500"><Icon className="h-3 w-3 text-cyan-400"/>{label}</div><div className="mt-0.5 font-mono text-[10px] text-slate-100">{value}</div></div>)}</div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[9px] sm:grid-cols-4">
            <div className="rounded-md border border-slate-800 bg-slate-900/70 px-2 py-1.5"><div className="text-slate-500">Occupancy</div><div className="mt-0.5 flex items-center gap-1 font-mono text-slate-100"><UserRound className="h-3 w-3 text-sky-300"/>{selectedLiveRoom.occupancy}</div></div>
            <div className="rounded-md border border-slate-800 bg-slate-900/70 px-2 py-1.5"><div className="text-slate-500">Power density</div><div className="mt-0.5 font-mono text-slate-100">{selectedLiveRoom.power_density_w_m2.toFixed(1)} W/m²</div></div>
            <div className="rounded-md border border-slate-800 bg-slate-900/70 px-2 py-1.5"><div className="text-slate-500">Alarm</div><div className="mt-0.5 font-mono" style={{color: alarmStroke[selectedLiveRoom.alarm_severity]}}>{selectedLiveRoom.alarm_severity}</div></div>
            <div className="rounded-md border border-slate-800 bg-slate-900/70 px-2 py-1.5"><div className="text-slate-500">Active case</div><div className="mt-0.5 truncate font-mono text-emerald-300">{selectedLiveRoom.active_case_id ? (cases[selectedLiveRoom.active_case_id]?.procedure ?? selectedLiveRoom.active_case_id) : "None"}</div></div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="rounded-md border border-slate-800 bg-slate-900/55 px-2 py-1 text-cyan-300"><div className="text-[8px] uppercase text-slate-500">Temperature trend</div><MiniSparkline points={selectedLiveRoom.trend} field="temp_c"/></div>
            <div className="rounded-md border border-slate-800 bg-slate-900/55 px-2 py-1 text-amber-300"><div className="text-[8px] uppercase text-slate-500">Power trend</div><MiniSparkline points={selectedLiveRoom.trend} field="power_kw"/></div>
          </div>
          {selectedLiveRoom.alarm_reasons.length > 0 && <div className="mt-2 rounded-md border border-amber-500/30 bg-amber-950/20 px-2 py-1.5 text-[9px] text-amber-200">{selectedLiveRoom.alarm_reasons.join(" · ")}</div>}
        </>}
      </div>}
    </div>
  );
}

interface CommandCenterViewProps {
  floorplan: FloorplanModel;
  rooms: Record<string, Room>;
  his: HISState;
  roi: RoiState;
  energyAI: EnergyAIState;
  autopilot: boolean;
  nextCaseSeconds: number;
  cases: Record<string, HISCase>;
  layer: FloorLayer;
  showDoors: boolean;
  showCirculation: boolean;
  selectedRoomId: string | null;
  selectedCase: HISCase | null;
  controls: Controls;
  lightingLevel: number;
  sterility: SterilityState;
  emergencyMode: string | null;
  pending: (action: string) => boolean;
  onLayer: (layer: FloorLayer) => void;
  onSelectRoom: (id: string) => void;
  onSelectCase: (id: string) => void;
  onAddExternal: () => void;
  onManualSchedule: (c: HISCase) => void;
  onToggleDoors: () => void;
  onToggleFlow: () => void;
  onProfile: (profile: string) => void;
  onControl: (field: keyof Controls, value: number) => void;
  onLighting: (value: number) => void;
  onSterilityCommand: (payload: Record<string, unknown>) => void;
  onClose: () => void;
  theme: BeamTheme;
}

function CommandCenterView({
  floorplan, rooms, his, roi, energyAI, autopilot, nextCaseSeconds, cases,
  layer, showDoors, showCirculation, selectedRoomId, selectedCase,
  controls, lightingLevel, sterility, emergencyMode, pending,
  onLayer, onSelectRoom, onSelectCase, onAddExternal, onManualSchedule,
  onToggleDoors, onToggleFlow, onProfile, onControl, onLighting,
  onSterilityCommand, onClose, theme,
}: CommandCenterViewProps) {
  const [rightMode, setRightMode] = useState<"OPERATIONS" | "HIS">("OPERATIONS");
  const unscheduled = his.cases.filter((c) => c.status === "UNSCHEDULED").sort((a, b) => b.priority_score - a.priority_score);
  const upcoming = his.cases.filter((c) => ["SCHEDULED", "IN_PROGRESS"].includes(c.status)).sort((a, b) => new Date(a.scheduled_start ?? 0).getTime() - new Date(b.scheduled_start ?? 0).getTime());
  const critical = Object.values(rooms).filter((r) => r.alarm_severity === "CRITICAL").length;
  const warnings = Object.values(rooms).filter((r) => r.alarm_severity === "WARNING").length;
  const roomArray = Object.values(rooms);
  return <div className="beam-command-center fixed inset-0 z-[120] overflow-y-auto lg:overflow-hidden">
    <div className="beam-cc-header flex min-h-12 flex-wrap items-center justify-between gap-2 border-b px-3 py-2 sm:px-4 lg:h-12 lg:flex-nowrap lg:py-0">
      <div className="flex items-center gap-3"><Activity className="h-5 w-5 text-emerald-400"/><div><div className="text-sm font-semibold tracking-wide">B.E.A.M. Command Center</div><div className="text-[9px] text-slate-500">PRO v10 · surgical operations · advanced HVAC/sterility · EnergyPlus-calibrated energy supervision</div></div></div>
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-rose-600 dark:text-rose-300">{critical} critical</span>
        <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">{warnings} warning</span>
        <span className="rounded border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-violet-700 dark:text-violet-200">Energy AI {energyAI.status}</span>
        <button type="button" onClick={onClose} className="rounded border border-slate-400/60 p-2 text-slate-600 hover:bg-slate-500/10 dark:border-slate-700 dark:text-slate-300" title="Exit command center"><X className="h-4 w-4"/></button>
      </div>
    </div>
    <div className="grid min-h-[calc(100dvh-3rem)] grid-cols-1 gap-3 p-2 sm:p-3 lg:h-[calc(100dvh-3rem)] lg:grid-cols-12">
      <section className="beam-panel flex min-h-[58dvh] flex-col rounded-xl border p-2 lg:col-span-7 lg:min-h-0 xl:col-span-8">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1"><div><div className="text-xs font-semibold">OpenStudio / EnergyPlus Digital Twin</div><div className="text-[9px] text-slate-500">Semantic zoom · room analytics · heatmap layers · live case overlay · click room for manual setup</div></div><div className="flex flex-wrap items-center gap-1 text-[9px]">{(["STATUS","TEMPERATURE","HUMIDITY","ENERGY"] as FloorLayer[]).map((item)=><button key={item} type="button" onClick={()=>onLayer(item)} className={`rounded border px-2 py-1 ${layer===item?"border-cyan-500/60 bg-cyan-500/10 text-cyan-700 dark:text-cyan-200":"border-slate-400/60 text-slate-500 dark:border-slate-700"}`}>{item === "TEMPERATURE" ? "TEMP" : item === "HUMIDITY" ? "RH" : item}</button>)}<button type="button" onClick={onToggleDoors} className={`rounded border px-2 py-1 ${showDoors?"border-cyan-500/60 text-cyan-700 dark:text-cyan-200":"border-slate-400/60 text-slate-500 dark:border-slate-700"}`}>Doors</button><button type="button" onClick={onToggleFlow} className={`rounded border px-2 py-1 ${showCirculation?"border-violet-500/60 text-violet-700 dark:text-violet-200":"border-slate-400/60 text-slate-500 dark:border-slate-700"}`}>Flow</button></div></div>
        <div className="min-h-0 flex-1"><FloorplanTwin floorplan={floorplan} rooms={rooms} cases={cases} layer={layer} selectedRoomId={selectedRoomId} selectedCase={selectedCase} showDoors={showDoors} showCirculation={showCirculation} presentation="COMMAND_CENTER" theme={theme} onSelectRoom={onSelectRoom}/></div>
      </section>

      <section className="beam-panel flex min-h-[52dvh] flex-col overflow-hidden rounded-xl border lg:col-span-5 lg:min-h-0 xl:col-span-4">
        <div className="flex shrink-0 items-center justify-between border-b border-slate-300/70 px-2 py-2 dark:border-slate-800">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Supervisory workspace</div>
          <div className="flex rounded-md border border-slate-300/80 p-0.5 text-[9px] dark:border-slate-700">
            <button type="button" onClick={()=>setRightMode("OPERATIONS")} className={`rounded px-2 py-1 ${rightMode === "OPERATIONS" ? "bg-cyan-500/15 font-semibold text-cyan-700 dark:text-cyan-200" : "text-slate-500"}`}>HVAC + Sterility</button>
            <button type="button" onClick={()=>setRightMode("HIS")} className={`rounded px-2 py-1 ${rightMode === "HIS" ? "bg-violet-500/15 font-semibold text-violet-700 dark:text-violet-200" : "text-slate-500"}`}>HIS + Energy</button>
          </div>
        </div>
        {rightMode === "OPERATIONS" ? (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-2">
            <ControlPanel controls={controls} lightingLevel={lightingLevel} rooms={roomArray} energyAI={energyAI} pending={pending} onProfile={onProfile} onControl={onControl} onLighting={onLighting}/>
            <SterilityPanel sterility={sterility} emergencyMode={emergencyMode} rooms={roomArray} pending={pending} onCommand={onSterilityCommand}/>
            <div className="grid grid-cols-1 gap-3 2xl:grid-cols-2"><EnergyPanel roi={roi} compact/><EnergyAISupervisorPanel state={energyAI}/></div>
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-2">
            <HISPanel his={his} rooms={rooms} autopilot={autopilot} nextCaseSeconds={nextCaseSeconds} unscheduled={unscheduled} upcoming={upcoming} selectedCaseId={selectedCase?.id ?? null} onSelectCase={onSelectCase} onAddExternal={onAddExternal} onManualSchedule={onManualSchedule}/>
            <EnergyPanel roi={roi}/>
            <EnergyAISupervisorPanel state={energyAI}/>
          </div>
        )}
      </section>
    </div>
  </div>;
}


interface HISPanelProps {
  his: HISState;
  rooms: Record<string, Room>;
  autopilot: boolean;
  nextCaseSeconds: number;
  unscheduled: HISCase[];
  upcoming: HISCase[];
  selectedCaseId: string | null;
  onSelectCase: (id: string) => void;
  onAddExternal: () => void;
  onManualSchedule: (c: HISCase) => void;
}

function HISPanel({ his, rooms, autopilot, nextCaseSeconds, unscheduled, upcoming, selectedCaseId, onSelectCase, onAddExternal, onManualSchedule }: HISPanelProps) {
  const healthClass = his.scheduler.health === "HEALTHY" ? "border-emerald-500/60 text-emerald-300" : his.scheduler.health === "DEGRADED" ? "border-amber-500/60 text-amber-300" : "border-rose-500/70 text-rose-300";
  return (
    <div className="flex max-h-[72dvh] xl:max-h-[760px] flex-col rounded-xl border border-slate-800 bg-slate-900/65 shadow-xl shadow-black/20">
      <div className="border-b border-slate-800 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-violet-400" />
            <div>
              <h2 className="text-sm font-semibold">HIS Infinite Intake & Scheduler</h2>
              <p className="text-[10px] text-slate-500">Non-seeded stochastic intake · validated OR capability allocation</p>
            </div>
          </div>
          <button type="button" onClick={onAddExternal} className="flex shrink-0 items-center gap-1 rounded-md border border-cyan-500/60 bg-cyan-500/10 px-2 py-1 text-[10px] text-cyan-300 hover:bg-cyan-500/20">
            <Plus className="h-3 w-3" /> External Case
          </button>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-[10px]">
          <div className={`rounded border px-2 py-1.5 ${healthClass}`}>
            <div className="text-slate-500">Scheduler</div><div className="font-semibold">{his.scheduler.health}</div><div className="mt-0.5 text-[8px] text-slate-500">SLA risk {his.scheduler.sla_risk_count}</div>
          </div>
          <div className="rounded border border-slate-700 px-2 py-1.5 text-slate-300">
            <div className="text-slate-500">Next random intake</div><div className="font-mono">~{nextCaseSeconds}s</div>
          </div>
          <div className="rounded border border-slate-700 px-2 py-1.5 text-slate-300">
            <div className="text-slate-500">Generated / External</div><div className="font-mono">{his.generator.total_generated} / {his.generator.total_external}</div>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold"><AlertTriangle className={`h-3.5 w-3.5 ${unscheduled.length ? "text-rose-400" : "text-slate-500"}`} /> Priority Queue</div>
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-mono ${unscheduled.length ? "bg-rose-500/15 text-rose-300" : "bg-slate-800 text-slate-500"}`}>{unscheduled.length} unscheduled</span>
        </div>
        {unscheduled.length === 0 ? (
          <div className="mb-4 rounded-md border border-emerald-500/20 bg-emerald-500/5 p-2 text-[10px] text-emerald-300">No scheduling backlog. {autopilot ? "AI is absorbing incoming cases." : "Manual queue is clear."}</div>
        ) : (
          <div className="mb-4 space-y-2">
            {unscheduled.map((c) => (
              <CaseCard key={c.id} c={c} room={null} selected={selectedCaseId === c.id} onClick={() => onSelectCase(c.id)}>
                <button type="button" onClick={(e) => { e.stopPropagation(); onManualSchedule(c); }} className="rounded border border-rose-500/60 bg-rose-500/10 px-2 py-1 text-[9px] text-rose-200 hover:bg-rose-500/20">Schedule manually</button>
              </CaseCard>
            ))}
          </div>
        )}

        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold"><CalendarClock className="h-3.5 w-3.5 text-cyan-400" /> Scheduled Cases</div>
          <span className="text-[9px] text-slate-500">turnover {his.scheduler.turnover_minutes} min</span>
        </div>
        <div className="space-y-2">
          {upcoming.map((c) => (
            <CaseCard key={c.id} c={c} room={c.scheduled_room_id ? rooms[c.scheduled_room_id] ?? null : null} selected={selectedCaseId === c.id} onClick={() => onSelectCase(c.id)}>
              <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
            </CaseCard>
          ))}
        </div>
      </div>
      <div className="border-t border-slate-800 px-3 py-2 text-[9px] text-slate-500">
        OR specialty capability is a B.E.A.M. configuration layer, not metadata claimed from OpenStudio.
      </div>
    </div>
  );
}

function CaseCard({ c, room, selected, onClick, children }: { c: HISCase; room: Room | null; selected: boolean; onClick: () => void; children: React.ReactNode }) {
  const urgencyClass = c.urgency === "STAT" ? "text-rose-300" : c.urgency === "EMERGENCY" ? "text-orange-300" : c.urgency === "URGENT" ? "text-amber-300" : "text-slate-400";
  return (
    <div role="button" tabIndex={0} onClick={onClick} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClick(); }} className={`w-full cursor-pointer rounded-md border p-2 text-left transition ${selected ? "border-violet-400 bg-violet-500/10" : c.status === "UNSCHEDULED" ? "border-rose-500/45 bg-rose-950/25 hover:border-rose-400" : "border-slate-700 bg-slate-950/45 hover:border-slate-600"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 text-[9px] font-mono">
            <span className={urgencyClass}>{c.urgency}</span>
            <span className="text-slate-600">·</span>
            <span className="text-cyan-300">{prettySpecialty(c.specialty)}</span>
            <span className="text-slate-600">·</span>
            <span className="text-slate-500">{c.source === "EXTERNAL" ? "EXTERNAL" : "HIS"}</span>
          </div>
          <div className="mt-1 truncate text-[11px] font-medium text-slate-200">{c.procedure}</div>
          <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[9px] text-slate-500">
            <span>{c.case_label}</span>
            <span>{c.estimated_duration_min} min</span>
            {room && <span className="text-emerald-300">{room.name}</span>}
            {c.scheduled_start && <span>{formatDateTime(c.scheduled_start)}</span>}
          </div>
          {c.constraint_reason && <div className="mt-1 text-[9px] text-rose-300">{c.constraint_reason}</div>}
        </div>
        <div className="flex shrink-0 items-center">{children}</div>
      </div>
    </div>
  );
}

function ControlPanel({
  className,
  controls,
  lightingLevel,
  rooms,
  energyAI,
  onControl,
  onLighting,
  onProfile,
  pending,
}: {
  className?: string;
  controls: Controls;
  lightingLevel: number;
  rooms: Room[];
  energyAI: EnergyAIState;
  onControl: (field: keyof Controls, value: number) => void;
  onLighting: (value: number) => void;
  onProfile: (profile: string) => void;
  pending: (action: string) => boolean;
}) {
  const conditioned = rooms.filter((r) => r.conditioned);
  const activeORs = rooms.filter((r) => r.category === "OPERATING_ROOM" && (r.status === "ACTIVE" || r.active_case_id)).length;
  const avgTemp = conditioned.length ? conditioned.reduce((sum, r) => sum + r.temp_c, 0) / conditioned.length : 0;
  const avgRh = conditioned.length ? conditioned.reduce((sum, r) => sum + r.humidity, 0) / conditioned.length : 0;
  const profiles = [
    { id: "CLINICAL_STANDARD", label: "Clinical Standard", detail: "20°C · 50% RH · 75% fan · 70% light" },
    { id: "SURGERY_READY", label: "Surgery Ready", detail: "20°C · 50% RH · 90% fan · 100% light" },
    { id: "ENERGY_BALANCED", label: "Energy Balanced", detail: "21°C · 50% RH · 60% fan · 45% light" },
    { id: "NIGHT_SETBACK", label: "Night Setback", detail: "23°C · 50% RH · 40% fan · 15% light" },
  ];
  return (
    <div className={`${className ?? ""} rounded-xl border border-slate-800 bg-slate-900/65 p-4 shadow-xl shadow-black/15`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-cyan-400" />
          <div>
            <h2 className="text-sm font-semibold">Clinical HVAC & Lighting Control Plane</h2>
            <p className="text-[9px] text-slate-500">Global supervisory setpoints · atomic profiles · room safety arbitration remains authoritative</p>
          </div>
        </div>
        <div className={`rounded border px-2 py-1 text-[9px] font-mono ${energyAI.enabled ? "border-violet-500/40 bg-violet-500/10 text-violet-200" : "border-slate-700 text-slate-500"}`}>
          Energy AI {energyAI.status}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[9px] sm:grid-cols-4">
        <Metric label="Conditioned spaces" value={`${conditioned.length}`} />
        <Metric label="Active ORs" value={`${activeORs}`} />
        <Metric label="Avg room temp" value={`${avgTemp.toFixed(1)}°C`} />
        <Metric label="Avg humidity" value={`${avgRh.toFixed(1)}%`} />
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[10px] font-semibold text-slate-300">Validated control profiles</div>
          <div className="text-[8px] text-slate-600">One backend ACK applies all four commands atomically</div>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {profiles.map((profile) => {
            const blocked = profile.id === "NIGHT_SETBACK" && activeORs > 0;
            return (
              <button
                key={profile.id}
                type="button"
                disabled={pending("APPLY_CONTROL_PROFILE") || blocked}
                onClick={() => onProfile(profile.id)}
                className="rounded-lg border border-slate-700 bg-slate-950/45 px-3 py-2 text-left transition hover:border-cyan-500/50 hover:bg-cyan-500/5 disabled:cursor-not-allowed disabled:opacity-35"
                title={blocked ? "Blocked while an operating room is clinically active" : profile.detail}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold text-slate-200">{profile.label}</span>
                  {blocked && <span className="rounded border border-rose-500/40 px-1.5 py-0.5 text-[8px] text-rose-300">LOCKED</span>}
                </div>
                <div className="mt-1 font-mono text-[8px] text-slate-500">{profile.detail}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/35 p-3">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[10px] font-semibold text-slate-300">Manual supervisory trim</div>
          <div className="font-mono text-[8px] text-cyan-400">ACKNOWLEDGED COMMANDS ONLY</div>
        </div>
        <div className="grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
          <ControlSlider label="Temperature Setpoint" suffix="°C" min={18} max={26} value={controls.tempSetpoint} disabled={pending("SET_TEMPERATURE_SETPOINT")} onChange={(v) => onControl("tempSetpoint", v)} />
          <ControlSlider label="Relative Humidity" suffix="%" min={45} max={60} value={controls.rhSetpoint} disabled={pending("SET_HUMIDITY_SETPOINT")} onChange={(v) => onControl("rhSetpoint", v)} />
          <ControlSlider label="AHU Fan Command" suffix="%" min={30} max={100} value={controls.fanSpeed} disabled={pending("SET_FAN_SPEED")} onChange={(v) => onControl("fanSpeed", v)} icon={<Wind className="h-3.5 w-3.5 text-cyan-400" />} />
          <ControlSlider label="Surgical Lighting" suffix="%" min={0} max={100} value={lightingLevel} disabled={pending("SET_LIGHTING")} onChange={onLighting} icon={<Lightbulb className="h-3.5 w-3.5 text-amber-400" />} />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 text-[9px] sm:grid-cols-3">
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5">
          <div className="font-semibold text-emerald-300">Clinical guardrail</div>
          <div className="mt-1 leading-relaxed text-slate-500">Active OR airflow remains safety-clamped even when a lower global fan command is requested.</div>
        </div>
        <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-2.5">
          <div className="font-semibold text-violet-300">Energy arbitration</div>
          <div className="mt-1 leading-relaxed text-slate-500">Energy AI may optimize idle rooms, but explicit room override, clinical demand and sterility safety have higher priority.</div>
        </div>
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-2.5">
          <div className="font-semibold text-cyan-300">Room-level control</div>
          <div className="mt-1 leading-relaxed text-slate-500">Click any conditioned floorplan polygon to open telemetry, trends and Manual Override / Room Operating Mode controls.</div>
        </div>
      </div>
    </div>
  );
}

function ControlSlider({ label, suffix, min, max, value, onChange, icon, disabled = false }: { label: string; suffix: string; min: number; max: number; value: number; onChange: (v: number) => void; icon?: React.ReactNode; disabled?: boolean }) {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!editing) setDraft(value); }, [editing, value]);
  const commit = (next: number) => {
    setDraft(next);
    setEditing(false);
    if (Math.abs(next - value) > 1e-9) onChange(next);
  };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[10px]">
        <span className="flex items-center gap-1 text-slate-400">{icon}{label}</span>
        <span className="font-mono text-cyan-300">{draft.toFixed(draft % 1 ? 1 : 0)}{suffix}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={draft}
        onPointerDown={() => setEditing(true)}
        onChange={(e) => { setEditing(true); setDraft(Number(e.target.value)); }}
        onPointerUp={(e) => commit(Number(e.currentTarget.value))}
        onKeyUp={(e) => { if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"].includes(e.key)) commit(Number(e.currentTarget.value)); }}
        onBlur={(e) => { if (editing) commit(Number(e.currentTarget.value)); }}
        disabled={disabled}
        className="w-full accent-cyan-500 disabled:cursor-wait disabled:opacity-50"
      />
    </div>
  );
}

function SterilityPanel({
  className,
  sterility,
  emergencyMode,
  rooms,
  onCommand,
  pending,
}: {
  className?: string;
  sterility: SterilityState;
  emergencyMode: string | null;
  rooms: Room[];
  onCommand: (p: Record<string, unknown>) => void;
  pending: (action: string) => boolean;
}) {
  const isIsolation = sterility.control_source === "NEGATIVE_ISOLATION" || emergencyMode === "Negative Pressure Isolation Mode";
  const margin = sterility.delta_p_pa - sterility.safety_threshold_pa;
  const clinicalRooms = rooms.filter((r) => ["OPERATING_ROOM", "PREP", "RECOVERY", "PREOP", "CORRIDOR"].includes(r.category) && r.conditioned);
  const safetyLockedRooms = rooms.filter((r) => r.control_source === "SAFETY_LOCK" || r.status === "ALARM").length;
  const pressureState = isIsolation ? "CONTROLLED ISOLATION" : sterility.pressure_alarm ? "HARD-LOCK ACTIVE" : margin < 0.35 ? "LOW RESERVE" : "NORMAL";
  const pressureClass = isIsolation ? "text-violet-300" : sterility.pressure_alarm ? "text-rose-300" : margin < 0.35 ? "text-amber-300" : "text-emerald-300";
  const trendData = sterility.trend.map((point) => ({
    time: new Date(point.time).toLocaleTimeString("en-GB", { hour12: false, minute: "2-digit", second: "2-digit" }),
    delta: point.delta_p_pa,
    target: point.target_delta_p_pa,
  }));
  const emergencyOptions = [
    { mode: "Immediate Smoke/Purge Mode", title: "Smoke / Purge", detail: "Maximum purge response; pressure safety logic remains latched until restored." },
    { mode: "Post-Op Sterilization Mode", title: "Post-Op Sterilization", detail: "High-turnover post-procedure ventilation policy for the digital twin." },
    { mode: "Negative Pressure Isolation Mode", title: "Negative Isolation", detail: "Intentional -2.5 Pa isolation mode; blocked while a physical pressure fault is latched." },
  ];

  return (
    <div className={`${className ?? ""} rounded-xl border border-slate-800 bg-slate-900/65 p-4 shadow-xl shadow-black/15`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-emerald-400" />
          <div>
            <h2 className="text-sm font-semibold">Sterility, Pressure & Safety Interlock</h2>
            <p className="text-[9px] text-slate-500">Differential-pressure supervision · hard-lock arbitration · emergency ventilation policies</p>
          </div>
        </div>
        <span className={`rounded border border-slate-700 bg-slate-950/50 px-2 py-1 text-[9px] font-semibold ${pressureClass}`}>{pressureState}</span>
      </div>

      <div className={`mt-3 rounded-xl border p-3 ${sterility.pressure_alarm ? "border-rose-500/60 bg-rose-500/10" : isIsolation ? "border-violet-500/45 bg-violet-500/7" : "border-emerald-500/30 bg-emerald-500/5"}`}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="text-[9px] uppercase tracking-wider text-slate-500">OR → Corridor differential</div>
            <div className={`mt-1 font-mono text-2xl ${pressureClass}`}>{sterility.delta_p_pa.toFixed(2)} Pa</div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-right text-[9px]">
            <div><div className="text-slate-600">Target</div><div className="font-mono text-cyan-300">{sterility.target_delta_p_pa.toFixed(2)} Pa</div></div>
            <div><div className="text-slate-600">Safety floor</div><div className="font-mono text-slate-300">+{sterility.safety_threshold_pa.toFixed(1)} Pa</div></div>
            <div><div className="text-slate-600">Reserve</div><div className={`font-mono ${isIsolation ? "text-violet-300" : margin >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{isIsolation ? "N/A" : `${margin >= 0 ? "+" : ""}${margin.toFixed(2)} Pa`}</div></div>
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-950">
          <div className={`h-full transition-all ${isIsolation ? "bg-violet-500" : sterility.pressure_alarm ? "bg-rose-500" : margin < 0.35 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${Math.max(4, Math.min(100, ((sterility.delta_p_pa + 3) / 8) * 100))}%` }} />
        </div>
        <div className="mt-2 flex flex-wrap justify-between gap-2 text-[8px] text-slate-600">
          <span>Control source: <span className="font-mono text-slate-400">{sterility.control_source}</span></span>
          <span>{clinicalRooms.length} clinical spaces supervised · {safetyLockedRooms} room lock(s)</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/35 p-2.5">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[10px] font-semibold text-slate-300">Live ΔP trend</span>
            <span className="text-[8px] text-slate-600">Real digital-twin samples · 4 s cadence</span>
          </div>
          <div className="h-28">
            {trendData.length >= 2 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="time" hide />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 8, fill: "#64748b" }} width={28} />
                  <Tooltip contentStyle={{ backgroundColor: "#020617", border: "1px solid #334155", fontSize: 9 }} />
                  <Line type="monotone" dataKey="delta" name="ΔP" stroke="#34d399" strokeWidth={1.8} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="target" name="Target" stroke="#22d3ee" strokeWidth={1} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : <div className="flex h-full items-center justify-center rounded border border-dashed border-slate-800 text-[9px] text-slate-600">Collecting pressure trend…</div>}
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/35 p-2.5">
          <div className="text-[10px] font-semibold text-slate-300">Positive-pressure policy</div>
          <p className="mt-1 text-[8px] leading-relaxed text-slate-600">The enhanced policy adds a conservative positive-pressure reserve in this prototype model. It does not replace hospital commissioning criteria.</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {(["STANDARD", "ENHANCED"] as const).map((policy) => (
              <button
                key={policy}
                type="button"
                disabled={pending("SET_PRESSURE_POLICY") || sterility.pressure_alarm}
                onClick={() => onCommand({ action: "SET_PRESSURE_POLICY", policy })}
                className={`rounded border px-2 py-2 text-[9px] disabled:cursor-not-allowed disabled:opacity-35 ${sterility.positive_pressure_policy === policy ? "border-cyan-500/60 bg-cyan-500/10 text-cyan-200" : "border-slate-700 text-slate-400 hover:border-slate-600"}`}
              >
                {policy === "STANDARD" ? "Standard Positive" : "Enhanced Reserve"}
              </button>
            ))}
          </div>
          <div className="mt-2 rounded border border-slate-800 bg-slate-950/50 px-2 py-1.5 text-[8px] text-slate-500">
            Policy changes are rejected while a physical pressure fault is latched.
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-[10px] font-semibold text-slate-300">Safety test & recovery</div>
          <div className="text-[8px] text-slate-600">Simulation controls — not a real actuator interface</div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[9px]">
          <button type="button" disabled={pending("STRESS_TEST_PRESSURE")} onClick={() => onCommand({ action: "STRESS_TEST_PRESSURE" })} className="rounded border border-rose-500/50 bg-rose-500/5 px-2 py-2 text-rose-300 hover:bg-rose-500/10 disabled:opacity-50">{pending("STRESS_TEST_PRESSURE") ? "Injecting…" : "Inject Pressure Fault"}</button>
          <button type="button" disabled={pending("RESTORE_PRESSURE")} onClick={() => onCommand({ action: "RESTORE_PRESSURE" })} className="rounded border border-emerald-500/50 bg-emerald-500/5 px-2 py-2 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50">{pending("RESTORE_PRESSURE") ? "Restoring…" : "Restore / Re-arm Positive Lock"}</button>
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2 text-[10px] font-semibold text-slate-300">Emergency ventilation policies</div>
        <div className="space-y-2">
          {emergencyOptions.map(({ mode, title, detail }) => (
            <button
              type="button"
              key={mode}
              disabled={pending("EMERGENCY_MODE")}
              onClick={() => onCommand({ action: "EMERGENCY_MODE", mode })}
              className={`w-full rounded-lg border px-3 py-2 text-left disabled:opacity-50 ${emergencyMode === mode ? "border-rose-400 bg-rose-500/15" : "border-slate-700 bg-slate-950/30 hover:border-slate-600"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-[10px] font-semibold ${emergencyMode === mode ? "text-rose-200" : "text-slate-300"}`}>{title}</span>
                {emergencyMode === mode && <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[8px] font-mono text-rose-300">ACTIVE</span>}
              </div>
              <div className="mt-1 text-[8px] leading-relaxed text-slate-600">{detail}</div>
            </button>
          ))}
        </div>
        {emergencyMode && <button type="button" disabled={pending("CLEAR_EMERGENCY_MODE")} onClick={() => onCommand({ action: "CLEAR_EMERGENCY_MODE" })} className="mt-2 w-full rounded border border-slate-600 px-2 py-2 text-[9px] text-slate-300 hover:bg-slate-800/50 disabled:opacity-50">{pending("CLEAR_EMERGENCY_MODE") ? "Clearing…" : "Clear Emergency Mode & Return to Arbitration"}</button>}
      </div>
    </div>
  );
}

function EnergyPanel({ className, roi, compact = false }: { className?: string; roi: RoiState; compact?: boolean }) {
  const vnd = new Intl.NumberFormat("en-US", { style: "currency", currency: "VND", maximumFractionDigits: 0 }).format(roi.financial_savings_vnd);
  const provenance = roi.baseline_provenance;
  const eui = provenance.site_eui_kwh_m2_year;
  const annualMwh = provenance.annual_site_energy_kwh != null ? provenance.annual_site_energy_kwh / 1000 : null;
  const sourceEui = provenance.source_eui_kwh_m2_year;
  const peak = provenance.annual_peak_electric_kw;
  const tier = provenance.calibration_tier || "NONE";
  const isHourly = provenance.reference_resolution === "HOURLY";
  const isMonthly = provenance.reference_resolution === "MONTHLY_MEAN";
  const isFullAnnualTabular = tier === "FULL_ANNUAL_TABULAR";
  const simulationHours = provenance.simulation_hours ?? (typeof provenance.metadata?.simulation_hours === "number" ? provenance.metadata.simulation_hours : null);
  const annualPeakTimestamp = provenance.annual_peak_timestamp ?? null;
  const calibrationClass = provenance.calibrated ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-300" : "border-amber-500/40 bg-amber-500/5 text-amber-200";
  const referenceLabel = isHourly ? "OpenStudio Hourly Ref." : isMonthly ? "OpenStudio Monthly Mean" : provenance.calibrated ? "OpenStudio Annual Only" : "Reference Load";
  const deltaLabel = isHourly ? "Instant Δ" : isMonthly ? "Δ vs Month Mean" : "Instant Δ";
  const metadata = provenance.metadata ?? {};
  const weather = typeof metadata.weather_file === "string" ? metadata.weather_file : null;
  const comfort = typeof metadata.comfort === "object" && metadata.comfort !== null ? metadata.comfort as Record<string, unknown> : {};
  const heatingUnmet = typeof comfort.occupied_heating_unmet_hours === "number" ? comfort.occupied_heating_unmet_hours : null;
  const coolingUnmet = typeof comfort.occupied_cooling_unmet_hours === "number" ? comfort.occupied_cooling_unmet_hours : null;
  const totalUnmet = heatingUnmet != null || coolingUnmet != null ? (heatingUnmet ?? 0) + (coolingUnmet ?? 0) : (typeof metadata.total_unmet_hours === "number" ? metadata.total_unmet_hours : null);
  const qualityFlags = Array.isArray(metadata.quality_flags)
    ? metadata.quality_flags
        .filter((flag): flag is Record<string, unknown> => typeof flag === "object" && flag !== null)
        .map((flag) => ({
          level: typeof flag.level === "string" ? flag.level : typeof flag.severity === "string" ? flag.severity : "INFO",
          message: typeof flag.message === "string" ? flag.message : "OpenStudio import note",
        }))
    : [];
  const hvacSummary = provenance.hvac_design && typeof provenance.hvac_design === "object"
    ? provenance.hvac_design
    : typeof metadata.hvac_design === "object" && metadata.hvac_design !== null
      ? metadata.hvac_design as Record<string, unknown>
      : typeof metadata.hvac_summary === "object" && metadata.hvac_summary !== null
        ? metadata.hvac_summary as Record<string, unknown>
        : {};
  const designSupply = typeof hvacSummary.design_supply_airflow_m3s === "number" ? `${hvacSummary.design_supply_airflow_m3s.toFixed(2)} m³/s` : null;
  const fanPower = typeof hvacSummary.fan_design_power_kw === "number" ? `${hvacSummary.fan_design_power_kw.toFixed(2)} kW` : null;
  const coolingCapacity = typeof hvacSummary.cooling_coil_capacity_kw === "number" ? `${hvacSummary.cooling_coil_capacity_kw.toFixed(1)} kW` : null;
  const outdoorAir = typeof hvacSummary.system_outdoor_airflow_m3s === "number" ? `${hvacSummary.system_outdoor_airflow_m3s.toFixed(2)} m³/s` : null;

  return (
    <div className={`${className ?? ""} rounded-xl border border-slate-800 bg-slate-900/65 p-4`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><Zap className="h-4 w-4 text-amber-400" /><div><h2 className="text-sm font-semibold">Energy & ROI Ledger</h2><p className="text-[9px] text-slate-500">OpenStudio-calibrated baseline + end-use-scaled B.E.A.M. control effect</p></div></div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`rounded border px-2 py-1 text-[8px] font-mono ${calibrationClass}`}>{provenance.calibrated ? `OPENSTUDIO ${tier}` : "PROTOTYPE REFERENCE"}</span>
          {provenance.calibrated && <span className={`rounded border px-2 py-1 text-[8px] font-mono ${isHourly ? "border-cyan-500/40 text-cyan-700 dark:text-cyan-300" : isFullAnnualTabular ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-300" : "border-amber-500/40 text-amber-700 dark:text-amber-300"}`}>{isHourly ? "8760/8784 HOURLY" : isFullAnnualTabular ? `${simulationHours ?? 8760}h FULL ANNUAL TABULAR` : isMonthly ? "MONTHLY-MEAN LIVE REF" : "ANNUAL METRICS ONLY"}</span>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-4">
        <Metric label={provenance.calibrated ? "B.E.A.M. Facility Est." : "Modeled Live Load"} value={`${roi.beam_load_kw.toFixed(1)} kW`} />
        <Metric label={referenceLabel} value={`${roi.baseline_kw.toFixed(1)} kW`} />
        <Metric label={deltaLabel} value={`${roi.instant_savings_percent >= 0 ? "+" : ""}${roi.instant_savings_percent.toFixed(1)}%`} />
        <Metric label="Session Net Avoided" value={`${roi.total_kwh_saved.toFixed(3)} kWh`} />
      </div>

      {provenance.calibrated && (
        <div className="mt-2 grid grid-cols-1 gap-2 text-[8px] sm:grid-cols-3">
          <Metric label="OS control-eligible envelope" value={roi.control_eligible_end_use_fraction != null ? `${(roi.control_eligible_end_use_fraction * 100).toFixed(1)}% of annual electricity` : "End-use breakdown unavailable"} />
          <Metric label="Modeled control effect" value={`${roi.modeled_control_fraction >= 0 ? "+" : ""}${(roi.modeled_control_fraction * 100).toFixed(1)}% within eligible loads`} />
          <Metric label="Applied facility Δ" value={`${roi.applied_control_delta_kw >= 0 ? "+" : ""}${roi.applied_control_delta_kw.toFixed(2)} kW`} />
        </div>
      )}

      <div className="mt-3 h-32">
        {roi.history.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={roi.history.slice(-100)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#64748b" strokeOpacity={0.22} />
              <XAxis dataKey="time_label" hide />
              <YAxis tick={{ fontSize: 9, fill: "#64748b" }} width={38} />
              <Tooltip contentStyle={{ background: "var(--beam-tooltip-bg, #0f172a)", border: "1px solid #64748b", fontSize: 10 }} />
              <Legend wrapperStyle={{ fontSize: 9 }} />
              <Line type="monotone" dataKey="beam_load_kw" name="B.E.A.M. facility est." stroke="#16a34a" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="baseline_kw" name={isHourly ? "OpenStudio hourly" : isMonthly ? "OpenStudio monthly mean" : "Reference"} stroke="#ea580c" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : <div className="flex h-full items-center justify-center rounded border border-dashed border-slate-800 text-[9px] text-slate-600">Collecting live energy history…</div>}
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 text-[9px] sm:grid-cols-4">
        <Metric label="Site EUI" value={eui != null ? `${eui.toFixed(1)} kWh/m²·yr` : "Not calibrated"} />
        <Metric label="Annual Site Energy" value={annualMwh != null ? `${annualMwh.toFixed(1)} MWh` : "—"} />
        <Metric label="Reported Peak" value={peak != null ? `${peak.toFixed(1)} kW` : "—"} />
        <Metric label="Source EUI" value={sourceEui != null ? `${sourceEui.toFixed(1)} kWh/m²·yr` : "—"} />
      </div>

      {!compact && provenance.calibrated && provenance.monthly.length > 0 && (
        <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/25 p-2" open>
          <summary className="cursor-pointer select-none text-[10px] font-semibold text-slate-300">OpenStudio annual result · monthly profile & end uses</summary>
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2 2xl:grid-cols-3">
            <div>
              <div className="mb-1 text-[8px] uppercase tracking-wide text-slate-500">Monthly electricity & reported peak</div>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={provenance.monthly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#64748b" strokeOpacity={0.18}/>
                    <XAxis dataKey="month" tick={{ fontSize: 8, fill: "#64748b" }}/>
                    <YAxis yAxisId="energy" tick={{ fontSize: 8, fill: "#64748b" }} width={40} tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`}/>
                    <YAxis yAxisId="peak" orientation="right" tick={{ fontSize: 8, fill: "#64748b" }} width={32} tickFormatter={(v) => `${Math.round(Number(v))}`}/>
                    <Tooltip contentStyle={{ background: "var(--beam-tooltip-bg, #0f172a)", border: "1px solid #64748b", fontSize: 9 }}/>
                    <Legend wrapperStyle={{ fontSize: 8 }}/>
                    <Bar yAxisId="energy" dataKey="electricity_kwh" name="Electricity kWh" fill="#0891b2" radius={[2,2,0,0]}/>
                    <Line yAxisId="peak" type="monotone" dataKey="peak_kw" name="Peak kW" stroke="#ea580c" strokeWidth={1.5} dot={{ r: 1.5 }}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div>
              <div className="mb-1 text-[8px] uppercase tracking-wide text-slate-500">Annual electrical end uses</div>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={provenance.end_uses_electricity.filter((d) => d.kwh > 0)} layout="vertical" margin={{ left: 4, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#64748b" strokeOpacity={0.18}/>
                    <XAxis type="number" tick={{ fontSize: 8, fill: "#64748b" }} tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`}/>
                    <YAxis type="category" dataKey="end_use" width={92} tick={{ fontSize: 8, fill: "#64748b" }}/>
                    <Tooltip formatter={(v) => [`${Number(v).toLocaleString(undefined, {maximumFractionDigits: 0})} kWh`, "Annual"]} contentStyle={{ background: "var(--beam-tooltip-bg, #0f172a)", border: "1px solid #64748b", fontSize: 9 }}/>
                    <Bar dataKey="kwh" fill="#7c3aed" radius={[0,2,2,0]}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            {provenance.monthly.some(p => p.cooling_mbtu != null || p.outdoor_temp_c != null) && (<div>
              <div className="mb-1 text-[8px] uppercase tracking-wide text-slate-500">Monthly cooling load & outdoor temperature</div>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={provenance.monthly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#64748b" strokeOpacity={0.18}/>
                    <XAxis dataKey="month" tick={{ fontSize: 8, fill: "#64748b" }}/>
                    <YAxis yAxisId="cooling" tick={{ fontSize: 8, fill: "#64748b" }} width={34} tickFormatter={(v) => `${Number(v).toFixed(0)}`}/>
                    <YAxis yAxisId="temp" orientation="right" tick={{ fontSize: 8, fill: "#64748b" }} width={32} tickFormatter={(v) => `${Number(v).toFixed(0)}°`}/>
                    <Tooltip contentStyle={{ background: "var(--beam-tooltip-bg, #0f172a)", border: "1px solid #64748b", fontSize: 9 }}/>
                    <Legend wrapperStyle={{ fontSize: 8 }}/>
                    <Bar yAxisId="cooling" dataKey="cooling_mbtu" name="Cooling MBtu" fill="#2563eb" radius={[2,2,0,0]}/>
                    <Line yAxisId="temp" type="monotone" dataKey="outdoor_temp_c" name="Outdoor °C" stroke="#16a34a" strokeWidth={1.5} dot={{ r: 1.5 }}/>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>)}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[8px] sm:grid-cols-4">
            <Metric label="EnergyPlus Run" value={simulationHours != null ? `${simulationHours.toFixed(0)} h` : "—"}/>
            <Metric label="OpenStudio Area" value={provenance.floor_area_m2 != null ? `${provenance.floor_area_m2.toFixed(0)} m²` : "—"}/>
            <Metric label="OS Conditioned Area" value={provenance.conditioned_floor_area_m2 != null ? `${provenance.conditioned_floor_area_m2.toFixed(0)} m²` : "—"}/>
            <Metric label="Occupied Unmet Hours" value={totalUnmet != null ? `${totalUnmet.toFixed(1)} h` : "—"}/>
            <Metric label="Annual Peak Time" value={annualPeakTimestamp ?? "—"}/>
            <Metric label="Weather" value={weather ? "Ho Chi Minh City TMYx" : "—"}/>
            <Metric label="Design Supply" value={designSupply ?? "—"}/>
            <Metric label="System OA" value={outdoorAir ?? "—"}/>
          </div>
          {(fanPower || coolingCapacity) && (
            <div className="mt-2 grid grid-cols-1 gap-2 text-[8px] sm:grid-cols-2">
              <Metric label="EnergyPlus Design Fan" value={fanPower ?? "—"}/>
              <Metric label="Cooling Coil Capacity" value={coolingCapacity ?? "—"}/>
            </div>
          )}
          {qualityFlags.length > 0 && (
            <div className="mt-2 rounded border border-slate-800/80 bg-slate-950/20 p-2">
              <div className="mb-1 text-[8px] font-semibold uppercase tracking-wide text-slate-500">Calibration quality checks</div>
              <div className="space-y-1">
                {qualityFlags.slice(0, 6).map((flag, idx) => {
                  const flagClass = flag.level === "PASS" ? "text-emerald-700 dark:text-emerald-300" : flag.level === "CHECK" ? "text-amber-800 dark:text-amber-300" : "text-slate-600 dark:text-slate-400";
                  return <div key={`${flag.level}-${idx}`} className={`text-[8px] leading-relaxed ${flagClass}`}><span className="font-mono font-semibold">{flag.level}</span> · {flag.message}</div>;
                })}
              </div>
            </div>
          )}
        </details>
      )}

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-slate-500">
        <span>{vnd}</span><span>{roi.co2_reduction_kg.toFixed(3)} kg CO₂ session net avoided</span><span>Rolling peak Δ {roi.peak_reduction_percent.toFixed(1)}%</span><span>B.E.A.M. geometric conditioned area {roi.conditioned_floor_area_m2.toFixed(0)} m²</span>
      </div>

      {provenance.calibrated && isHourly ? (
        <div className="mt-2 rounded border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5 text-[9px] text-emerald-700 dark:text-emerald-200/80">Full hourly calibration is active. The facility reference comes from imported 8760/8784 OpenStudio/EnergyPlus electricity data. B.E.A.M. maps its modeled control ratio only onto the OpenStudio HVAC/lighting end-use envelope, preserving unrelated facility loads.</div>
      ) : provenance.calibrated && isMonthly ? (
        <div className="mt-2 rounded border border-emerald-500/25 bg-emerald-500/5 px-2 py-1.5 text-[9px] text-emerald-800 dark:text-emerald-200/80"><b>{isFullAnnualTabular ? "Full 8760-hour EnergyPlus annual simulation is calibrated." : "Annual OpenStudio calibration is active."}</b> Site/source EUI, end uses, space design loads, HVAC design, monthly energy and reported peaks come from imported simulation results. The tabular report is an annual summary, not an hourly meter stream, so the live facility anchor remains the current month <b>mean kW</b>. B.E.A.M. applies its modeled control ratio only to the calibrated control-eligible end-use envelope. Import <code>eplusout.sql</code> later only if an hourly facility trace is needed.</div>
      ) : provenance.calibrated ? (
        <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5 text-[9px] text-amber-800 dark:text-amber-200/80">Annual OpenStudio metrics are loaded, but no monthly/hourly reference exists. Live ROI remains counterfactual-model based.</div>
      ) : (
        <div className="mt-2 rounded border border-amber-500/25 bg-amber-500/5 px-2 py-1.5 text-[9px] text-amber-800 dark:text-amber-200/80">Annual EUI and calibrated facility reference are withheld until an OpenStudio/EnergyPlus result is imported.</div>
      )}
    </div>
  );
}

function EnergyAISupervisorPanel({ state }: { state: EnergyAIState }) {
  const statusClass = state.status === "SAFETY_OVERRIDE" ? "text-rose-300" : state.enabled ? "text-violet-200" : "text-slate-500";
  return (
    <div className="rounded-xl border border-violet-500/20 bg-slate-900/65 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2"><Brain className="mt-0.5 h-4 w-4 text-violet-400" /><div><h2 className="text-sm font-semibold">B.E.A.M. Energy AI Supervisor</h2><p className="text-[9px] text-slate-500">Constraint-aware supervisory optimizer · room setbacks · anticipatory conditioning · no safety bypass</p></div></div>
        <div className="text-right"><div className={`font-mono text-xs ${statusClass}`}>{state.status}</div><div className="text-[8px] text-slate-600">score {state.score.toFixed(0)}/100</div></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[9px]">
        <Metric label="Supervisor" value={state.enabled ? "Enabled" : "Disabled"} />
        <Metric label="Instant avoided" value={`${state.estimated_avoided_kw >= 0 ? "+" : ""}${state.estimated_avoided_kw.toFixed(2)} kW`} />
      </div>
      <div className="mt-3">
        <div className="mb-1 text-[9px] uppercase tracking-wide text-slate-600">Current decisions</div>
        {state.actions.length ? <div className="max-h-28 space-y-1 overflow-auto">
          {state.actions.slice(0, 8).map((a) => <div key={`${a.room_id}-${a.action}`} className="flex items-center justify-between gap-2 rounded border border-slate-800 bg-slate-950/45 px-2 py-1 text-[9px]"><span className="truncate text-slate-300">{a.room}</span><span className="shrink-0 font-mono text-violet-300">{a.action}</span></div>)}
        </div> : <div className="rounded border border-slate-800 bg-slate-950/35 px-2 py-1.5 text-[9px] text-slate-600">No optimization actions required at this instant.</div>}
      </div>
      <div className="mt-2 text-[8px] text-slate-600">Priority: safety → emergency → room manual override → clinical/HIS demand → energy optimization.</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-md border border-slate-800 bg-slate-950/60 px-2 py-1.5"><div className="text-slate-500">{label}</div><div className="mt-0.5 font-mono text-slate-200">{value}</div></div>;
}

function AuditPanel({ incidents }: { incidents: IncidentEvent[] }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/65 p-4">
      <div className="mb-3 flex items-center gap-2"><Clock className="h-4 w-4 text-amber-400" /><h2 className="text-sm font-semibold">System Audit Trail</h2></div>
      <div className="max-h-44 overflow-auto">
        <table className="w-full text-left text-[10px]">
          <thead className="sticky top-0 bg-slate-900 text-slate-500"><tr><th className="py-1 pr-3">Time</th><th className="py-1 pr-3">Event</th><th className="py-1 pr-3">Actor</th><th className="py-1">Status</th></tr></thead>
          <tbody>{incidents.map((e) => <tr key={e.id} className="border-t border-slate-800"><td className="whitespace-nowrap py-1.5 pr-3 font-mono text-slate-500">{new Date(e.timestamp).toLocaleTimeString("en-GB", { hour12: false })}</td><td className="py-1.5 pr-3 text-slate-300">{e.type}</td><td className="py-1.5 pr-3 text-slate-400">{e.user}</td><td className={`py-1.5 font-mono ${e.status === "ALARM" ? "text-rose-300" : e.status === "ACTION" ? "text-emerald-300" : "text-slate-500"}`}>{e.status}</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}

function RoomControlModal({
  room,
  onClose,
  onMode,
  onTargets,
  onResetTargets,
  modePending,
  targetsPending,
}: {
  room: Room;
  onClose: () => void;
  onMode: (mode: string) => void;
  onTargets: (targets: { temp_c: number; humidity: number; airflow_percent: number }) => Promise<CommandResult> | void;
  onResetTargets: () => Promise<CommandResult> | void;
  modePending: boolean;
  targetsPending: boolean;
}) {
  const [manualTemp, setManualTemp] = useState(room.manual_targets?.temp_c ?? room.target_temp_c);
  const [manualRh, setManualRh] = useState(room.manual_targets?.humidity ?? room.target_humidity);
  const inferredAirflowPercent = room.max_airflow_m3h ? (room.target_airflow_m3h / room.max_airflow_m3h) * 100 : 70;
  const [manualAirflow, setManualAirflow] = useState(room.manual_targets?.airflow_percent ?? Math.max(30, Math.min(100, inferredAirflowPercent)));

  useEffect(() => {
    setManualTemp(room.manual_targets?.temp_c ?? room.target_temp_c);
    setManualRh(room.manual_targets?.humidity ?? room.target_humidity);
    const pct = room.max_airflow_m3h ? (room.target_airflow_m3h / room.max_airflow_m3h) * 100 : 70;
    setManualAirflow(room.manual_targets?.airflow_percent ?? Math.max(30, Math.min(100, pct)));
  }, [room.id]);

  return (
    <ModalShell onClose={onClose} width="max-w-3xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-cyan-500">{prettyCategory(room.category)}</div>
          <h3 className="text-xl font-semibold">{room.name}</h3>
          <p className="text-[10px] text-slate-500">OpenStudio-linked space · {room.area_m2.toFixed(1)} m² · digital-twin telemetry · source {room.telemetry_source}</p>
        </div>
        <StatusChip status={room.status} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-4">
        <Telemetry icon={<Thermometer className="h-4 w-4" />} label="Temperature" value={`${room.temp_c.toFixed(1)}°C`} target={`Target ${room.target_temp_c.toFixed(1)}°C`} />
        <Telemetry icon={<Droplets className="h-4 w-4" />} label="Humidity" value={`${room.humidity.toFixed(1)}%`} target={`Target ${room.target_humidity.toFixed(1)}%`} />
        <Telemetry icon={<Wind className="h-4 w-4" />} label="Airflow" value={`${Math.round(room.airflow_m3h)} m³/h`} target={`Target ${Math.round(room.target_airflow_m3h)} m³/h`} />
        <Telemetry icon={<Power className="h-4 w-4" />} label="Power" value={`${room.power_kw.toFixed(2)} kW`} target={`${room.damper_position.toFixed(0)}% damper`} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-4">
        <div className="rounded-md border border-slate-800 bg-slate-950/45 p-2"><div className="text-slate-500">Control source</div><div className="mt-1 font-mono text-slate-200">{room.control_source}</div></div>
        <div className="rounded-md border border-slate-800 bg-slate-950/45 p-2"><div className="text-slate-500">Occupancy</div><div className="mt-1 flex items-center gap-1 font-mono text-slate-200"><UserRound className="h-3.5 w-3.5 text-sky-400" />{room.occupancy}</div></div>
        <div className="rounded-md border border-slate-800 bg-slate-950/45 p-2"><div className="text-slate-500">Session utilization</div><div className="mt-1 font-mono text-slate-200">{room.session_utilization_percent.toFixed(1)}%</div></div>
        <div className="rounded-md border border-slate-800 bg-slate-950/45 p-2"><div className="text-slate-500">Power density</div><div className="mt-1 font-mono text-slate-200">{room.power_density_w_m2.toFixed(1)} W/m²</div></div>
      </div>

      {room.openstudio_space_calibration?.matched && <div className="mt-3 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2"><div><div className="text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">EnergyPlus calibrated room design</div><div className="text-[8px] text-slate-500">Annual 8760h tabular design data is mapped to this OpenStudio space; airflow is zone-flow area allocation where EnergyPlus reports one zone terminal for multiple spaces.</div></div><span className="rounded border border-emerald-500/30 px-2 py-1 text-[8px] font-mono text-emerald-700 dark:text-emerald-300">{room.openstudio_space_calibration.calibration_method ?? "ENERGYPLUS"}</span></div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[9px] sm:grid-cols-4">
          <Metric label="EnergyPlus Zone" value={room.openstudio_space_calibration.zone_name ?? "—"}/>
          <Metric label="Space Type" value={room.openstudio_space_calibration.space_type ?? "—"}/>
          <Metric label="Lighting Design" value={room.lighting_design_w_m2 != null ? `${room.lighting_design_w_m2.toFixed(1)} W/m²` : "—"}/>
          <Metric label="Plug Design" value={room.equipment_design_w_m2 != null ? `${room.equipment_design_w_m2.toFixed(1)} W/m²` : "—"}/>
          <Metric label="Design Airflow" value={`${Math.round(room.max_airflow_m3h)} m³/h`}/>
          <Metric label="Calibrated Minimum" value={room.calibrated_min_airflow_m3h != null ? `${Math.round(room.calibrated_min_airflow_m3h)} m³/h` : "—"}/>
          <Metric label="Fan Design Share" value={room.fan_design_kw != null ? `${room.fan_design_kw.toFixed(3)} kW` : "—"}/>
          <Metric label="Design People" value={room.design_people_capacity != null ? room.design_people_capacity.toFixed(1) : "—"}/>
        </div>
      </div>}

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div className="rounded-md border border-slate-800 bg-slate-950/45 p-2 text-cyan-500"><div className="text-[9px] uppercase tracking-wide text-slate-500">Temperature trend · live session</div><MiniSparkline points={room.trend} field="temp_c"/></div>
        <div className="rounded-md border border-slate-800 bg-slate-950/45 p-2 text-amber-500"><div className="text-[9px] uppercase tracking-wide text-slate-500">Power trend · live session</div><MiniSparkline points={room.trend} field="power_kw"/></div>
      </div>

      <div className="mt-3 rounded-md border px-3 py-2 text-[10px]" style={{borderColor: `${alarmStroke[room.alarm_severity]}88`, color: alarmStroke[room.alarm_severity], backgroundColor: `${alarmStroke[room.alarm_severity]}0d`}}>
        <div className="font-semibold">Alarm severity: {room.alarm_severity}</div>
        <div className="mt-0.5 text-slate-500">{room.alarm_reasons.length ? room.alarm_reasons.join(" · ") : "No active room-level alarm condition."}</div>
      </div>

      {room.category === "OPERATING_ROOM" && <div className="mt-4"><div className="text-[10px] uppercase tracking-wide text-slate-500">Configured OR capabilities</div><div className="mt-1 flex flex-wrap gap-1">{room.capabilities.map((c) => <span key={c} className="rounded border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-[9px] text-violet-500">{prettySpecialty(c)}</span>)}</div><p className="mt-1 text-[9px] text-slate-500">Capability profile is B.E.A.M. configuration, not inferred clinical metadata from OpenStudio.</p></div>}

      <div className="mt-5 border-t border-slate-800 pt-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><SlidersHorizontal className="h-4 w-4 text-cyan-500" />Room Manual Setup</div>
            <div className="mt-0.5 text-[10px] text-slate-500">Per-room targets override Energy AI/HIS optimization, but physical safety, emergency modes and active-OR airflow minimums remain authoritative.</div>
          </div>
          <span className={`rounded border px-2 py-1 text-[9px] font-mono ${room.manual_targets ? "border-amber-500/50 bg-amber-500/10 text-amber-500" : "border-emerald-500/40 bg-emerald-500/5 text-emerald-500"}`}>{room.manual_targets ? "ROOM TARGETS MANUAL" : "AUTO TARGETS"}</span>
        </div>

        {room.conditioned ? <>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <RoomTargetSlider label="Temperature target" suffix="°C" min={18} max={26} step={0.5} value={manualTemp} onChange={setManualTemp} />
            <RoomTargetSlider label="Relative humidity target" suffix="%" min={45} max={60} step={1} value={manualRh} onChange={setManualRh} />
            <RoomTargetSlider label="Airflow target" suffix="% design" min={30} max={100} step={5} value={manualAirflow} onChange={setManualAirflow} />
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-[9px] text-slate-500">For an active OR, airflow commands below the clinical hard minimum are automatically clamped by the backend.</div>
            <div className="flex gap-2">
              <button type="button" disabled={targetsPending || !room.manual_targets} onClick={() => { void onResetTargets(); }} className="flex items-center gap-1.5 rounded-md border border-slate-700 px-3 py-2 text-[10px] text-slate-400 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"><RotateCcw className="h-3.5 w-3.5" />Release to Auto</button>
              <button type="button" disabled={targetsPending} onClick={() => { void onTargets({ temp_c: manualTemp, humidity: manualRh, airflow_percent: manualAirflow }); }} className="rounded-md border border-cyan-500/60 bg-cyan-500/10 px-3 py-2 text-[10px] font-semibold text-cyan-600 disabled:cursor-wait disabled:opacity-50">{targetsPending ? "Applying…" : "Apply Room Targets"}</button>
            </div>
          </div>
        </> : <div className="rounded border border-slate-700 bg-slate-950/45 p-3 text-[10px] text-slate-500">This polygon is part of the OpenStudio floorplan but is not configured as an HVAC-controlled room.</div>}
      </div>

      <div className="mt-5 border-t border-slate-800 pt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div><div className="text-xs font-semibold">Manual Override / Room Operating Mode</div><div className="mt-0.5 text-[9px] text-slate-500">Auto / Balance releases the operating-mode override. Minimum/Shutdown are backend-blocked while an OR has an active surgical case.</div></div>
          <span className={`rounded border px-2 py-1 text-[8px] font-mono ${room.manual_mode ? "border-amber-500/50 bg-amber-500/10 text-amber-500" : "border-emerald-500/40 bg-emerald-500/5 text-emerald-500"}`}>{room.manual_mode ?? "AUTO"}</span>
        </div>
        {room.conditioned ? <div className="grid grid-cols-2 gap-2">{ROOM_MODES.map(([value, label]) => <button type="button" key={value} disabled={modePending} onClick={() => onMode(value)} className={`rounded-md border px-3 py-2 text-left text-[10px] disabled:cursor-wait disabled:opacity-50 ${room.manual_mode === value || (value === "BALANCE" && !room.manual_mode) ? "border-cyan-500/60 bg-cyan-500/10 text-cyan-600" : "border-slate-700 text-slate-300 hover:border-slate-600"}`}>{modePending ? `${label}…` : label}</button>)}</div> : null}
      </div>
    </ModalShell>
  );
}

function RoomTargetSlider({ label, suffix, min, max, step, value, onChange }: { label: string; suffix: string; min: number; max: number; step: number; value: number; onChange: (value: number) => void }) {
  return <div className="rounded-lg border border-slate-800 bg-slate-950/35 p-3"><div className="mb-2 flex items-center justify-between gap-2 text-[10px]"><span className="text-slate-500">{label}</span><span className="font-mono font-semibold text-cyan-600">{value.toFixed(step < 1 ? 1 : 0)}{suffix}</span></div><input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} className="w-full accent-cyan-500" /></div>;
}

function Telemetry({ icon, label, value, target }: { icon: React.ReactNode; label: string; value: string; target: string }) {
  return <div className="rounded-md border border-slate-800 bg-slate-950/55 p-2"><div className="flex items-center gap-1 text-slate-500">{icon}{label}</div><div className="mt-1 font-mono text-sm text-slate-200">{value}</div><div className="text-[9px] text-slate-600">{target}</div></div>;
}

function StatusChip({ status }: { status: RoomStatus }) {
  const p = statusStyle[status];
  return <span className="rounded-full border px-2 py-1 text-[9px] font-mono" style={{ color: p.stroke, borderColor: p.stroke, backgroundColor: `${p.fill}aa` }}>{p.label}</span>;
}

function ExternalCaseModal({ onClose, onSubmit, pending }: { onClose: () => void; onSubmit: (payload: Record<string, unknown>) => Promise<void> | void; pending: boolean }) {
  const [caseLabel, setCaseLabel] = useState("");
  const [procedure, setProcedure] = useState("");
  const [specialty, setSpecialty] = useState("GENERAL");
  const [urgency, setUrgency] = useState<Urgency>("URGENT");
  const [duration, setDuration] = useState(90);
  const [notes, setNotes] = useState("");
  return (
    <ModalShell onClose={onClose} width="max-w-xl">
      <div className="flex items-center gap-2"><Plus className="h-4 w-4 text-cyan-400" /><h3 className="text-base font-semibold">Add External Surgery Case</h3></div>
      <p className="mt-1 text-[10px] text-slate-500">Case enters the same validated HIS pipeline. AI ON schedules it automatically; AI OFF leaves it in the manual priority queue.</p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Case label (optional)"><input value={caseLabel} onChange={(e) => setCaseLabel(e.target.value)} maxLength={40} className="field" placeholder="e.g. EXT-TRAUMA-1" /></Field>
        <Field label="Urgency"><select value={urgency} onChange={(e) => setUrgency(e.target.value as Urgency)} className="field"><option>STAT</option><option>EMERGENCY</option><option>URGENT</option><option>ELECTIVE</option></select></Field>
        <Field label="Specialty"><select value={specialty} onChange={(e) => setSpecialty(e.target.value)} className="field">{SPECIALTIES.map((s) => <option key={s} value={s}>{prettySpecialty(s)}</option>)}</select></Field>
        <Field label="Estimated duration (min)"><input type="number" min={15} max={480} value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="field" /></Field>
        <div className="sm:col-span-2"><Field label="Procedure"><input value={procedure} onChange={(e) => setProcedure(e.target.value)} maxLength={80} className="field" placeholder="Procedure description" /></Field></div>
        <div className="sm:col-span-2"><Field label="Notes (optional)"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={300} className="field min-h-20" placeholder="Operational notes only; avoid unnecessary patient identifiers." /></Field></div>
      </div>
      <div className="mt-4 flex justify-end gap-2"><button type="button" onClick={onClose} className="rounded border border-slate-700 px-3 py-2 text-xs text-slate-400">Cancel</button><button type="button" disabled={pending || !procedure.trim() || duration < 15 || duration > 480} onClick={() => { void onSubmit({ case_label: caseLabel, procedure: procedure.trim(), specialty, urgency, estimated_duration_min: duration, notes }); }} className="rounded border border-cyan-500/60 bg-cyan-500/15 px-3 py-2 text-xs text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40">{pending ? "Validating…" : "Insert into HIS"}</button></div>
    </ModalShell>
  );
}

function ManualScheduleModal({ caseItem, rooms, onClose, onSubmit, pending }: { caseItem: HISCase; rooms: Record<string, Room>; onClose: () => void; onSubmit: (roomId: string, start: string) => Promise<void> | void; pending: boolean }) {
  const eligible = caseItem.eligible_room_ids.map((id) => rooms[id]).filter(Boolean);
  const [roomId, setRoomId] = useState(eligible[0]?.id ?? "");
  const [start, setStart] = useState(localDateTimeInput(new Date(Date.now() + 10 * 60 * 1000)));
  return (
    <ModalShell onClose={onClose} width="max-w-lg">
      <div className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-rose-400" /><h3 className="text-base font-semibold">Manual OR Allocation</h3></div>
      <div className="mt-3 rounded border border-rose-500/30 bg-rose-500/5 p-3 text-[10px]"><div className="font-semibold text-slate-200">{caseItem.case_label} · {caseItem.procedure}</div><div className="mt-1 text-slate-400">{caseItem.urgency} · {prettySpecialty(caseItem.specialty)} · {caseItem.estimated_duration_min} min</div></div>
      <div className="mt-4 space-y-3">
        <Field label="Eligible operating room"><select value={roomId} onChange={(e) => setRoomId(e.target.value)} className="field">{eligible.map((r) => <option key={r.id} value={r.id}>{r.name} · {r.capabilities.map(prettySpecialty).join(", ")}</option>)}</select></Field>
        <Field label="Start time"><input type="datetime-local" value={start} min={localDateTimeInput(new Date())} onChange={(e) => setStart(e.target.value)} className="field" /></Field>
        <p className="text-[9px] text-slate-500">Backend will reject past times, specialty mismatch, overlap, and the required {18}-minute turnover window.</p>
      </div>
      <div className="mt-4 flex justify-end gap-2"><button type="button" onClick={onClose} className="rounded border border-slate-700 px-3 py-2 text-xs text-slate-400">Cancel</button><button type="button" disabled={pending || !roomId || !start} onClick={() => { void onSubmit(roomId, start); }} className="rounded border border-rose-500/60 bg-rose-500/15 px-3 py-2 text-xs text-rose-200 disabled:opacity-40">{pending ? "Validating…" : "Validate & Schedule"}</button></div>
    </ModalShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-1 block text-[10px] text-slate-400">{label}</span>{children}</label>;
}

function ModalShell({ onClose, width, children }: { onClose: () => void; width: string; children: React.ReactNode }) {
  const target = document.fullscreenElement ?? document.body;
  return createPortal(
    <div className="beam-modal-backdrop fixed inset-0 z-[220] flex items-center justify-center p-3 backdrop-blur-sm sm:p-4" onMouseDown={onClose}>
      <div className={`w-full ${width} max-h-[92dvh] overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl sm:p-5`} onMouseDown={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} className="float-right rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200"><X className="h-4 w-4" /></button>
        {children}
      </div>
    </div>,
    target,
  );
}

export default App;
