/** Detail ONU — PRD 3.4.6, wireframe DESIGN 12.6. Satu halaman: header + kartu Sinyal /
 *  Pelanggan / Perangkat, tab Status · Running config · Info software · Speed & traffic ·
 *  Mode · Ethernet, dan menu Aksi.
 *
 *  WiFi dan TR-069 sengaja TIDAK ada di sini (Phase 2, PRD 3.4.6 poin 7-8).
 *
 *  Komponen bersama saja: Confirm/Drawer/TableCard dari components/crud.tsx, SignalBar/
 *  StatusBadge/Panel dari components/data.tsx. Bucket sinyal tidak dihitung di halaman ini —
 *  SignalBar yang menanganinya (satu definisi bucket, lihat data.tsx).
 *
 *  Semua aksi = job: tombol hanya membuat job lalu menunggu statusnya. TANPA optimistic
 *  update (AGENTS.md) — angka di layar berubah setelah job selesai dan query di-invalidate.
 */
import { ArrowLeft, CaretDown } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Popover } from "radix-ui";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Confirm, Drawer, Field, TableCard, cell, input } from "../components/crud";
import {
  ErrorState, Panel, Skeleton, SignalBar, StatusBadge, fmtDateTime, nf,
} from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, type OnuDetail as Detail, type OnuLog, type SignalPoint,
  type SpeedProfile, type Splitter, type Vlan, type Zone,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { useJob } from "../lib/jobs";

const TABS = ["Status", "Running config", "Info software", "Speed & traffic", "Mode", "Ethernet"] as const;
type Tab = (typeof TABS)[number];
const RANGES = [["24h", "24 jam"], ["7d", "7 hari"], ["30d", "30 hari"]] as const;

const dash = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));
const dbm = (v: number | null) => (v === null ? "—" : `${Number(v).toFixed(1)} dBm`);

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b px-4 py-2 last:border-0">
      <span className="text-muted">{label}</span>
      <span className="text-right font-mono">{value}</span>
    </div>
  );
}

function fmtDistance(m: number | null) {
  if (m === null) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${nf.format(m)} m`;
}

function fmtUptime(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d}h ${h}j` : h > 0 ? `${h}j ${m}m` : `${m}m`;
}

/** Ringkasan histori Rx: terendah / rata-rata / tertinggi + jumlah kejadian putus.
 *  Operator butuh ini untuk membedakan sinyal yang memang jelek dari yang naik-turun. */
function rxStats(points: SignalPoint[]) {
  const values = points.map((p) => p.rx_power_dbm).filter((v): v is number => v !== null);
  const downs = points.filter((p) => p.status !== "online").length;
  if (values.length === 0) return null;
  return {
    min: Math.min(...values),
    max: Math.max(...values),
    avg: values.reduce((a, b) => a + b, 0) / values.length,
    downs,
    count: values.length,
  };
}

/** Grafik Rx sederhana: sparkline SVG dari histori, ambang sebagai garis putus.
 *  ponytail: tanpa library chart — satu polyline sudah menjawab "trennya turun atau tidak".
 *  skipped: tooltip per titik & zoom, tambah kalau operator memang memintanya. */
function RxChart({ points }: { points: SignalPoint[] }) {
  const values = points.map((p) => p.rx_power_dbm).filter((v): v is number => v !== null);
  if (values.length < 2) return <p className="px-4 py-6 text-muted">Belum cukup data histori sinyal.</p>;
  const min = Math.min(...values, -30);
  const max = Math.max(...values, -8);
  const span = max - min || 1;
  const x = (i: number) => (i / (points.length - 1)) * 100;
  const y = (v: number) => 100 - ((v - min) / span) * 100;
  const line = points
    .map((p, i) => (p.rx_power_dbm === null ? null : `${x(i)},${y(p.rx_power_dbm)}`))
    .filter((s): s is string => s !== null)
    .join(" ");
  return (
    <div className="px-4 py-3">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-24 w-full" role="img"
           aria-label={`Grafik Rx ONU, ${values.length} titik, terendah ${min.toFixed(1)} dBm`}>
        {[-25, -27].map((t) => (
          <line key={t} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
                strokeWidth="0.4" strokeDasharray="2 2" className="text-muted" />
        ))}
        <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1"
                  className="text-fiber" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="mt-1 text-xs text-muted">
        Garis putus = ambang {`-25`} dan {`-27`} dBm · {values.length} bacaan
      </p>
    </div>
  );
}

