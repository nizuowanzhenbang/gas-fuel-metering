import { http, PagedResult } from "./client";

// ------------------------------ 档案 ------------------------------
export interface GasSource {
  id: number;
  code: string;
  name: string;
  supplier: string;
  gas_type: "PIPELINE" | "LNG";
  contract_no: string | null;
  contract_base_price: number | null;
  daily_volume_plan_nm3: number | null;
  status: "ACTIVE" | "SUSPENDED" | "RETIRED";
  notes: string | null;
  created_at: string;
}

export interface MeteringStation {
  id: number;
  code: string;
  name: string;
  location: string | null;
  source_id: number | null;
  design_pressure_kpa: number;
  design_flow_min_nm3h: number;
  design_flow_max_nm3h: number;
  verified_until: string | null;
  status: "RUNNING" | "MAINTENANCE" | "OFFLINE";
  created_at: string;
}

export interface GCAnalyzer {
  id: number;
  code: string;
  model: string;
  serial_no: string | null;
  station_id: number | null;
  last_calibration_at: string | null;
  next_calibration_at: string | null;
  status: "RUNNING" | "CALIBRATING" | "FAULT" | "OFFLINE";
  created_at: string;
}

export const listGasSources = (params: Record<string, any> = {}) =>
  http.get<PagedResult<GasSource>>("/gas-sources", { params }).then((r) => r.data);
export const createGasSource = (body: Partial<GasSource>) =>
  http.post<GasSource>("/gas-sources", body).then((r) => r.data);
export const updateGasSource = (id: number, body: Partial<GasSource>) =>
  http.patch<GasSource>(`/gas-sources/${id}`, body).then((r) => r.data);
export const retireGasSource = (id: number) =>
  http.delete<GasSource>(`/gas-sources/${id}`).then((r) => r.data);

export const listStations = (params: Record<string, any> = {}) =>
  http.get<PagedResult<MeteringStation>>("/metering-stations", { params }).then((r) => r.data);
export const createStation = (body: Partial<MeteringStation>) =>
  http.post<MeteringStation>("/metering-stations", body).then((r) => r.data);
export const updateStation = (id: number, body: Partial<MeteringStation>) =>
  http.patch<MeteringStation>(`/metering-stations/${id}`, body).then((r) => r.data);

export const listGCs = (params: Record<string, any> = {}) =>
  http.get<PagedResult<GCAnalyzer>>("/gc-analyzers", { params }).then((r) => r.data);
export const createGC = (body: Partial<GCAnalyzer>) =>
  http.post<GCAnalyzer>("/gc-analyzers", body).then((r) => r.data);
export const updateGC = (id: number, body: Partial<GCAnalyzer>) =>
  http.patch<GCAnalyzer>(`/gc-analyzers/${id}`, body).then((r) => r.data);

// ------------------------------ 告警 ------------------------------
export interface Alert {
  id: number;
  alert_no: string;
  level: "INFO" | "WARN" | "CRITICAL";
  category: string;
  status: "OPEN" | "ACKED" | "RESOLVED";
  message: string;
  station_id: number | null;
  gc_id: number | null;
  source_id: number | null;
  payload_json: Record<string, any> | null;
  opened_at: string;
  acked_at: string | null;
  resolved_at: string | null;
}

export const listAlerts = (params: Record<string, any> = {}) =>
  http.get<PagedResult<Alert>>("/alerts", { params }).then((r) => r.data);
export const ackAlert = (id: number) =>
  http.post<Alert>(`/alerts/${id}/ack`).then((r) => r.data);
export const resolveAlert = (id: number) =>
  http.post<Alert>(`/alerts/${id}/resolve`).then((r) => r.data);

// ------------------------------ 对账 ------------------------------
export interface MeteringEvidence {
  station_id: number;
  source: string;
  sample_count: number;
  excluded_count: number;
  first_ts: string | null;
  last_ts: string | null;
  start_counter_nm3: number | null;
  end_counter_nm3: number | null;
  volume_nm3: number | null;
  issues: string[];
}

export interface BusinessPolicy { timezone: string; start_minute: number; version: string; latest_completed_date: string }
export interface BusinessWindow { policy: Omit<BusinessPolicy, "latest_completed_date">; start_utc: string; end_utc: string }
export const getBusinessPolicy = () => http.get<BusinessPolicy>("/reconciliation/policy").then(r => r.data);

export interface DailyReconResult {
  window: BusinessWindow;
  source_id: number;
  source_code: string;
  business_date: string;
  plant_volume_nm3: number;
  upstream_volume_nm3: number;
  absolute_diff_nm3: number;
  relative_diff_pct: number;
  tolerance_pct: number;
  verdict: "PASS" | "WARN" | "FAIL";
  reason: string;
  sample_count: number;
  stations: MeteringEvidence[];
}

