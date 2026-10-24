const TOKEN_KEY = "token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ");
  return "";
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers,
      body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    });
  } catch {
    throw new ApiError(0, "API tidak dapat dihubungi");
  }
  if (res.status === 401 && token) {
    setToken(null);
    location.assign("/login");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detailText(body.detail) || `HTTP ${res.status} dari API`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const qs = (params: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

/** Query string yang mengulang kunci untuk nilai banyak (`?signal=weak&signal=los`),
 *  bentuk yang dipahami FastAPI untuk parameter list. */
export const qsMulti = (params: Record<string, string | number | string[] | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((item) => item !== "" && p.append(k, String(item)));
    else if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
};

/** Unduh file dari endpoint yang butuh Authorization — <a href> biasa tidak mengirim token. */
export async function download(path: string, fallbackName: string) {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detailText(body.detail) || `HTTP ${res.status} dari API`);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1];
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name ?? fallbackName;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export type Role = "superadmin" | "admin" | "user";
export type Me = {
  id: number; username: string; full_name: string; role: Role; admin_id: number | null; must_change_password: boolean;
};

export type Olt = {
  id: number; name: string; host: string; vendor: string; model: string;
  firmware_version: string | null; cli_protocol: string; cli_port: number; cli_username: string;
  snmp_port: number; pon_port_count: number; max_onu_per_port: number; location: string | null;
  status: string; last_sync_at: string | null; last_error: string | null; is_active: boolean;
};

export type PonPort = {
  id: number; slot: number; port: number; ifindex: number | null; oper_state: string | null;
  onu_count: number; capacity: number; last_sync_at: string | null;
};

/** Satu kartu/board OLT (olts.cards JSONB), tab Konfigurasi Detail OLT. */
export type OltCard = {
  slot: number; cfg_type: string | null; real_type: string | null; port_count: number | null;
  hardware_version: string | null; software_version: string | null; status: string | null;
  cpu_pct: number | null; ram_pct: number | null;
};

/** GET /api/olts/{id}/detail — seluruh halaman Detail OLT dalam satu panggilan (PRD 3.4.7). */
export type OltDetail = Olt & {
  owner_id: number; owner_name: string; access_user_ids: number[]; onu_count: number;
  onu_by_status: Record<string, number>;
  cpu_pct: number | null; ram_pct: number | null; temperature_c: number | null;
  uptime_seconds: number | null; software_version: string | null;
  cards: OltCard[]; pon_ports: PonPort[]; uplink_ports: string[];
};

export type RxBucketFilter = "good" | "fair" | "weak" | "critical" | "los";

export type OnuRow = {
  id: number; serial_number: string; name: string | null; customer_name: string | null;
  customer_id: string | null; olt_id: number; olt_name: string; slot: number; port: number;
  onu_index: number | null; onu_type: string | null; status: string; config_state: string;
  admin_state: string; rx_power_dbm: number | null; olt_rx_power_dbm: number | null;
  download_profile_name: string | null; upload_profile_name: string | null;
  vlan_number: number | null; zone_name: string | null;
  splitter_name: string | null; last_seen_at: string | null; last_down_at: string | null;
  last_down_reason: string | null;
};

export type OnuDetail = OnuRow & {
  pon_port_id: number; description: string | null; address: string | null; phone: string | null;
  contact: string | null; external_id: string | null;
  tx_power_dbm: number | null; temperature_c: number | null; voltage_v: number | null;
  distance_m: number | null; mac_address: string | null; ip_address: string | null;
  vlan_id: number | null; zone_id: number | null; splitter_id: number | null;
  splitter_port: number | null;
  download_speed_profile_id: number | null; upload_speed_profile_id: number | null;
  line_profile_id: string | null; srv_profile_id: string | null;
  software_version: string | null; hardware_version: string | null;
  onu_mode: string | null; wan_mode: string | null; mgmt_ip_mode: string | null;
  pppoe_username: string | null; latitude: number | null; longitude: number | null;
  registered_at: string | null;
};

/** Hasil POST /api/onus/bulk — satu job per ONU, jadi hasilnya per serial. */
export type BulkActionResult = {
  items: { serial_number: string; job_id: number | null; error: string | null }[];
  queued: number;
  failed: number;
};

export type Page<T> = { items: T[]; total: number; page: number; size: number };

export type PendingOnu = {
  id: number; olt_id: number; olt_name: string; pon_port_id: number; slot: number; port: number;
  serial_number: string; onu_type: string | null; first_seen_at: string; last_seen_at: string;
};

export type SignalPoint = {
  sampled_at: string; rx_power_dbm: number | null; tx_power_dbm: number | null;
  olt_rx_power_dbm: number | null; status: string;
};

export type OnuLog = {
  id: number; created_at: string; username: string | null; action: string; success: boolean;
  job_id: number | null; raw_command: string | null; raw_output: string | null;
};

export type Vlan = {
  id: number; olt_id: number | null; vlan_id: number; name: string; type: string;
  description: string | null; gemport: number | null; tag_action: string;
  user_vlan: number | null; uplink_ports: Record<string, "tagged" | "untagged">;
  is_active: boolean;
};

export type SpeedProfile = {
  id: number; name: string; direction: "download" | "upload"; speed_kbps: number;
  olt_id: number | null; device_profile_id: string | null;
};

/** Baris tabel Settings -> Speed Profile (GET /api/speed-profiles, Fase B4). */
export type SpeedProfileRow = SpeedProfile & {
  olt_name: string | null; vlan_db_id: number | null; vlan_id: number | null;
  vlan_name: string | null; description: string | null; is_active: boolean; onu_count: number;
};

export type Job = {
  id: number; job_type: string; status: string; olt_id: number | null; onu_id: number | null;
  created_at: string; started_at: string | null; finished_at: string | null;
  error_message: string | null; error_code: string | null; result: Record<string, unknown> | null;
};

/** PRD 3.4.15 /logs. */
export type LogCategory = "authorize" | "reboot" | "service" | "delete" | "olt" | "user" | "login";
export type LogRow = {
  id: number; created_at: string; username: string | null; action: string; category: LogCategory;
  olt_id: number | null; olt_name: string | null; onu_id: number | null; onu_serial: string | null;
  entity_type: string; entity_id: string | null; success: boolean;
  raw_command: string | null; raw_output: string | null;
};
export type LogPage = { items: LogRow[]; total: number; page: number; size: number };

export type OltRow = Olt & {
  owner_id: number; owner_name: string; access_user_ids: number[];
  onu_count: number; onu_online: number;
  cpu_pct: number | null; ram_pct: number | null; temperature_c: number | null;
};

export type Dashboard = {
  olt_by_status: Record<string, number>;
  onu_by_status: Record<string, number>;
  onu_by_signal: Record<string, number>;
  unconfigured: number;
  last_poll_at: string | null;
  olts: OltRow[];
  recent_activity: LogRow[];
};

export type SystemStatus = {
  worker_alive: boolean;
  worker_heartbeat_at: string | null;
  jobs_pending: number;
  last_poll_at: string | null;
};

export type Zone = {
  id: number; owner_id: number; name: string; external_id: string | null;
  latitude: number | null; longitude: number | null; splitter_count: number; onu_count: number;
};

export type OnuType = {
  id: number; pon_type: string; name: string; eth_ports: number; wifi_ssids: number;
  voip_ports: number; catv: boolean; capability: string; allow_custom_profiles: boolean;
  is_active: boolean; onu_count: number;
};

export type Splitter = {
  id: number; name: string; code: string | null; type: string; ratio: string | null;
  capacity: number | null; zone_id: number | null; zone_name: string | null;
  parent_id: number | null; parent_name: string | null; olt_id: number | null;
  pon_port_id: number | null; location: string | null; latitude: number | null;
  longitude: number | null; insertion_loss_db: number | null; notes: string | null;
  onu_count: number;
};

export type SplitterDetail = Splitter & {
  onus: { id: number; serial_number: string; name: string | null; customer_name: string | null; splitter_port: number | null }[];
};

/** Preset Form Otorisasi (PRD 3.4.4 "Gunakan preset"). */
export type OnuPreset = {
  id: number; owner_id: number; name: string; onu_type_id: number; vlan: number | null;
  download_profile: string | null; upload_profile: string | null;
  onu_mode: "routing" | "bridging"; wan_mode: "webpage" | "dhcp" | "static" | "pppoe";
  zone_id: number | null; splitter_id: number | null;
};