/** Field editable di dialog "Ubah" kartu Pelanggan — hanya kolom database (bukan OLT). */
type InfoForm = {
  customer_name: string; customer_id: string; name: string; contact: string; phone: string;
  address: string; external_id: string; zone_id: string; splitter_id: string;
  splitter_port: string; latitude: string; longitude: string;
};

const str = (v: unknown) => (v === null || v === undefined ? "" : String(v));

function infoFrom(d: Detail): InfoForm {
  return {
    customer_name: str(d.customer_name), customer_id: str(d.customer_id), name: str(d.name),
    contact: str(d.contact), phone: str(d.phone), address: str(d.address),
    external_id: str(d.external_id), zone_id: str(d.zone_id), splitter_id: str(d.splitter_id),
    splitter_port: str(d.splitter_port), latitude: str(d.latitude), longitude: str(d.longitude),
  };
}

/** Teks kosong dikirim sebagai null supaya kolom benar-benar dibersihkan, bukan jadi "". */
function infoPayload(f: InfoForm) {
  const text = (v: string) => (v.trim() === "" ? null : v.trim());
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  return {
    customer_name: text(f.customer_name), customer_id: text(f.customer_id),
    name: text(f.name), contact: text(f.contact), phone: text(f.phone),
    address: text(f.address), external_id: text(f.external_id),
    zone_id: num(f.zone_id), splitter_id: num(f.splitter_id),
    splitter_port: num(f.splitter_port), latitude: num(f.latitude), longitude: num(f.longitude),
  };
}