export const reconcileDaily = (body: {
  source_id: number;
  business_date: string;
  upstream_volume_nm3: number;
}) => http.post<DailyReconResult>("/reconciliation/daily", body).then((r) => r.data);

export interface RunSummary {
  id: string; parent_run_id: string | null; source_id: number; business_date: string;
  created_at: string; created_by: string; snapshot_sha256: string;
  result: Pick<DailyReconResult, "plant_volume_nm3" | "upstream_volume_nm3" | "verdict">;
}
export interface ArchivedRun extends Omit<RunSummary, "result"> {
  snapshot: { result: RunSummary["result"]; delta_plant_nm3: number | null; [key: string]: unknown };
}
export const listReconciliationRuns = () => http.get<RunSummary[]>("/reconciliation/runs").then(r => r.data);
export const archiveReconciliation = (body: Parameters<typeof reconcileDaily>[0]) =>
  http.post<ArchivedRun>("/reconciliation/runs", body).then(r => r.data);
export const getReconciliationRun = (id: string) => http.get<ArchivedRun>(`/reconciliation/runs/${id}`).then(r => r.data);
export const verifyReconciliationRun = (id: string) => http.get<{ matches: boolean }>(`/reconciliation/runs/${id}/verify`).then(r => r.data);
export const recalculateReconciliationRun = (id: string) => http.post<ArchivedRun>(`/reconciliation/runs/${id}/recalculate`, {}).then(r => r.data);

// ------------------------------ 大屏 ------------------------------
export interface Overview {
  active_sources: number;
  running_stations: number;
  online_gc: number;
  last_24h_volume_nm3: number;
  latest_hhv_mj_nm3: number | null;
  open_alerts: { info: number; warn: number; critical: number };
  verification_due_30d: number;
}

export interface StationSnapshot {
  station_id: number;
  code: string;
  name: string;
  status: "RUNNING" | "MAINTENANCE" | "OFFLINE";
  source_code: string | null;
  latest_ts: string | null;
  latest_normal_volume_rate_nm3h: number | null;
  latest_pressure_kpa: number | null;
  latest_temperature_c: number | null;
  accumulated_volume_nm3: number | null;
  latest_hhv_mj_nm3: number | null;
  last_alert_level: "INFO" | "WARN" | "CRITICAL" | null;
}

export const getOverview = () =>
  http.get<Overview>("/dashboard/overview").then((r) => r.data);
export const getStationSnapshots = () =>
  http.get<StationSnapshot[]>("/dashboard/stations").then((r) => r.data);

// ------------------------------ 用户 ------------------------------
export interface UserRow {
  id: number;
  username: string;
  full_name: string;
  role: "ADMIN" | "OPERATOR" | "METER_ENG" | "ACCOUNTANT" | "VIEWER";
  is_active: boolean;
  created_at: string;
}

export const listUsers = (params: Record<string, any> = {}) =>
  http.get<PagedResult<UserRow>>("/users", { params }).then((r) => r.data);
export const createUser = (body: any) =>
  http.post<UserRow>("/users", body).then((r) => r.data);
export const updateUser = (id: number, body: any) =>
  http.patch<UserRow>(`/users/${id}`, body).then((r) => r.data);
export const deactivateUser = (id: number) =>
  http.delete<UserRow>(`/users/${id}`).then((r) => r.data);
export const resetUserPassword = (id: number, password: string) =>
  http.post<UserRow>(`/users/${id}/reset-password`, { password }).then((r) => r.data);

// ------------------------------ 读数（趋势用） ------------------------------
export interface MeteringReading {
  id: number;
  station_id: number;
  ts: string;
  actual_volume_rate_m3h: number;
  normal_volume_rate_nm3h: number;
  pressure_kpa: number;
  temperature_c: number;
  accumulated_volume_nm3: number;
  validity: string;
  source: "PRIMARY" | "BACKUP";
}

export const listMeteringReadings = (params: Record<string, any> = {}) =>
  http.get<PagedResult<MeteringReading>>("/readings/metering", { params }).then((r) => r.data);

// ------------------------------ 上传 ------------------------------
export interface UploadResponse {
  total: number;
  success: number;
  failed: number;
  rows: {
    row_index: number;
    business_date: string | null;
    source_code: string | null;
    plant_volume_nm3: number | null;
    upstream_volume_nm3: number | null;
    relative_diff_pct: number | null;
    verdict: string | null;
    error: string | null;
    error_code: string | null;
    window: BusinessWindow | null;
    stations: MeteringEvidence[];
  }[];
}

export const uploadUpstreamDaily = (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return http
    .post<UploadResponse>("/upload/upstream-daily", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
};
