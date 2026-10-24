/** Detail ONU — PRD 3.4.6. Satu halaman (tidak ada halaman detail kedua).
 *
 *  Tata letak mengikuti aplikasi referensi milik pemilik (permintaan user: "biar sama dengan
 *  aplikasi ... untuk tampilan nya"), urutan blok: grid teks dua kolom (identitas | status &
 *  koneksi) → baris Status (tombol baca live + output CLI) → Trafik/Sinyal → Profil Kecepatan →
 *  Port Ethernet → WiFi → VoIP/CATV → baris aksi. Inventaris sumber-vs-Nexfiber dan daftar
 *  menu yang belum bisa disamakan ada di ONU-DETAIL-PARITY.md. Tidak ada nama/branding
 *  aplikasi referensi di kode maupun UI; token warna/komponen tetap milik Nexfiber.
 *
 *  Penyimpangan sadar dari DESIGN 12.6: tab horizontal dan dropdown "Aksi ▾" diganti blok
 *  bertumpuk + baris tombol, karena user meminta kesetaraan tampilan dengan referensi.
 *
 *  Komponen bersama saja: Confirm/Drawer/TableCard dari components/crud.tsx, SignalBar/
 *  StatusBadge/Panel dari components/data.tsx. Bucket sinyal tidak dihitung di halaman ini.
 *
 *  Semua aksi ke perangkat = job: tombol hanya membuat job lalu menunggu statusnya. TANPA
 *  optimistic update (AGENTS.md).
 */
import { ArrowLeft, Pencil } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Confirm, Drawer, Field, TableCard, cell, input } from "../components/crud";
import {
  ErrorState, Panel, Skeleton, SignalBar, StatusBadge, fmtDateTime, nf,
} from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, type OnuDetail as Detail, type OnuLog, type OnuType, type SignalPoint,
  type SpeedProfile, type Splitter, type Vlan, type Zone,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { useJob } from "../lib/jobs";

const RANGES = [["24h", "24 jam"], ["7d", "7 hari"], ["30d", "30 hari"]] as const;
/** Interval auto-refresh tombol LIVE — sama dengan siklus status referensi (15 detik). */
const LIVE_MS = 15_000;

const dash = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));
const dbm = (v: number | null) => (v === null ? "—" : `${Number(v).toFixed(2)} dBm`);

/** Baris label/nilai grid atas: label kanan-align lebar tetap di ≥600px, menumpuk di bawahnya
 *  (mengikuti breakpoint referensi). `onEdit` membuat seluruh baris bisa diklik. */
function DRow(
  { label, value, onEdit }: { label: string; value: React.ReactNode; onEdit?: () => void },
) {
  const content = (
    <>
      <span className="text-xs font-semibold text-muted sm:w-[190px] sm:shrink-0 sm:text-right">
        {label}
      </span>
      <span className="flex min-w-0 flex-wrap items-center gap-1.5">
        {onEdit && <Pencil size={12} aria-hidden className="text-muted" />}
        {value}
      </span>
    </>
  );
  return onEdit ? (
    <button type="button" onClick={onEdit}
      className="flex w-full flex-col gap-0.5 py-0.5 text-left hover:text-fiber sm:flex-row sm:items-baseline sm:gap-5">
      {content}
    </button>
  ) : (
    <div className="flex flex-col gap-0.5 py-0.5 sm:flex-row sm:items-baseline sm:gap-5">
      {content}
    </div>
  );
}