export function OnuDetail() {
  const { id: serial = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const { isManager } = useAuth();
  const tab = (TABS.find((t) => t.toLowerCase() === params.get("tab")) ?? "Status") as Tab;
  const range = (params.get("range") ?? "24h") as "24h" | "7d" | "30d";
  const [jobId, setJobId] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<null | "reboot" | "resync" | "restore-factory" | "delete" | "state">(null);
  const [typed, setTyped] = useState("");
  const [editing, setEditing] = useState<null | "speed" | "vlan" | "replace" | "info">(null);
  const [form, setForm] = useState("");
  const [info, setInfo] = useState<InfoForm | null>(null);
  const [dnForm, setDnForm] = useState("");
  const [upForm, setUpForm] = useState("");
  const [note, setNote] = useState("");

  const onu = useQuery({
    queryKey: ["onu", serial],
    queryFn: () => api<Detail>(`/api/onus/${serial}`),
  });
  const signal = useQuery({
    queryKey: ["onu", serial, "signal", range],
    queryFn: () => api<SignalPoint[]>(`/api/onus/${serial}/signal?range=${range}`),
  });
  const logs = useQuery({
    queryKey: ["onu", serial, "logs"],
    queryFn: () => api<OnuLog[]>(`/api/onus/${serial}/logs?limit=50`),
  });
  const profiles = useQuery({
    queryKey: ["speed-profiles"], queryFn: () => api<SpeedProfile[]>("/api/speed-profiles"),
  });
  const vlans = useQuery({ queryKey: ["vlans"], queryFn: () => api<Vlan[]>("/api/vlans") });
  const zones = useQuery({ queryKey: ["zones"], queryFn: () => api<Zone[]>("/api/zones") });
  const splitters = useQuery({
    queryKey: ["splitters", "all"], queryFn: () => api<Splitter[]>("/api/splitters"),
  });
  const job = useJob(jobId);

  /** Edit data pelanggan/lokasi: kolom database saja, jadi langsung PATCH (bukan job). */
  const saveInfo = useMutation({
    mutationFn: (f: InfoForm) =>
      api<Detail>(`/api/onus/${serial}/info`, { method: "PATCH", json: infoPayload(f) }),
    onSuccess: () => {
      setEditing(null);
      setNote("Data pelanggan disimpan.");
      qc.invalidateQueries({ queryKey: ["onu", serial] });
      qc.invalidateQueries({ queryKey: ["onus"] });
    },
  });

  /** Semua aksi memakai jalur yang sama: POST -> job_id -> tampilkan status job. */
  const act = useMutation({
    mutationFn: ({ path, method = "POST", json }: { path: string; method?: string; json?: unknown }) =>
      api<{ job_id: number }>(`/api/onus/${serial}${path}`, { method, json }),
    onSuccess: (r) => {
      setJobId(r.job_id);
      setNote(`Job #${r.job_id} dibuat.`);
      setConfirm(null);
      setEditing(null);
      setTyped("");
      qc.invalidateQueries({ queryKey: ["onu", serial] });
    },
    onError: (e: Error) => setNote(e.message),
  });

  if (onu.isPending) return <Skeleton text="Memuat detail ONU ..." rows={6} />;
  if (onu.isError || !onu.data) {
    return <ErrorState message={onu.error?.message ?? "Gagal memuat ONU"} onRetry={() => onu.refetch()} />;
  }
  const d = onu.data;
  const stats = rxStats(signal.data ?? []);
  const live = (job.data?.result ?? {}) as Record<string, unknown>;
  const runningConfig = typeof live.running_config === "string" ? live.running_config : "";

  const setTab = (t: Tab) => {
    const p = new URLSearchParams(params);
    p.set("tab", t.toLowerCase());
    setParams(p, { replace: true });
  };

  const actions: { label: string; run: () => void; danger?: boolean; manager?: boolean }[] = [
    { label: "Reboot", run: () => setConfirm("reboot") },
    { label: "Resync config", run: () => setConfirm("resync") },
    { label: "Ubah data pelanggan", run: () => { setInfo(infoFrom(d)); setEditing("info"); } },
    { label: "Ubah speed", run: () => {
      setDnForm(String(d.download_speed_profile_id ?? "")); setUpForm(String(d.upload_speed_profile_id ?? ""));
      setEditing("speed");
    } },
    { label: "Ubah VLAN", run: () => { setForm(String(d.vlan_id ?? "")); setEditing("vlan"); } },
    { label: "Replace ONU / ganti SN", run: () => { setForm(""); setEditing("replace"); }, manager: true },
    { label: d.admin_state === "disabled" ? "Aktifkan ONU" : "Nonaktifkan ONU", run: () => setConfirm("state") },
    { label: "Restore factory", run: () => setConfirm("restore-factory"), danger: true, manager: true },
    { label: "Hapus ONU", run: () => setConfirm("delete"), danger: true, manager: true },
  ].filter((a) => !a.manager || isManager);

  return (
    <>
      <Link to="/configured" className="mb-1 inline-flex items-center gap-1 text-fiber hover:underline">
        <ArrowLeft size={14} aria-hidden /> Configured
      </Link>

      <div className="mb-3 flex min-h-12 flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">{d.customer_name ?? d.name ?? d.serial_number}</h1>
          <StatusBadge status={d.admin_state === "disabled" ? "unknown" : d.status} />
          <span className="font-mono text-muted">
            {d.serial_number} · {d.olt_name} · {d.slot}/{d.port}
            {d.onu_index === null ? "" : `:${d.onu_index}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => act.mutate({ path: "/refresh" })} disabled={act.isPending}>
            ↻ Cek ulang
          </Button>
          <Popover.Root>
            <Popover.Trigger asChild>
              <Button variant="fiber">Aksi <CaretDown size={12} aria-hidden /></Button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content align="end" sideOffset={4}
                className="z-50 w-56 rounded-md border bg-surface p-1 shadow-modal data-[state=open]:animate-[fade-in_150ms_ease-out]">
                {actions.map((a) => (
                  <button key={a.label} type="button" onClick={a.run}
                    className={`block w-full rounded-sm px-2 py-1.5 text-left hover:bg-sunken ${a.danger ? "text-down" : ""}`}>
                    {a.label}
                  </button>
                ))}
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
        </div>
      </div>

      {(note || job.data) && (
        <p className="mb-2 text-muted" role="status">
          {note}{job.data ? ` Status job: ${job.data.status}${job.data.error_message ? ` — ${job.data.error_message}` : ""}` : ""}
        </p>
      )}

      <div className="mb-3 grid gap-3 lg:grid-cols-3">
        <Panel title="Sinyal" className="lg:col-span-2">
          <div className="flex flex-wrap items-center gap-6 px-4 py-3">
            <div>
              <p className="text-xs text-muted">Rx ONU</p>
              <SignalBar dbm={d.rx_power_dbm} big />
            </div>
            <div><p className="text-xs text-muted">Rx OLT</p><p className="font-mono">{dbm(d.olt_rx_power_dbm)}</p></div>
            <div><p className="text-xs text-muted">Tx ONU</p><p className="font-mono">{dbm(d.tx_power_dbm)}</p></div>
            <div><p className="text-xs text-muted">Jarak</p><p className="font-mono">{fmtDistance(d.distance_m)}</p></div>
            <div><p className="text-xs text-muted">Suhu</p><p className="font-mono">{d.temperature_c === null ? "—" : `${Number(d.temperature_c).toFixed(1)} °C`}</p></div>
            <div><p className="text-xs text-muted">Tegangan</p><p className="font-mono">{d.voltage_v === null ? "—" : `${Number(d.voltage_v).toFixed(2)} V`}</p></div>
          </div>
          <div className="flex gap-1 px-4" role="tablist" aria-label="Rentang histori sinyal">
            {RANGES.map(([value, label]) => (
              <button key={value} type="button" role="tab" aria-selected={range === value}
                onClick={() => { const p = new URLSearchParams(params); p.set("range", value); setParams(p, { replace: true }); }}
                className={`border-b-2 px-2 py-1 ${range === value ? "border-fiber font-semibold text-fiber" : "border-transparent text-muted hover:text-ink"}`}>
                {label}
              </button>
            ))}
          </div>
          {signal.isPending
            ? <Skeleton text="Memuat histori sinyal ..." rows={2} />
            : <RxChart points={signal.data ?? []} />}
          {stats && (
            <Row label={`Rx ${range} (min · rata-rata · maks)`}
                 value={`${stats.min.toFixed(1)} · ${stats.avg.toFixed(1)} · ${stats.max.toFixed(1)} dBm`} />
          )}
          {stats && <Row label={`Bacaan tidak online (${range})`} value={`${stats.downs} dari ${stats.count}`} />}
          <Row label="Terakhir online" value={fmtDateTime(d.last_seen_at)} />
          <Row label="Offline terakhir"
               value={d.last_down_at ? `${dash(d.last_down_reason)} · ${fmtDateTime(d.last_down_at)}` : "—"} />
        </Panel>

        <div className="flex flex-col gap-3">
          <Panel title="Pelanggan"
            action={<Button size="sm" onClick={() => { setInfo(infoFrom(d)); setEditing("info"); }}>Ubah</Button>}>
            <Row label="Nama pelanggan" value={dash(d.customer_name)} />
            <Row label="ID pelanggan" value={dash(d.customer_id)} />
            <Row label="Nama/label ONU" value={dash(d.name)} />
            <Row label="Kontak" value={dash(d.contact ?? d.phone)} />
            <Row label="Alamat" value={dash(d.address)} />
            <Row label="Zone" value={dash(d.zone_name)} />
            <Row label="Splitter"
                 value={d.splitter_name ? `${d.splitter_name}${d.splitter_port ? ` · port ${d.splitter_port}` : ""}` : "—"} />
            <Row label="External ID" value={dash(d.external_id)} />
            <Row label="Lokasi" value={d.latitude !== null && d.longitude !== null
              ? <a className="text-fiber hover:underline" target="_blank" rel="noreferrer"
                   href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=17/${d.latitude}/${d.longitude}`}>
                  {Number(d.latitude).toFixed(5)}, {Number(d.longitude).toFixed(5)}
                </a>
              : "—"} />
          </Panel>
          <Panel title="Perangkat">
            <Row label="Tipe ONU" value={dash(d.onu_type)} />
            <Row label="MAC" value={dash(d.mac_address)} />
            <Row label="IP" value={dash(d.ip_address)} />
            <Row label="Otentikasi" value={d.auth_type === "loid" ? `LOID · ${dash(d.loid)}` : d.auth_type.toUpperCase()} />
            <Row label="Match state" value={dash(d.match_state)} />
            <Row label="Bias laser" value={d.bias_current_ma === null ? "—" : `${Number(d.bias_current_ma).toFixed(2)} mA`} />
            <Row label="Preset otorisasi" value={dash(d.preset_name)} />
            <Row label="Diotorisasi" value={fmtDateTime(d.registered_at)} />
            <Row label="Diotorisasi oleh" value={dash(d.registered_by_name)} />
            <Row label="Sinkron terakhir" value={fmtDateTime(d.last_sync_at)} />
          </Panel>
        </div>
      </div>

      <div className="mb-3 flex gap-1 overflow-x-auto border-b" role="tablist">
        {TABS.map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`border-b-2 px-3 py-2 whitespace-nowrap ${tab === t ? "border-fiber font-semibold text-fiber" : "border-transparent text-muted hover:text-ink"}`}>
            {t}
          </button>
        ))}
        <span className="px-3 py-2 text-faint" title="Phase 2">WiFi · Segera</span>
        <span className="px-3 py-2 text-faint" title="Phase 2">TR-069 · Segera</span>
      </div>

      {tab === "Status" && (
        <Panel title="Hasil baca live">
          <Row label="Fase (live)" value={dash(live.phase_state)} />
          <Row label="Rx ONU (live)" value={dbm((live.rx_power_dbm as number | null) ?? d.rx_power_dbm)} />
          <Row label="Tx ONU (live)" value={dbm((live.tx_power_dbm as number | null) ?? d.tx_power_dbm)} />
          <Row label="Rx OLT (live)" value={dbm((live.olt_rx_power_dbm as number | null) ?? d.olt_rx_power_dbm)} />
          <Row label="Jarak" value={fmtDistance((live.distance_m as number | null) ?? d.distance_m)} />
          <Row label="Uptime" value={fmtUptime(live.online_duration_s as number | null)} />
          <Row label="Config state" value={d.config_state} />
          <Row label="Admin state" value={d.admin_state} />
          <p className="px-4 py-2 text-muted">
            Kolom "(live)" terisi setelah job <strong>Cek ulang</strong> selesai; sebelum itu yang tampil nilai terakhir dari database.
          </p>
        </Panel>
      )}

      {tab === "Running config" && (
        <Panel title="Running config"
          action={runningConfig && (
            <Button size="sm" onClick={() => navigator.clipboard?.writeText(runningConfig)}>Salin</Button>
          )}>
          {runningConfig
            ? <pre className="overflow-x-auto bg-sunken p-4 font-mono text-xs whitespace-pre">{runningConfig}</pre>
            : <p className="px-4 py-6 text-muted">Jalankan <strong>Cek ulang</strong> untuk membaca running config dari OLT.</p>}
        </Panel>
      )}

      {tab === "Info software" && (
        <Panel title="Versi perangkat">
          <Row label="Software aktif" value={dash(live.software_version ?? d.software_version)} />
          <Row label="Software standby" value={dash(live.software_version_standby)} />
          <Row label="Hardware" value={dash(live.hardware_version ?? d.hardware_version)} />
          <p className="px-4 py-2 text-muted">Versi standby hanya terisi setelah <strong>Cek ulang</strong>.</p>
        </Panel>
      )}

      {tab === "Speed & traffic" && (
        <Panel title="Speed profile"
          action={<Button size="sm" onClick={() => {
            setDnForm(String(d.download_speed_profile_id ?? "")); setUpForm(String(d.upload_speed_profile_id ?? ""));
            setEditing("speed");
          }}>Ubah speed</Button>}>
          <Row label="Paket download" value={dash(d.download_profile_name)} />
          <Row label="Paket upload" value={dash(d.upload_profile_name)} />
          <Row label="Profile download (OLT)" value={dash(d.line_profile_id)} />
          <Row label="Profile upload (OLT)" value={dash(d.srv_profile_id)} />
          <Row label="VLAN" value={dash(d.vlan_number)} />
          <p className="px-4 py-2 text-muted">Grafik traffic per ONU: Phase 2 (PRD 3.4.6).</p>
        </Panel>
      )}

      {tab === "Mode" && (
        <Panel title="Mode ONU">
          <Row label="Mode ONU" value={dash(d.onu_mode)} />
          <Row label="Mode WAN" value={dash(d.wan_mode)} />
          <Row label="IP manajemen" value={dash(d.mgmt_ip_mode)} />
          <Row label="PPPoE username" value={dash(d.pppoe_username)} />
          <p className="px-4 py-2 text-muted">
            Sumber konfigurasi TR-069 dan akses remote: Phase 2. Nilai di atas dari konfigurasi saat otorisasi.
          </p>
        </Panel>
      )}

      {tab === "Ethernet" && (
        <Panel title="Port Ethernet">
          <p className="px-4 py-6 text-muted">
            Konfigurasi port per ONU belum dibaca dari OLT pada tahap ini — belum ada contoh keluaran CLI
            `show onu running config` untuk port Ethernet yang bisa diparse dengan benar.
            {/* ponytail: tabel port kosong daripada menebak isi. skipped: parsing port Ethernet,
                tambah setelah ada transkrip CLI nyata dari ONU test. */}
          </p>
        </Panel>
      )}

      <Panel title="Log aksi terakhir" className="mt-3"
        action={<Link className="text-fiber hover:underline" to={`/logs?q=${d.serial_number}`}>
          Buka di Logs
        </Link>}>
        <TableCard
          query={logs}
          loadingText="Memuat log ..."
          empty="Belum ada log untuk ONU ini."
          columns={["Waktu", "Pengguna", "Aksi", "Hasil", "Job", "Command"]}
          row={(l: OnuLog) => (
            <tr key={l.id} className="border-b last:border-0">
              <td className={cell}>{fmtDateTime(l.created_at)}</td>
              <td className={cell}>{dash(l.username)}</td>
              <td className={`${cell} font-mono`}>{l.action}</td>
              <td className={cell}>
                <span className={l.success ? "text-up" : "text-down"}>{l.success ? "Berhasil" : "Gagal"}</span>
              </td>
              <td className={`${cell} font-mono`}>{l.job_id === null ? "—" : `#${l.job_id}`}</td>
              <td className={`${cell} max-w-[22rem] truncate font-mono text-xs text-muted`}
                  title={l.raw_command ?? ""}>
                {dash(l.raw_command)}
              </td>
            </tr>
          )}
        />
      </Panel>

      {confirm === "reboot" && (
        <Confirm title="Reboot ONU?" action="Reboot" busy={act.isPending} error={act.error?.message}
          body="ONU akan mati sekitar satu menit. Dijalankan sebagai job oleh worker."
          onConfirm={() => act.mutate({ path: "/reboot" })} onClose={() => setConfirm(null)} />
      )}
      {confirm === "resync" && (
        <Confirm title="Resync config ke OLT?" action="Resync" busy={act.isPending} error={act.error?.message}
          body="Konfigurasi dari database dikirim ulang ke OLT. Aman diulang."
          onConfirm={() => act.mutate({ path: "/resync" })} onClose={() => setConfirm(null)} />
      )}
      {confirm === "state" && (
        <Confirm
          title={d.admin_state === "disabled" ? "Aktifkan ONU?" : "Nonaktifkan ONU?"}
          action={d.admin_state === "disabled" ? "Aktifkan" : "Nonaktifkan"}
          busy={act.isPending} error={act.error?.message}
          body={d.admin_state === "disabled"
            ? "Layanan pelanggan ini akan hidup kembali."
            : "Layanan pelanggan ini akan mati sampai diaktifkan lagi."}
          onConfirm={() => act.mutate({ path: "/state", json: { enabled: d.admin_state === "disabled" } })}
          onClose={() => setConfirm(null)} />
      )}

      {(confirm === "restore-factory" || confirm === "delete") && (
        <Drawer
          title={confirm === "delete" ? "Hapus ONU" : "Restore factory"}
          busy={act.isPending}
          error={act.error?.message}
          onClose={() => { setConfirm(null); setTyped(""); }}
          onSubmit={() => typed === d.serial_number && act.mutate(
            confirm === "delete" ? { path: "", method: "DELETE" } : { path: "/restore-factory" })}
        >
          <p className="mb-3 text-down">
            {confirm === "delete"
              ? "ONU dihapus dari OLT dan di-soft-delete di Nexfiber. Riwayat sinyal tetap tersimpan."
              : "ONU dikembalikan ke setelan pabrik. Seluruh konfigurasi di perangkat pelanggan hilang."}
          </p>
          <Field label={`Ketik serial number untuk konfirmasi: ${d.serial_number}`}>
            <input className={input} value={typed} onChange={(e) => setTyped(e.target.value)}
                   placeholder={d.serial_number} autoComplete="off" />
          </Field>
          {typed !== "" && typed !== d.serial_number && (
            <p className="text-down">Serial number belum cocok.</p>
          )}
        </Drawer>
      )}

      {editing === "speed" && (
        <Drawer title="Ubah speed profile" busy={act.isPending} error={act.error?.message}
          onClose={() => setEditing(null)}
          onSubmit={() => (dnForm || upForm) && act.mutate({
            path: "/speed-profile",
            json: {
              download_speed_profile_id: dnForm ? Number(dnForm) : null,
              upload_speed_profile_id: upForm ? Number(upForm) : null,
            },
          })}>
          <Field label="Profile download">
            <select className={input} value={dnForm} onChange={(e) => setDnForm(e.target.value)}>
              <option value="">Jangan ubah</option>
              {(profiles.data ?? []).filter((p) => p.direction === "download").map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({nf.format(p.speed_kbps / 1000)} Mbps)</option>
              ))}
            </select>
          </Field>
          <Field label="Profile upload">
            <select className={input} value={upForm} onChange={(e) => setUpForm(e.target.value)}>
              <option value="">Jangan ubah</option>
              {(profiles.data ?? []).filter((p) => p.direction === "upload").map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({nf.format(p.speed_kbps / 1000)} Mbps)</option>
              ))}
            </select>
          </Field>
        </Drawer>
      )}

      {editing === "vlan" && (
        <Drawer title="Ubah VLAN" busy={act.isPending} error={act.error?.message}
          onClose={() => setEditing(null)}
          onSubmit={() => form && act.mutate({ path: "/vlan", json: { vlan_id: Number(form) } })}>
          <Field label="VLAN">
            <select className={input} value={form} onChange={(e) => setForm(e.target.value)}>
              <option value="">Pilih VLAN ...</option>
              {(vlans.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>VLAN {v.vlan_id} · {v.name}</option>
              ))}
            </select>
          </Field>
          <p className="text-muted">Service-port ONU dikonfigurasi ulang di OLT lewat job.</p>
        </Drawer>
      )}

      {editing === "replace" && (
        <Drawer title="Replace ONU / ganti SN" busy={act.isPending} error={act.error?.message}
          onClose={() => setEditing(null)}
          onSubmit={() => form.length >= 4 && act.mutate({ path: "/replace", json: { serial_number: form } })}>
          <Field label="Serial number lama">
            <input className={input} value={d.serial_number} readOnly disabled />
          </Field>
          <Field label="Serial number baru">
            <input className={input} value={form} onChange={(e) => setForm(e.target.value.trim())}
                   placeholder="ZTEGC..." autoComplete="off" />
          </Field>
          <p className="text-muted">
            ONU lama dihapus dari OLT lalu SN baru diotorisasi di ONU ID yang sama. Data pelanggan,
            paket, VLAN, dan riwayat sinyal tetap ikut baris ini.
          </p>
        </Drawer>
      )}
      {editing === "info" && info && (
        <Drawer title="Ubah data pelanggan" busy={saveInfo.isPending} error={saveInfo.error?.message}
          onClose={() => setEditing(null)}
          onSubmit={() => saveInfo.mutate(info)}>
          <Field label="Nama pelanggan">
            <input className={input} value={info.customer_name}
                   onChange={(e) => setInfo({ ...info, customer_name: e.target.value })} />
          </Field>
          <Field label="ID pelanggan">
            <input className={input} value={info.customer_id} autoComplete="off"
                   onChange={(e) => setInfo({ ...info, customer_id: e.target.value })} />
          </Field>
          <Field label="Nama/label ONU">
            <input className={input} value={info.name}
                   onChange={(e) => setInfo({ ...info, name: e.target.value })} />
          </Field>
          <Field label="Kontak">
            <input className={input} value={info.contact}
                   onChange={(e) => setInfo({ ...info, contact: e.target.value })} />
          </Field>
          <Field label="Telepon">
            <input className={input} value={info.phone}
                   onChange={(e) => setInfo({ ...info, phone: e.target.value })} />
          </Field>
          <Field label="Alamat">
            <input className={input} value={info.address}
                   onChange={(e) => setInfo({ ...info, address: e.target.value })} />
          </Field>
          <Field label="External ID">
            <input className={input} value={info.external_id}
                   onChange={(e) => setInfo({ ...info, external_id: e.target.value })} />
          </Field>
          <Field label="Zone">
            <select className={input} value={info.zone_id}
                    onChange={(e) => setInfo({ ...info, zone_id: e.target.value })}>
              <option value="">Tanpa zone</option>
              {(zones.data ?? []).map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </Field>
          <Field label="Splitter / ODP">
            <select className={input} value={info.splitter_id}
                    onChange={(e) => setInfo({ ...info, splitter_id: e.target.value })}>
              <option value="">Tanpa splitter</option>
              {(splitters.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>{s.name}{s.zone_name ? ` · ${s.zone_name}` : ""}</option>
              ))}
            </select>
          </Field>
          <Field label="Port splitter">
            <input className={input} type="number" min={1} value={info.splitter_port}
                   onChange={(e) => setInfo({ ...info, splitter_port: e.target.value })} />
          </Field>
          <Field label="Latitude">
            <input className={input} value={info.latitude} placeholder="-6.20000"
                   onChange={(e) => setInfo({ ...info, latitude: e.target.value })} />
          </Field>
          <Field label="Longitude">
            <input className={input} value={info.longitude} placeholder="106.81666"
                   onChange={(e) => setInfo({ ...info, longitude: e.target.value })} />
          </Field>
          <p className="text-muted">
            Data ini hanya tersimpan di Nexfiber — tidak ada perintah yang dikirim ke OLT.
          </p>
        </Drawer>
      )}
    </>
  );
}
