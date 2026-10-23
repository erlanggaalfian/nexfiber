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

export type Me = { id: number; username: string; full_name: string; role: string; permissions: string[] };

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

export type OnuRow = {
  id: number; serial_number: string; name: string | null; customer_name: string | null;
  customer_id: string | null; olt_id: number; olt_name: string; slot: number; port: number;
  onu_index: number | null; onu_type: string | null; status: string; config_state: string;
  admin_state: string; rx_power_dbm: number | null; olt_rx_power_dbm: number | null;
  speed_profile_name: string | null; last_seen_at: string | null; last_down_at: string | null;
  last_down_reason: string | null;
};

export type OnuDetail = OnuRow & {
  pon_port_id: number; description: string | null; address: string | null; phone: string | null;
  tx_power_dbm: number | null; temperature_c: number | null; distance_m: number | null;
  mac_address: string | null; ip_address: string | null; vlan_id: number | null;
  speed_profile_id: number | null; line_profile_id: string | null; srv_profile_id: string | null;
  software_version: string | null; registered_at: string | null;
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

export type Vlan = { id: number; olt_id: number | null; vlan_id: number; name: string; type: string; description: string | null };

export type SpeedProfile = {
  id: number; name: string; download_kbps: number; upload_kbps: number; olt_id: number | null;
  line_profile_id: string | null; srv_profile_id: string | null;
};

export type Job = {
  id: number; job_type: string; status: string; olt_id: number | null; onu_id: number | null;
  created_at: string; started_at: string | null; finished_at: string | null;
  error_message: string | null; error_code: string | null; result: Record<string, unknown> | null;
};

export type Thresholds = { warn: number; crit: number };

export type Dashboard = {
  action: { los_over_15m: number; pending_authorization: number; olt_poll_failed: number };
  rx_histogram: Partial<Record<"normal" | "warn" | "bad", number>>;
  rx_threshold: Thresholds;
  busiest_pon_ports: { pon_port_id: number; olt_id: number; olt_name: string; slot: number; port: number; used: number; capacity: number }[];
  onu_by_status: Record<string, number>;
  olt_count: number;
  activated_today: number;
  last_poll_at: string | null;
};