/** Baris blok bawah: label kiri (160px) + konten, menumpuk di < 768px seperti referensi. */
function Section(
  { label, children, tight = false }:
  { label: string; children: React.ReactNode; tight?: boolean },
) {
  return (
    <section className={`flex flex-col gap-2.5 border-b py-4 last:border-0 md:flex-row md:items-start md:gap-4
      ${tight ? "py-2" : ""}`}>
      <h2 className="text-xs font-semibold uppercase tracking-[0.02em] text-muted md:w-40 md:shrink-0 md:pt-1">
        {label}
      </h2>
      <div className="min-w-0 grow">{children}</div>
    </section>
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

/** Ringkasan histori Rx: terendah / rata-rata / tertinggi + jumlah bacaan tidak online. */
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

/** Grafik Rx: sparkline SVG dari histori, ambang sebagai garis putus.
 *  ponytail: tanpa library chart — satu polyline sudah menjawab "trennya turun atau tidak".
 *  skipped: tooltip per titik & zoom, tambah kalau operator memang memintanya. */
function RxChart({ points }: { points: SignalPoint[] }) {
  const values = points.map((p) => p.rx_power_dbm).filter((v): v is number => v !== null);
  if (values.length < 2) return <p className="py-6 text-muted">Belum cukup data histori sinyal.</p>;
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
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-28 w-full" role="img"
         aria-label={`Grafik Rx ONU, ${values.length} titik, terendah ${min.toFixed(1)} dBm`}>
      {[-25, -27].map((t) => (
        <line key={t} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
              strokeWidth="0.4" strokeDasharray="2 2" className="text-muted" />
      ))}
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1"
                className="text-fiber" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Kartu grafik: judul + isi + legenda, posisi sama dengan dua kartu sejajar di referensi. */
function ChartCard(
  { title, children, legend }:
  { title: string; children: React.ReactNode; legend?: React.ReactNode },
) {
  return (
    <div className="min-w-0 flex-1 rounded-md border bg-surface p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.02em] text-muted">{title}</p>
      {children}
      {legend && <div className="mt-3 grid gap-1 text-xs text-muted">{legend}</div>}
    </div>
  );
}

function LegendRow({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-1.5">
        <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-sm ${color}`} />
        {label}
      </span>
      <span className="font-mono text-ink">{value}</span>
    </div>
  );
}

/** Field editable di dialog "Ubah" data pelanggan — hanya kolom database (bukan OLT). */
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

const PON_LABEL: Record<string, string> = {
  gpon: "GPON", epon: "EPON", xgpon: "XG-PON", xgspon: "XGS-PON",
};

export function OnuDetail() {
  const { id: serial = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const { isManager } = useAuth();
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
  /** Panel output CLI di bawah baris tombol Status (satu panel, tiga pilihan isi). */
  const [cliView, setCliView] = useState<null | "status" | "running" | "software">(null);
  const [live, setLive] = useState(false);

  const onu = useQuery({
    queryKey: ["onu", serial],
    queryFn: () => api<Detail>(`/api/onus/${serial}`),
    refetchInterval: live ? LIVE_MS : false,
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
  /** Jumlah port Ethernet/SSID/VoIP/CATV berasal dari katalog ONU Types (master data nyata),
   *  bukan angka hardcode per tipe. */
  const onuTypes = useQuery({
    queryKey: ["onu-types"], queryFn: () => api<OnuType[]>("/api/onu-types"),
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
  const result = (job.data?.result ?? {}) as Record<string, unknown>;
  const runningConfig = typeof result.running_config === "string" ? result.running_config : "";
  const specs = (onuTypes.data ?? []).find(
    (t) => t.id === d.onu_type_id || t.name.toLowerCase() === (d.onu_type ?? "").toLowerCase(),
  );
  const statusKey = d.admin_state === "disabled" ? "disabled" : d.status;

  /** Tombol baris Status: baca live lewat job refresh (read-only ke OLT), lalu tampilkan
   *  potongan hasilnya di panel output. Job dibuat sekali; klik tombol lain cuma ganti isi. */
  const readLive = (view: "status" | "running" | "software") => {
    setCliView(view);
    if (!job.data || job.data.status === "success" || job.data.status === "failed") {
      act.mutate({ path: "/refresh" });
    }
  };

  const infoDialog = () => { setInfo(infoFrom(d)); setEditing("info"); };
  const speedDialog = () => {
    setDnForm(String(d.download_speed_profile_id ?? ""));
    setUpForm(String(d.upload_speed_profile_id ?? ""));
    setEditing("speed");
  };

  const cliText = () => {
    if (cliView === "running") {
      return runningConfig || "Menunggu hasil job pembacaan running-config dari OLT ...";
    }
    if (cliView === "software") {
      return [
        `Software aktif   : ${dash(result.software_version ?? d.software_version)}`,
        `Software standby : ${dash(result.software_version_standby)}`,
        `Hardware         : ${dash(result.hardware_version ?? d.hardware_version)}`,
      ].join("\n");
    }
    return [
      `Fase            : ${dash(result.phase_state)}`,
      `Rx ONU          : ${dbm((result.rx_power_dbm as number | null) ?? d.rx_power_dbm)}`,
      `Tx ONU          : ${dbm((result.tx_power_dbm as number | null) ?? d.tx_power_dbm)}`,
      `Rx OLT          : ${dbm((result.olt_rx_power_dbm as number | null) ?? d.olt_rx_power_dbm)}`,
      `Jarak           : ${fmtDistance((result.distance_m as number | null) ?? d.distance_m)}`,
      `Uptime          : ${fmtUptime(result.online_duration_s as number | null)}`,
      `Config state    : ${d.config_state}`,
      `Admin state     : ${d.admin_state}`,
      `Perintah        : ${dash(result.raw_command)}`,
    ].join("\n");
  };

  return (
    <>
      <Link to="/configured" className="mb-1 inline-flex items-center gap-1 text-fiber hover:underline">
        <ArrowLeft size={14} aria-hidden /> Configured
      </Link>
      <h1 className="mb-4 text-xl font-semibold">
        Detail ONU — {d.customer_name ?? d.name ?? d.serial_number}
      </h1>

      {(note || job.data) && (
        <p className="mb-3 text-muted" role="status">
          {note}{job.data ? ` Status job: ${job.data.status}${job.data.error_message ? ` — ${job.data.error_message}` : ""}` : ""}
        </p>
      )}

      {/* Blok 1: grid teks dua kolom, tanpa kartu/garis (urutan field sama dengan referensi) */}
      <div className="mb-5 grid gap-x-16 gap-y-0 lg:grid-cols-2">
        <div className="flex flex-col">
          <DRow label="OLT" value={
            <Link className="text-fiber hover:underline" to={`/olt/${d.olt_id}`}>{d.olt_name}</Link>
          } />
          <DRow label="Shelf" value="1" />
          <DRow label="Slot" value={d.slot} />
          <DRow label="Port" value={d.port} />
          <DRow label="ONU" value={
            <Link className="font-mono text-fiber hover:underline" to={`/configured?olt_id=${d.olt_id}`}>
              gpon-onu_{d.slot}/{d.port}{d.onu_index === null ? "" : `:${d.onu_index}`}
            </Link>
          } />
          <DRow label="Kanal" value={specs ? PON_LABEL[specs.pon_type] ?? specs.pon_type.toUpperCase() : "—"} />
          <DRow label="SN" value={<span className="font-mono">{d.serial_number}</span>}
                onEdit={isManager ? () => { setForm(""); setEditing("replace"); } : undefined} />
          <DRow label="Tipe ONU" value={dash(d.onu_type)} />
          <DRow label="Preset konfigurasi" value={dash(d.preset_name)} />
          <DRow label="Zone" value={dash(d.zone_name)} onEdit={infoDialog} />
          <DRow label="Splitter" onEdit={infoDialog}
                value={d.splitter_name ? `${d.splitter_name}${d.splitter_port ? ` · port ${d.splitter_port}` : ""}` : "—"} />
          <DRow label="Nama" value={dash(d.customer_name ?? d.name)} onEdit={infoDialog} />
          <DRow label="Alamat atau keterangan" value={dash(d.address ?? d.description)} onEdit={infoDialog} />
          <DRow label="Kontak" value={dash(d.contact ?? d.phone)} onEdit={infoDialog} />
          <DRow label="Tanggal otorisasi" value={fmtDateTime(d.registered_at)} />
          <DRow label="Diotorisasi oleh" value={dash(d.registered_by_name)} />
          <DRow label="Port splitter" value={dash(d.splitter_port)} onEdit={infoDialog} />
          <DRow label="ONU external ID" value={dash(d.external_id)} onEdit={infoDialog} />
          <DRow label="Lokasi" value={d.latitude !== null && d.longitude !== null
            ? <a className="text-fiber hover:underline" target="_blank" rel="noreferrer"
                 href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=17/${d.latitude}/${d.longitude}`}>
                {Number(d.latitude).toFixed(5)}, {Number(d.longitude).toFixed(5)}
              </a>
            : "—"} />
        </div>

        <div className="flex flex-col">
          <DRow label="Status" value={
            <>
              <StatusBadge status={statusKey} reason={d.last_down_reason} withLabel />
              {live && <span className="text-xs text-muted">auto-refresh {LIVE_MS / 1000}s</span>}
            </>
          } />
          <DRow label="Terakhir online" value={fmtDateTime(d.last_seen_at)} />
          <DRow label="Last down" value={d.last_down_at
            ? `${dash(d.last_down_reason)} · ${fmtDateTime(d.last_down_at)}` : "—"} />
          <DRow label="Sinyal Rx" value={
            <>
              <SignalBar dbm={d.rx_power_dbm} />
              <span className="font-mono">{dbm(d.rx_power_dbm)}</span>
              <span className="text-muted">/</span>
              <span className="font-mono">{dbm(d.olt_rx_power_dbm)}</span>
              <span className="text-muted">{fmtDistance(d.distance_m)}</span>
            </>
          } />
          <DRow label="Tx ONU" value={<span className="font-mono">{dbm(d.tx_power_dbm)}</span>} />
          <DRow label="Suhu / tegangan" value={
            <span className="font-mono">
              {d.temperature_c === null ? "—" : `${Number(d.temperature_c).toFixed(1)} °C`}
              {" / "}
              {d.voltage_v === null ? "—" : `${Number(d.voltage_v).toFixed(2)} V`}
            </span>
          } />
          <DRow label="Bias laser" value={
            <span className="font-mono">
              {d.bias_current_ma === null ? "—" : `${Number(d.bias_current_ma).toFixed(2)} mA`}
            </span>
          } />
          <DRow label="MAC / IP" value={
            <span className="font-mono">{dash(d.mac_address)} / {dash(d.ip_address)}</span>
          } />
          <DRow label="IP manajemen" value={dash(d.mgmt_ip_mode)} />
          <DRow label="TR-069 profile" value={<span className="text-faint">Segera</span>} />
          <DRow label="VLAN terpasang" value={dash(d.vlan_number)}
                onEdit={() => { setForm(String(d.vlan_id ?? "")); setEditing("vlan"); }} />
          <DRow label="Akses remote WAN" value={<span className="text-faint">Segera</span>} />
          <DRow label="Mode ONU" value={`${dash(d.onu_mode)}${d.vlan_number ? ` — WAN ${d.vlan_number}` : ""}`} />
          <DRow label="Mode setup WAN" value={dash(d.wan_mode)} />
          <DRow label="Nama pengguna PPPoE" value={<span className="font-mono">{dash(d.pppoe_username)}</span>} />
          <DRow label="Kata sandi PPPoE" value={
            <span className="text-faint">Tidak ditampilkan</span>
          } />
          <DRow label="Otentikasi" value={d.auth_type === "loid" ? `LOID · ${dash(d.loid)}` : d.auth_type.toUpperCase()} />
          <DRow label="Match state" value={dash(d.match_state)} />
          <DRow label="Sinkron terakhir" value={fmtDateTime(d.last_sync_at)} />
        </div>
      </div>

      {/* Blok 2: baris Status — tombol baca live + panel output CLI di bawahnya */}
      <Section label="Status">
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => readLive("status")} disabled={act.isPending}>Status</Button>
          <Button onClick={() => readLive("running")} disabled={act.isPending}>Show running-config</Button>
          <Button onClick={() => readLive("software")} disabled={act.isPending}>Info SW</Button>
          {/* Tombol status TR-069 di aplikasi referensi hanya muncul saat profil TR-069 ONU
              menunjuk server ACS internal aplikasi. Nexfiber belum punya server ACS internal
              maupun katalog profil TR-069 (Phase 2, DECISIONS.md), jadi kondisinya tidak pernah
              benar dan tombolnya tidak dirender sama sekali — bukan placeholder "Segera". */}
          <Button variant={live ? "fiber" : "secondary"} aria-pressed={live}
                  onClick={() => setLive(!live)}>
            {live ? "LIVE aktif" : "LIVE!"}
          </Button>
          {cliView && runningConfig && cliView === "running" && (
            <Button size="sm" onClick={() => navigator.clipboard?.writeText(runningConfig)}>Salin</Button>
          )}
        </div>
        {cliView && (
          <pre className="mt-3 overflow-x-auto rounded-md bg-sunken p-4 font-mono text-xs whitespace-pre">
            {cliText()}
          </pre>
        )}
      </Section>

      {/* Blok 3: Trafik/Sinyal — dua kartu sejajar, menumpuk di layar kecil */}
      <Section label="Trafik/Sinyal">
        <div className="flex flex-col gap-4 lg:flex-row">
          <ChartCard title={`gpon-onu_${d.slot}/${d.port}${d.onu_index === null ? "" : `:${d.onu_index}`} trafik`}>
            <p className="py-10 text-center text-muted">
              Grafik trafik per ONU: Phase 2 — belum ada sumber counter per ONU.
            </p>
          </ChartCard>
          <ChartCard
            title={`gpon-onu_${d.slot}/${d.port}${d.onu_index === null ? "" : `:${d.onu_index}`} sinyal`}
            legend={
              <>
                <LegendRow color="bg-fiber" label="Rx ONU" value={dbm(d.rx_power_dbm)} />
                <LegendRow color="bg-amber" label="Rx OLT" value={dbm(d.olt_rx_power_dbm)} />
                {stats && (
                  <LegendRow color="bg-sunken" label={`Rx ${range} min · rata-rata · maks`}
                    value={`${stats.min.toFixed(1)} · ${stats.avg.toFixed(1)} · ${stats.max.toFixed(1)}`} />
                )}
                {stats && (
                  <LegendRow color="bg-sunken" label={`Bacaan tidak online (${range})`}
                    value={`${stats.downs} / ${stats.count}`} />
                )}
              </>
            }>
            <div className="mb-2 flex gap-1" role="tablist" aria-label="Rentang histori sinyal">
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
          </ChartCard>
        </div>
      </Section>

      {/* Blok 4: Profil Kecepatan */}
      <Section label="Profil Kecepatan">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b text-xs text-muted">
                <th className={`${cell} w-[45%]`}>Download</th>
                <th className={`${cell} w-[45%]`}>Upload</th>
                <th className={cell}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className={cell}>
                  {dash(d.download_profile_name)}
                  <span className="ml-2 font-mono text-xs text-muted">{dash(d.line_profile_id)}</span>
                </td>
                <td className={cell}>
                  {dash(d.upload_profile_name)}
                  <span className="ml-2 font-mono text-xs text-muted">{dash(d.srv_profile_id)}</span>
                </td>
                <td className={cell}>
                  <Button size="sm" onClick={speedDialog}>Konfigurasi</Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      {/* Blok 5: Port Ethernet — jumlah port dari katalog ONU Types */}
      <Section label="Port Ethernet">
        {specs && specs.eth_ports > 0 ? (
          <>
            <p className="mb-1">
              <span className="font-semibold">{specs.eth_ports} port</span>{" "}
              <span className="text-muted">({specs.name})</span>
            </p>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b text-xs text-muted">
                    <th className={cell}>Port</th>
                    <th className={cell}>Admin state</th>
                    <th className={cell}>Mode</th>
                    <th className={cell}>DHCP</th>
                    <th className={cell}>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: specs.eth_ports }, (_, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className={`${cell} font-mono`}>eth_0/{i + 1}</td>
                      <td className={`${cell} text-muted`}>—</td>
                      <td className={cell}>LAN</td>
                      <td className={`${cell} text-muted`}>—</td>
                      <td className={`${cell} text-faint`}>Segera</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-xs text-muted">
              Status dan konfigurasi port per ONU belum dibaca dari OLT — belum ada transkrip CLI
              nyata untuk port Ethernet ONU.
            </p>
          </>
        ) : (
          <span className="text-muted">
            {specs ? "—" : "Tipe ONU belum terdaftar di ONU Types, jumlah port tidak diketahui."}
          </span>
        )}
      </Section>

      {/* Blok 6: WiFi */}
      <Section label="WiFi">
        {specs && specs.wifi_ssids > 0 ? (
          <>
            <p>
              <span className="font-semibold">{specs.wifi_ssids} SSID</span>{" "}
              <span className="text-muted">({specs.name})</span>
            </p>
            <p className="mt-1 text-xs text-muted">
              Pengaturan SSID/password lewat TR-069: Phase 2.
            </p>
          </>
        ) : (
          <span className="text-muted">—</span>
        )}
      </Section>

      {/* Blok 7: VoIP & CATV */}
      <Section label="Layanan VoIP" tight>
        {specs && specs.voip_ports > 0
          ? <span className="font-semibold">{specs.voip_ports} port</span>
          : <span className="text-muted">Nonaktif</span>}
      </Section>
      <Section label="CATV" tight>
        {specs?.catv
          ? <span className="font-semibold text-up">Didukung</span>
          : <span className="text-muted">Tidak didukung</span>}
      </Section>

      {/* Blok 8: baris aksi (semua lewat konfirmasi + job; RBAC sama seperti sebelumnya) */}
      <section className="flex flex-wrap gap-2 border-t py-4">
        <Button onClick={() => setConfirm("reboot")}>Reboot</Button>
        <Button onClick={() => setConfirm("resync")}>Resync config</Button>
        <Button onClick={infoDialog}>Ubah data pelanggan</Button>
        <Button onClick={speedDialog}>Ubah speed</Button>
        <Button onClick={() => { setForm(String(d.vlan_id ?? "")); setEditing("vlan"); }}>Ubah VLAN</Button>
        {isManager && (
          <Button onClick={() => { setForm(""); setEditing("replace"); }}>Replace ONU / ganti SN</Button>
        )}
        <Button onClick={() => setConfirm("state")}>
          {d.admin_state === "disabled" ? "Aktifkan ONU" : "Nonaktifkan ONU"}
        </Button>
        {isManager && (
          <Button variant="danger" onClick={() => setConfirm("restore-factory")}>Restore factory</Button>
        )}
        {isManager && (
          <Button variant="danger" onClick={() => setConfirm("delete")}>Hapus</Button>
        )}
      </section>

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
