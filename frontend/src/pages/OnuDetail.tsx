/** Detail ONU — PRD 3.4.6. Satu halaman (tidak ada halaman detail kedua).
 *
 *  Tata letak mengikuti desain acuan `design/onu-detail-stitch.html` + screenshot aplikasi
 *  referensi (grid label rata-kanan bold / nilai): bagian atas dua kolom (kiri identitas,
 *  kanan ilustrasi panel belakang ONU + Status + `Rx signal levels` + spesifikasi koneksi) →
 *  baris tombol `Status` (+ panel LIVE realtime saat LIVE aktif) → dua kartu `Traffic/Signal`
 *  → tabel Profil Kecepatan → Port Ethernet → WiFi → Layanan (VoIP/IPTV/CATV) → Aksi siklus
 *  hidup → Log aksi.
 *
 *  Label baris pada dua blok atas DIPAKAI PERSIS seperti aplikasi referensi (bahasa Inggris:
 *  `ONU type`, `Configuration Preset`, `Attached VLANs`, `WAN setup mode`, ...) atas permintaan
 *  pemilik; sisa halaman tetap bahasa Indonesia.
 *
 *  Penyesuaian pemilik terhadap desain acuan (sengaja TIDAK diikuti):
 *  - Shelf/Board, Slot, Port, GPON channel, Tx ONU, suhu, tegangan, MAC TIDAK ditampilkan;
 *  - Rx null = "LOS", tidak pernah digambar sebagai angka (mis. −30) yang tidak dibaca;
 *  - kolom identitas yang memang kosong ditulis `None` miring seperti acuan; baris
 *    spesifikasi koneksi memakai `Inactive`/"—" sesuai aturan pemilik;
 *  - baris `PPPoE username`/`PPPoE password` hanya muncul saat `wan_mode === "pppoe"`;
 *    kata sandi TIDAK PERNAH dirender (backend tidak mengirimnya);
 *  - `Pps`/`Avg size` di panel LIVE = "—": kontrak counter backend hanya octet, tidak ada
 *    counter paket. Tidak ada OID/CLI baru yang ditambahkan ke perangkat untuk ini;
 *  - kartu `Traffic history` (histori jam-jaman) KOSONG dengan keterangan jujur: backend
 *    belum menyimpan sampel counter di DB. Diajukan terpisah, bukan dikarang di frontend;
 *  - tombol `TR-069` dirender MATI (belum ada ACS internal), bukan tombol ke endpoint karangan.
 *
 *  Warna memakai token Nexfiber sendiri (`bg-surface`, `text-fiber`, dst.), bukan palet/CDN
 *  desain acuan, dan tidak ada data contoh dari desain yang disalin: semua nilai dari API.
 *
 *  Satu markup untuk desktop & mobile: kartu dua kolom menumpuk di bawah `lg`, label baris
 *  pindah ke atas di bawah `sm`, tabel dibungkus `overflow-x-auto`, toolbar `flex-wrap`.
 *
 *  Komponen bersama dipakai apa adanya (tidak diubah): Confirm/Drawer/TableCard/Field dari
 *  components/crud.tsx, SignalBar/StatusBadge/Panel dari components/data.tsx. Bucket sinyal
 *  tidak pernah dihitung ulang di halaman ini.
 *
 *  Semua aksi ke perangkat = job: tombol hanya membuat job lalu menunggu statusnya. TANPA
 *  optimistic update (AGENTS.md).
 */
import {
  ArrowDown, ArrowLeft, ArrowSquareOut, ArrowUp, Eye, EyeSlash, Gear, Pencil,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Confirm, Drawer, Field, TableCard, cell, input } from "../components/crud";
import { OnuRearPanel } from "../components/onu/OnuRearPanel";
import {
  ErrorState, Panel, Skeleton, StatusBadge, fmtDateTime, nf, rxBucket, RX_BUCKETS,
} from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, ApiError, type OnuDetail as Detail, type OnuLog, type OnuType, type SignalPoint,
  type SpeedProfile, type Splitter, type Vlan, type Zone,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { DONE, useJob } from "../lib/jobs";
import { cleanProfileName } from "../lib/profileName";
import { deltaMbps, type TrafficPoint, type TrafficSample } from "../lib/traffic";

const RANGES = [["24h", "24 jam"], ["7d", "7 hari"], ["30d", "30 hari"]] as const;
/** Interval auto-refresh detail ONU dari database saat LIVE aktif. */
const LIVE_MS = 15_000;
/** Interval sampel counter trafik saat LIVE aktif (proposal §5: 5 detik, bukan 3). */
const TRAFFIC_MS = 5_000;
/** LIVE mati sendiri setelah ini supaya tab yang ditinggal terbuka tidak memolling OLT terus. */
const LIVE_MAX_MS = 10 * 60_000;
/** Titik grafik yang disimpan (10 menit @5s = 120). */
const TRAFFIC_KEEP = 120;

const dash = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));
const dbm = (v: number | null) => (v === null ? "—" : `${Number(v).toFixed(2)} dBm`);
const mbps = (v: number) => `${v < 10 ? v.toFixed(2) : v.toFixed(1)} Mbps`;

/** Kolom identitas mengikuti acuan: kolom yang memang KOSONG ditulis `None` miring, bukan "—".
 *  Hanya untuk blok identitas — baris spesifikasi koneksi tetap memakai `dash()`/`Inactive`
 *  sesuai aturan pemilik. Tidak pernah mengisi nilai: kosong tetap terlihat kosong. */
const NONE = <span className="italic text-faint">None</span>;
const orNone = (v: unknown) =>
  v === null || v === undefined || v === "" ? NONE : <>{String(v)}</>;

/** Mode WAN yang dikenal aplikasi referensi: default `Setup via ONU webpage`, lalu DHCP /
 *  Static IP / PPPoE untuk ONU yang mendukungnya. Nilai di luar daftar ini DITAMPILKAN APA
 *  ADANYA (bukan error, bukan dipaksa ke salah satu label) supaya mode baru dari perangkat
 *  tetap terbaca operator. Huruf kapital ada di teks label, BUKAN `text-transform` CSS. */
const WAN_MODE_LABEL: Record<string, string> = {
  webpage: "Setup via ONU webpage",
  dhcp: "DHCP",
  static: "Static IP",
  pppoe: "PPPoE",
};
/** Mode yang menampilkan IP WAN + baris PPPoE. `webpage` sengaja tidak punya IP. */
const wanLabel = (mode: string | null) =>
  mode === null || mode === "" ? null : (WAN_MODE_LABEL[mode.toLowerCase()] ?? mode);

/** Mode IP manajemen pada acuan: `Static` / `DHCP`. Nilai lain tampil apa adanya. */
const MGMT_MODE_LABEL: Record<string, string> = { static: "Static", dhcp: "DHCP" };

/** Kartu bagian (desain acuan §3-§9): label di kolom kiri sempit **rata kanan bold**,
 *  isi di kanan. Label pindah ke atas di bawah `md`. */
function Section(
  { label, note, children, className = "" }:
  { label: string; note?: string; children: React.ReactNode; className?: string },
) {
  return (
    <section className={`rounded-md border bg-surface p-3.5 ${className}`}>
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:gap-4">
        <div className="md:w-[130px] md:shrink-0 md:pt-0.5 md:text-right">
          <h2 className="text-xs font-semibold uppercase tracking-[0.05em] text-fiber">{label}</h2>
          {note && <p className="font-mono text-xs text-faint md:mt-0.5">{note}</p>}
        </div>
        <div className="min-w-0 grow">{children}</div>
      </div>
    </section>
  );
}

/** Baris label/nilai mengikuti desain acuan: label kolom kiri **rata kanan bold**
 *  (grid 12: label 4 / nilai 8), menumpuk jadi satu kolom di bawah `sm` supaya tetap
 *  terbaca di 390px. `onEdit` membuat seluruh baris bisa diklik. */
function DRow(
  { label, value, onEdit }: { label: string; value: React.ReactNode; onEdit?: () => void },
) {
  const content = (
    <>
      <span className="text-xs font-semibold text-ink sm:col-span-4 sm:pr-3 sm:text-right">
        {label}
      </span>
      <span className="flex min-w-0 flex-wrap items-center gap-1.5 font-mono text-xs text-muted sm:col-span-8">
        {onEdit && <Pencil size={12} aria-hidden className="text-faint" />}
        {value}
      </span>
    </>
  );
  const shape = "grid w-full gap-0.5 border-b py-1 last:border-0 sm:grid-cols-12 sm:items-baseline sm:gap-x-2 sm:border-0 sm:py-0.5";
  return onEdit ? (
    <button type="button" onClick={onEdit} className={`${shape} text-left hover:text-fiber`}>
      {content}
    </button>
  ) : (
    <div className={shape}>{content}</div>
  );
}

/** Header kartu: judul kecil + keterangan, pola berulang di desain Stitch. */
function CardHead({ title, note, action }: { title: string; note?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-2.5 flex flex-wrap items-center gap-2 border-b pb-2">
      <h3 className="font-mono text-xs font-semibold uppercase tracking-[0.05em]">{title}</h3>
      {note && <span className="font-mono text-xs text-faint">{note}</span>}
      {action && <span className="ml-auto">{action}</span>}
    </div>
  );
}

/** Nama pengguna PPPoE: tersembunyi secara default, dibuka manual lewat tombol mata
 *  (pola desain acuan — teksnya `**********` dengan panjang tetap supaya panjang nilai
 *  nyata tidak ikut terbaca). Hanya menampilkan nilai yang MEMANG dikirim backend —
 *  kata sandi tidak pernah ada di props mana pun. */
function PppoeUser({ value }: { value: string }) {
  const [shown, setShown] = useState(false);
  return (
    <>
      <span className={shown ? "" : "tracking-wider"}>{shown ? value : "**********"}</span>
      <button type="button" onClick={() => setShown(!shown)}
              aria-pressed={shown}
              className="text-fiber hover:underline"
              title={shown ? "Sembunyikan" : "Tampilkan"}>
        {shown ? <EyeSlash size={14} aria-hidden /> : <Eye size={14} aria-hidden />}
        <span className="sr-only">{shown ? "Sembunyikan nama pengguna PPPoE" : "Tampilkan nama pengguna PPPoE"}</span>
      </button>
    </>
  );
}

/** Tautan ke alamat IP perangkat: tab baru + ikon keluar seperti acuan. Dipakai untuk
 *  IP WAN dan IP manajemen; `http://` karena yang dituju halaman web ONU di LAN. */
function IpLink({ ip }: { ip: string }) {
  return (
    <a className="inline-flex items-center gap-1 text-fiber hover:underline" href={`http://${ip}`}
       target="_blank" rel="noopener noreferrer">
      {ip}
      <ArrowSquareOut size={12} aria-hidden />
    </a>
  );
}

function fmtDistance(m: number | null) {
  if (m === null) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${nf.format(m)} m`;
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

/** Kotak satu arah sinyal Rx (ONU 1490nm / OLT 1310nm) seperti dua kotak di desain:
 *  nilai besar + label bucket + bar. Bucket & warna dari RX_BUCKETS bersama. */
function RxBox({ title, value }: { title: string; value: number | null }) {
  const b = rxBucket(value);
  const meta = b ? RX_BUCKETS[b] : null;
  /** Posisi bar: -8 dBm (kuat) .. -30 dBm (lemah), dipakai hanya sebagai indikator visual. */
  const pct = value === null ? 0 : Math.max(0, Math.min(100, ((value + 30) / 22) * 100));
  return (
    <div className="flex flex-col gap-1.5 rounded-sm border bg-sunken p-2.5">
      <div className="flex items-center justify-between gap-2 font-mono text-xs">
        <span className="text-muted">{title}</span>
        <span className={meta ? `font-semibold ${meta.color.replace("bg-", "text-")}` : "text-muted"}>
          {meta ? meta.label : "LOS"}
        </span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-lg font-semibold">{value === null ? "LOS" : value.toFixed(2)}</span>
        {value !== null && <span className="font-mono text-xs text-faint">dBm</span>}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-sm bg-app">
        <div className={`h-full ${meta ? meta.color : "bg-sunken"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
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
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-32 w-full" role="img"
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

/** Grafik trafik LIVE: dua polyline dari delta counter nyata, sumbu Y Mbps berskala otomatis
 *  seperti acuan (puncak dibulatkan ke atas ke langkah yang rapi). Tidak pernah menggambar
 *  nilai karangan — selama sampel belum cukup yang tampil adalah keterangan, bukan garis nol. */
function LiveChart({ points }: { points: TrafficPoint[] }) {
  if (points.length < 2) {
    return (
      <p className="py-10 text-center text-muted">
        Mengambil sampel counter dari OLT setiap {TRAFFIC_MS / 1000} detik. Butuh dua sampel
        sebelum laju bisa dihitung.
      </p>
    );
  }
  const peak = Math.max(...points.flatMap((p) => [p.inMbps, p.outMbps]));
  /** Skala sumbu: 5 garis (0 .. top) dengan `top` dibulatkan ke 1/2/5 × 10^n di atas puncak. */
  const top = niceTop(peak);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  const x = (i: number) => (i / (points.length - 1)) * 100;
  const y = (v: number) => 100 - (v / top) * 100;
  const path = (pick: (p: TrafficPoint) => number) =>
    points.map((p, i) => `${x(i)},${y(pick(p))}`).join(" ");
  return (
    <div className="flex gap-2">
      {/* Label sumbu Y di luar SVG: SVG-nya non-uniform scale, teks di dalamnya ikut melar. */}
      <div className="flex w-12 shrink-0 flex-col justify-between py-0.5 text-right font-mono text-[10px] text-faint">
        {[...ticks].reverse().map((t, i) => <span key={i}>{axisTick(t)}</span>)}
      </div>
      <div className="min-w-0 grow">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-40 w-full" role="img"
             aria-label={`Grafik trafik LIVE, ${points.length} sampel, puncak ${peak.toFixed(2)} Mbps`}>
          {ticks.map((t) => (
            <line key={t} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
                  strokeWidth="0.3" className="text-line" vectorEffect="non-scaling-stroke" />
          ))}
          <polyline points={path((p) => p.outMbps)} fill="none" stroke="currentColor" strokeWidth="1.5"
                    className="text-amber" vectorEffect="non-scaling-stroke" />
          <polyline points={path((p) => p.inMbps)} fill="none" stroke="currentColor" strokeWidth="1.5"
                    className="text-fiber" vectorEffect="non-scaling-stroke" />
        </svg>
        <p className="mt-1 text-center font-mono text-[10px] text-faint">Mbps</p>
      </div>
    </div>
  );
}

/** Batas atas sumbu yang "rapi": 1, 2, 5 × 10^n tepat di atas nilai puncak. */
function niceTop(peak: number) {
  if (!(peak > 0)) return 1;
  const pow = 10 ** Math.floor(Math.log10(peak));
  for (const m of [1, 2, 5, 10]) if (peak <= m * pow) return m * pow;
  return 10 * pow;
}

const axisTick = (v: number) => (v === 0 ? "0" : v < 1 ? v.toFixed(1) : String(Number(v.toFixed(1))));

/** Satu baris ringkasan arah (naik/turun) di bawah grafik LIVE, mengikuti acuan:
 *  Speed / Max / Pps / Avg size. `Pps` dan `Avg size` butuh counter PAKET yang BELUM ADA di
 *  kontrak backend (`OnuTrafficSample` hanya mengirim octet) — jadi keduanya "—", bukan angka
 *  hasil pembagian yang tidak punya sumber. */
function LiveRow(
  { dir, label, color, speed, max }:
  { dir: "up" | "down"; label: string; color: string; speed: number | null; max: number | null },
) {
  const Arrow = dir === "up" ? ArrowUp : ArrowDown;
  const cell = (k: string, v: string) => (
    <span className="flex items-baseline gap-1">
      <span className="text-faint">{k}</span>
      <span className="text-ink">{v}</span>
    </span>
  );
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b py-1.5 font-mono text-xs last:border-0">
      <span className={`flex items-center gap-1 font-semibold ${color}`}>
        <Arrow size={12} aria-hidden />
        {label}
      </span>
      <span className={`font-semibold ${color}`}>{speed === null ? "—" : mbps(speed)}</span>
      {cell("Max", max === null ? "—" : mbps(max))}
      {cell("Pps", "—")}
      {cell("Avg size", "—")}
    </div>
  );
}

/** Kartu grafik: judul + isi + legenda, dua kartu sejajar seperti desain. */
function ChartCard(
  { title, note, children, legend }:
  { title: string; note?: string; children: React.ReactNode; legend?: React.ReactNode },
) {
  return (
    <div className="min-w-0 flex-1 rounded-sm border bg-sunken p-3">
      <CardHead title={title} note={note} />
      {children}
      {legend && <div className="mt-2 grid gap-1 border-t pt-2 text-xs text-muted">{legend}</div>}
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

/** VLAN terpasang = DAFTAR, bukan satu nilai. Sumbernya seluruh `service-port` ONU di
 *  running-config (mis. 15 dan 100 sekaligus). Backend mengirimnya sebagai
 *  `service_vlans` pada detail ONU — kontrak milik track metadata ONU
 *  (`ONU-METADATA-VLAN-SOURCE-PROPOSAL.md` §4), bukan tebakan halaman ini.
 *
 *  Baris dengan penanda management DISEMBUNYIKAN. Penandanya `is_management` dari backend
 *  (yang menurunkannya dari `vlans.type == "management"` di master), **tidak pernah** dari
 *  nomor VLAN — tidak ada 100 atau angka lain yang di-hardcode di sini.
 *
 *  Daftar kosong ditampilkan apa adanya ("—"): semua VLAN-nya management atau ONU memang
 *  tidak punya service-port. Tidak ada fallback ke `vlan_number`.
 *
 *  `vlan_number` lama tetap dipakai HANYA oleh dialog "Ubah VLAN" (menulis satu VLAN
 *  primer) dan sebagai tampilan sementara selagi `service_vlans` belum dikirim backend —
 *  dengan keterangan eksplisit bahwa daftarnya belum tersedia, bukan daftar karangan.
 *  Semua field dibuat opsional supaya bentuk final kontrak sibling tidak memaksa
 *  perubahan tipe bersama di `lib/api.ts`. */
type OnuServiceVlan = {
  vlan_id?: number | null;
  name?: string | null;
  is_management?: boolean | null;
  /** `false` = ada di perangkat tapi belum terdaftar di master VLAN; tetap ditampilkan. */
  in_master?: boolean | null;
};

type DetailWithVlans = Detail & {
  service_vlans?: OnuServiceVlan[] | null;
  /** Hasil parse `description` ONU di perangkat (read-only; belum tentu = kolom operator).
   *  Dipakai hanya sebagai sumber kedua saat kolom master kosong, dan selalu ditandai
   *  asalnya — placeholder master yang kosong tidak boleh menutupi nilai nyata yang memang
   *  ada di description perangkat. `authorized_on` murni dari penanda `_authd_`: kalau
   *  backend mengirim null, barisnya "—" dan TIDAK diturunkan dari registered_at. */
  device_metadata?: {
    zone?: string | null;
    address?: string | null;
    splitter?: string | null;
    authorized_on?: string | null;
    structured?: boolean | null;
  } | null;
};

/** Nilai + penanda asal: kolom master dulu; kalau kosong pakai hasil parse `description`
 *  perangkat dan beri label asalnya. `null` di keduanya = "—". Keduanya tidak pernah
 *  ditampilkan sebagai hal yang sama. */
function fromMasterOrDescription(master: unknown, parsed: string | null | undefined) {
  const m = master === null || master === undefined || master === "" ? null : String(master);
  if (m !== null) return <>{m}</>;
  const p = parsed === null || parsed === undefined || parsed === "" ? null : parsed;
  if (p === null) return <>—</>;
  return (
    <>
      <span>{p}</span>
      <span className="text-faint">dari description perangkat</span>
    </>
  );
}

const isManagementVlan = (v: OnuServiceVlan) => v.is_management === true;

/** VLAN layanan yang boleh tampil: punya nomor, bukan VLAN management, tanpa duplikat.
 *  `null` = backend belum mengirim `service_vlans` (beda dari daftar kosong yang nyata). */
function serviceVlans(d: DetailWithVlans): OnuServiceVlan[] | null {
  if (!Array.isArray(d.service_vlans)) return null;
  const rows = d.service_vlans;
  const seen = new Set<number>();
  return rows.filter((v) => {
    if (typeof v.vlan_id !== "number" || isManagementVlan(v)) return false;
    if (seen.has(v.vlan_id)) return false;
    seen.add(v.vlan_id);
    return true;
  });
}

/** View diagnostik = isi body `POST /api/onus/{sn}/diagnostics` (kontrak backend sibling). */
type DiagView = "status" | "running" | "software";

const DIAG_LABEL: Record<DiagView, string> = {
  status: "Get status",
  running: "Show running-config",
  software: "SW info",
};

/** LIVE trafik: ambil satu snapshot counter per interval, ubah jadi titik Mbps.
 *
 *  - berhenti total saat `enabled` false dan saat komponen unmount (interval di-clear,
 *    hasil fetch yang datang terlambat diabaikan lewat flag `alive`);
 *  - dijeda saat tab tidak terlihat (`document.hidden`) — tanpa menutup LIVE;
 *  - sampel pertama hanya baseline (tidak ada titik), delta dihitung di lib/traffic.ts;
 *  - sampel yang tidak bisa dipercaya (counter reset / wrap tak wajar) membuang baseline
 *    dan mulai lagi, bukan menggambar lonjakan palsu.
 */
function useLiveTraffic(serial: string, enabled: boolean) {
  const [points, setPoints] = useState<TrafficPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<TrafficSample | null>(null);
  const prev = useRef<TrafficSample | null>(null);

  useEffect(() => {
    if (!enabled) {
      prev.current = null;
      // Titik dibuang saat LIVE mati: "Max" di panel = maksimum sesi LIVE yang sedang jalan,
      // bukan sisa sesi sebelumnya yang sudah tidak terlihat di grafik.
      setPoints([]);
      setLast(null);
      setError(null);
      return;
    }
    let alive = true;
    const tick = async () => {
      if (document.hidden) return;
      try {
        const s = await api<TrafficSample>(`/api/onus/${serial}/traffic`);
        if (!alive) return;
        setError(null);
        setLast(s);
        const before = prev.current;
        prev.current = s;
        if (!before) return;
        const point = deltaMbps(before, s);
        if (point === null) return; // counter reset/jump: baseline baru, tanpa titik palsu
        setPoints((p) => [...p, point].slice(-TRAFFIC_KEEP));
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Gagal membaca counter trafik");
      }
    };
    void tick();
    const id = setInterval(() => void tick(), TRAFFIC_MS);
    return () => {
      alive = false;
      clearInterval(id);
      prev.current = null;
    };
  }, [serial, enabled]);

  return { points, error, last };
}

/** Param URL `/onu/:id` boleh berupa **ID numerik** (tautan dari Detail OLT) atau serial
 *  number (tautan dari Configured/Form Otorisasi). Detail diambil lewat endpoint yang sesuai;
 *  seluruh operasi per-ONU tetap memakai `d.serial_number` dari respons, bukan nilai URL —
 *  jadi tidak ada tebakan bahwa angka di URL sama dengan serial.
 *
 *  Kontrak yang dipakai untuk bentuk numerik: `GET /api/onus/by-id/{onu_id}` -> OnuDetail
 *  (dimiliki track backend resolver). Selama endpoint itu belum ada, bentuk numerik gagal
 *  dengan pesan API apa adanya — tidak ada fallback yang menebak serial dari ID. */
const isNumericId = (v: string) => /^\d+$/.test(v);
const detailPath = (param: string) =>
  isNumericId(param) ? `/api/onus/by-id/${param}` : `/api/onus/${encodeURIComponent(param)}`;

export function OnuDetail() {
  const { id: routeKey = "" } = useParams();
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
  /** Panel output diagnostik: satu panel, isi = hasil job view yang terakhir diminta. */
  const [diagView, setDiagView] = useState<DiagView | null>(null);
  const [diagJobId, setDiagJobId] = useState<number | null>(null);
  /** View tombol yang sedang berjalan (penanda tombol aktif); null = tidak ada pembacaan. */
  const [diagRunView, setDiagRunView] = useState<DiagView | null>(null);
  /** Pesan khusus toolbar diagnostik (mis. penolakan 409), terpisah dari `note` aksi job. */
  const [diagMsg, setDiagMsg] = useState("");
  /** Waktu mulai pembacaan (ms epoch) untuk penghitung detik; tetap sama saat job_id datang. */
  const [diagStart, setDiagStart] = useState<number | null>(null);
  const [diagSecs, setDiagSecs] = useState(0);
  const [live, setLive] = useState(false);

  const onu = useQuery({
    queryKey: ["onu", routeKey],
    queryFn: () => api<DetailWithVlans>(detailPath(routeKey)),
    refetchInterval: live ? LIVE_MS : false,
  });
  /** Satu-satunya identitas untuk semua operasi: serial dari respons detail. */
  const serial = onu.data?.serial_number ?? "";
  const signal = useQuery({
    queryKey: ["onu", serial, "signal", range],
    queryFn: () => api<SignalPoint[]>(`/api/onus/${serial}/signal?range=${range}`),
    enabled: serial !== "",
  });
  const logs = useQuery({
    queryKey: ["onu", serial, "logs"],
    queryFn: () => api<OnuLog[]>(`/api/onus/${serial}/logs?limit=50`),
    enabled: serial !== "",
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
  const diagJob = useJob(diagJobId);
  const traffic = useLiveTraffic(serial, live && serial !== "");

  /** LIVE mati sendiri setelah LIVE_MAX_MS; mati juga saat halaman ditinggalkan. */
  useEffect(() => {
    if (!live) return;
    const id = setTimeout(() => setLive(false), LIVE_MAX_MS);
    return () => clearTimeout(id);
  }, [live]);
  useEffect(() => () => setLive(false), []);

  /** Edit data pelanggan/lokasi: kolom database saja, jadi langsung PATCH (bukan job). */
  const saveInfo = useMutation({
    mutationFn: (f: InfoForm) =>
      api<Detail>(`/api/onus/${serial}/info`, { method: "PATCH", json: infoPayload(f) }),
    onSuccess: () => {
      setEditing(null);
      setNote("Data pelanggan disimpan.");
      qc.invalidateQueries({ queryKey: ["onu"] });
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
      qc.invalidateQueries({ queryKey: ["onu"] });
    },
    onError: (e: Error) => setNote(e.message),
  });

  /** Diagnostik baca-saja: satu job per tombol (backend sibling), hasilnya string output. */
  const diag = useMutation({
    mutationFn: (view: DiagView) =>
      api<{ job_id: number }>(`/api/onus/${serial}/diagnostics`, { method: "POST", json: { view } }),
    onSuccess: (r, view) => {
      setDiagView(view);
      setDiagJobId(r.job_id);
    },
    onError: (e: Error) => {
      setDiagRunView(null);
      // 409 = backend sengaja menolak job sejenis yang tumpang-tindih untuk ONU yang sama.
      // Pesannya dibuat jelas dan panel hasil sebelumnya dibiarkan utuh.
      if (e instanceof ApiError && e.status === 409) {
        setDiagMsg("Pembacaan untuk ONU ini masih berjalan, tunggu selesai.");
        return;
      }
      setNote(e.message);
    },
  });

  /** Satu job diagnostik butuh ~4-8 detik di OLT, jadi tombol harus mati sampai job SELESAI
   *  (success/failed/cancelled), bukan hanya selama request POST. Polling job berhenti sendiri
   *  saat status selesai (useJob di lib/jobs.ts). */
  const diagJobActive =
    diagJobId !== null && !diagJob.isError && !(diagJob.data && DONE.has(diagJob.data.status));
  const diagRunning = diag.isPending || diagJobActive;

  /** Penghitung detik berjalan selama pembacaan, dihitung dari waktu klik. */
  useEffect(() => {
    if (!diagRunning || diagStart === null) return;
    const tick = () => setDiagSecs(Math.floor((Date.now() - diagStart) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [diagRunning, diagStart]);

  if (onu.isPending) return <Skeleton text="Memuat detail ONU ..." rows={6} />;
  if (onu.isError || !onu.data) {
    return <ErrorState message={onu.error?.message ?? "Gagal memuat ONU"} onRetry={() => onu.refetch()} />;
  }
  const d = onu.data;
  const stats = rxStats(signal.data ?? []);
  const specs = (onuTypes.data ?? []).find(
    (t) => t.id === d.onu_type_id || t.name.toLowerCase() === (d.onu_type ?? "").toLowerCase(),
  );
  const statusKey = d.admin_state === "disabled" ? "disabled" : d.status;
  /** `null` = backend belum mengirim daftar VLAN (field `vlans`), bukan "tidak ada VLAN". */
  const vlanList = serviceVlans(d);
  const meta = d.device_metadata ?? null;
  const onuIf = `gpon-onu_${d.slot}/${d.port}${d.onu_index === null ? "" : `:${d.onu_index}`}`;
  const latest = traffic.points.at(-1) ?? null;
  /** "Max" di panel LIVE = puncak sejak LIVE dinyalakan (titik dibuang saat LIVE mati). */
  const liveMax = traffic.points.length === 0 ? null : {
    out: Math.max(...traffic.points.map((p) => p.outMbps)),
    in: Math.max(...traffic.points.map((p) => p.inMbps)),
  };
  /** Teks baris spesifikasi koneksi. Semuanya turunan data nyata — tidak ada nilai cadangan. */
  const wanMode = wanLabel(d.wan_mode);
  const isPppoe = (d.wan_mode ?? "").toLowerCase() === "pppoe";
  /** `webpage` = konfigurasi dilakukan di halaman web ONU, tidak ada IP WAN yang dibaca OLT. */
  const wanHasIp = wanMode !== null && (d.wan_mode ?? "").toLowerCase() !== "webpage";
  /** Mgmt IP hanya punya mode Static/DHCP di acuan; nilai lain tampil apa adanya. */
  const mgmtMode = d.mgmt_ip_mode === null || d.mgmt_ip_mode === ""
    ? null
    : (MGMT_MODE_LABEL[d.mgmt_ip_mode.toLowerCase()] ?? d.mgmt_ip_mode);
  /** VLAN WAN pada "ONU mode" = VLAN layanan ONU dari `service_vlans`. Tidak ada fallback ke
   *  `vlan_number` (satu VLAN primer di master ≠ VLAN WAN perangkat): tanpa daftar nyata,
   *  nomornya tidak ditempel sama sekali. */
  const wanVlan = vlanList && vlanList.length > 0 ? vlanList[0].vlan_id ?? null : null;

  const runDiag = (view: DiagView) => {
    if (diagRunning) return; // tombol sudah disabled; jaga-jaga bila terpanggil lewat keyboard
    setDiagMsg("");
    setDiagRunView(view);
    setDiagStart(Date.now());
    setDiagSecs(0);
    diag.mutate(view);
  };

  /** Isi panel output: hanya string yang dikirim backend. Tidak ada rakitan teks di frontend
   *  (satu formatter saja, di backend), tidak ada nilai contoh saat job belum selesai. */
  const diagResult = (diagJob.data?.result ?? {}) as Record<string, unknown>;
  const diagOutput = typeof diagResult.output === "string" ? diagResult.output : "";
  const diagOutputView = typeof diagResult.view === "string" ? diagResult.view : null;
  const diagStatus = diagJob.data?.status ?? (diagRunning ? "pending" : null);
  const diagText = () => {
    if (diagRunning) {
      return `Sedang membaca dari OLT ... ${diagSecs}s`;
    }
    if (diagOutput && (diagOutputView === null || diagOutputView === diagView)) return diagOutput;
    if (diagJob.data?.status === "failed") {
      return `Job #${diagJob.data.id} gagal: ${diagJob.data.error_message ?? "tanpa keterangan"}`;
    }
    return `Menunggu hasil job pembacaan "${DIAG_LABEL[diagView ?? "status"]}" dari OLT ...`;
  };

  const infoDialog = () => { setInfo(infoFrom(d)); setEditing("info"); };
  const speedDialog = () => {
    setDnForm(String(d.download_speed_profile_id ?? ""));
    setUpForm(String(d.upload_speed_profile_id ?? ""));
    setEditing("speed");
  };
  const vlanDialog = () => { setForm(String(d.vlan_id ?? "")); setEditing("vlan"); };
  const replaceDialog = () => { setForm(""); setEditing("replace"); };

  return (
    <div className="space-y-4">
      {/* Breadcrumb halaman (desain Stitch): kembali + identitas ONU dalam satu baris padat.
          Header aplikasi & navigasi tidak disentuh — ini milik halaman ini saja. */}
      <div className="flex flex-wrap items-center gap-2 border-b pb-2.5 text-xs">
        <Link to="/configured" className="inline-flex items-center gap-1 text-fiber hover:underline">
          <ArrowLeft size={14} aria-hidden /> Kembali ke Configured
        </Link>
        <span className="text-faint">/</span>
        <span className="font-mono text-muted">{onuIf}</span>
        <span className="text-faint">•</span>
        <span className="text-muted">OLT:</span>
        <Link to={`/olt/${d.olt_id}`} className="font-mono font-semibold text-fiber hover:underline">
          {d.olt_name}
        </Link>
        <span className="text-faint">•</span>
        <h1 className="text-sm font-semibold">{d.customer_name ?? d.name ?? d.serial_number}</h1>
        <span className="rounded-sm border border-fiber/40 bg-sunken px-2 py-0.5 font-mono text-xs font-semibold text-fiber">
          SN: {d.serial_number}
        </span>
        {d.onu_type && (
          <span className="rounded-sm bg-sunken px-1.5 py-0.5 font-mono text-xs text-muted">{d.onu_type}</span>
        )}
      </div>

      {(note || job.data) && (
        <p className="text-muted" role="status">
          {note}{job.data ? ` Status job: ${job.data.status}${job.data.error_message ? ` — ${job.data.error_message}` : ""}` : ""}
        </p>
      )}

      {/* 1. BAGIAN ATAS (desain acuan §1): kiri meta, kanan ilustrasi panel + status +
          kartu Rx + spesifikasi koneksi. Menumpuk di bawah `lg`. */}
      <div className="overflow-hidden rounded-md border bg-surface">
        <div className="grid divide-y lg:grid-cols-2 lg:divide-x lg:divide-y-0">
          <div className="min-w-0 p-4">
            <CardHead title="Informasi & status ONU" note={`Sinkron terakhir ${fmtDateTime(d.last_sync_at)}`} />
            <div className="flex flex-col">
              <DRow label="OLT" value={
                <Link className="text-fiber hover:underline" to={`/olt/${d.olt_id}`}>{d.olt_name}</Link>
              } />
              <DRow label="ONU" value={
                <Link className="text-fiber hover:underline" to={`/configured?olt_id=${d.olt_id}`}>
                  {onuIf}
                </Link>
              } />
              <DRow label="SN" value={<span className="font-semibold text-fiber">{d.serial_number}</span>}
                    onEdit={isManager ? replaceDialog : undefined} />
              <DRow label="ONU type" value={orNone(d.onu_type)} />
              <DRow label="Configuration Preset" value={orNone(d.preset_name)} />
              <DRow label="Zone" value={fromMasterOrDescription(d.zone_name, meta?.zone)} onEdit={infoDialog} />
              <DRow label="Splitter" onEdit={infoDialog} value={
                d.splitter_name
                  ? `${d.splitter_name}${d.splitter_port ? ` · port ${d.splitter_port}` : ""}`
                  : fromMasterOrDescription(null, meta?.splitter)
              } />
              {/* Sector belum ada kolomnya di master data Nexfiber: baris tetap ada supaya
                  urutan acuan utuh, nilainya `None` karena memang tidak ada datanya. */}
              <DRow label="Sector" value={NONE} />
              <DRow label="Name" value={orNone(d.customer_name ?? d.name)} onEdit={infoDialog} />
              <DRow label="Address or comment"
                    value={fromMasterOrDescription(d.address, meta?.address ?? d.description)}
                    onEdit={infoDialog} />
              <DRow label="Contact" value={orNone(d.contact ?? d.phone)} onEdit={infoDialog} />
              <DRow label="Authorization date" value={
                <>
                  {fromMasterOrDescription(
                    d.registered_at ? fmtDateTime(d.registered_at) : null,
                    meta?.authorized_on,
                  )}
                  {d.registered_by_name && (
                    <span className="text-muted">oleh {d.registered_by_name}</span>
                  )}
                  {/* "History" pada acuan = tautan ke riwayat ONU; di Nexfiber riwayatnya ada
                      di halaman Logs, dicari lewat param `q` yang memang dipakai halaman itu. */}
                  <Link className="text-fiber hover:underline" to={`/logs?q=${encodeURIComponent(d.serial_number)}`}>
                    History
                  </Link>
                </>
              } />
              <DRow label="ONU external ID" value={orNone(d.external_id)} onEdit={infoDialog} />
              <DRow label="Lokasi" value={d.latitude !== null && d.longitude !== null
                ? <a className="text-fiber hover:underline" target="_blank" rel="noreferrer"
                     href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=17/${d.latitude}/${d.longitude}`}>
                    {Number(d.latitude).toFixed(5)}, {Number(d.longitude).toFixed(5)}
                  </a>
                : "—"} />
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-3 p-4">
            {/* (a) Ilustrasi panel belakang modem — hanya bila katalog ONU Types tahu
                jumlah port nyatanya; tidak digambar dari tebakan. */}
            {specs && (specs.eth_ports > 0 || specs.voip_ports > 0) && (
              <OnuRearPanel ethPorts={specs.eth_ports} voipPorts={specs.voip_ports}
                            online={d.status === "online" && d.admin_state !== "disabled"} />
            )}

            {/* (b) Baris status + jarak + muat ulang */}
            <div className="flex flex-wrap items-center gap-3 border-b pb-2.5">
              <span className="text-xs font-semibold text-ink">Status</span>
              <StatusBadge status={statusKey} reason={d.last_down_reason} withLabel />
              <span className="font-mono text-xs text-muted">{fmtDistance(d.distance_m)}</span>
              <Button size="sm" variant="quiet" onClick={() => onu.refetch()} disabled={onu.isFetching}>
                {onu.isFetching ? "Memuat ..." : "Muat ulang"}
              </Button>
              {live && (
                <span className="font-mono text-xs text-fiber">auto-refresh {LIVE_MS / 1000}s</span>
              )}
            </div>

            {/* (c) Kartu Rx: dua kotak sebelah-menyebelah seperti desain */}
            <div className="rounded-sm border bg-app p-3">
              <CardHead title="Rx signal levels" note="Normal −8,0 s/d −27,0 dBm" />
              <div className="grid gap-2 sm:grid-cols-2">
                <RxBox title="ONU Rx 1490nm" value={d.rx_power_dbm} />
                <RxBox title="OLT Rx 1310nm" value={d.olt_rx_power_dbm} />
              </div>
            </div>

            {/* (d) Spesifikasi koneksi — label persis acuan (Inggris, permintaan pemilik):
                TR069 Profile, Mgmt IP, Attached VLANs, ONU mode, WAN setup mode, lalu dua
                baris PPPoE HANYA saat modenya pppoe. */}
            <div className="flex flex-col">
              {/* Nexfiber belum punya profil ACS/TR-069 internal (DECISIONS.md), jadi nilainya
                  selalu `Inactive` apa adanya — bukan badge "via Mgmt IP" milik aplikasi lain. */}
              <DRow label="TR069 Profile" value="Inactive" />
              {/* Mgmt IP mengikuti acuan: "<Static|DHCP> - vlan: N - IP". Potongan yang tidak
                  dikirim backend hilang dari teks; tanpa mode sama sekali = `Inactive`. */}
              <DRow label="Mgmt IP" value={
                mgmtMode === null ? "Inactive" : (
                  <>
                    <span>
                      {mgmtMode}
                      {d.vlan_id !== null && ` - vlan: ${d.vlan_id}`}
                      {d.ip_address && " - "}
                    </span>
                    {d.ip_address && <IpLink ip={d.ip_address} />}
                  </>
                )
              } />
              <DRow label="Attached VLANs" value={
                vlanList === null ? (
                  <>
                    <span>{dash(d.vlan_number)}</span>
                    <span className="text-faint">daftar lengkap belum dikirim backend</span>
                  </>
                ) : vlanList.length === 0 ? (
                  <span className="text-muted">—</span>
                ) : (
                  <>
                    {vlanList.map((v) => (
                      <span key={v.vlan_id} className="rounded-sm bg-sunken px-1.5 py-0.5"
                            title={v.name ?? undefined}>
                        {v.vlan_id}
                        {v.in_master === false && <span className="ml-0.5 text-warn">*</span>}
                      </span>
                    ))}
                    {vlanList.some((v) => v.in_master === false) && (
                      <span className="text-faint">* belum terdaftar di master VLAN</span>
                    )}
                  </>
                )
              } onEdit={vlanDialog} />
              {/* "Routing - WAN vlan: N" seperti acuan; nomor VLAN hanya ditempel bila ada. */}
              <DRow label="ONU mode" value={
                d.onu_mode === null || d.onu_mode === ""
                  ? "—"
                  : `${d.onu_mode}${wanVlan === null ? "" : ` - WAN vlan: ${wanVlan}`}`
              } />
              {/* WAN setup mode: label mode dari WAN_MODE_LABEL (huruf kapital di teks, bukan
                  CSS uppercase) + IP sebagai tautan tab baru. `webpage` tidak punya IP WAN. */}
              <DRow label="WAN setup mode" value={
                wanMode === null ? "—" : (
                  <>
                    <span>{wanMode}</span>
                    {wanHasIp && d.ip_address && <IpLink ip={d.ip_address} />}
                  </>
                )
              } />
              {/* Dua baris PPPoE hanya untuk mode pppoe; static/dhcp/webpage menyembunyikannya
                  sepenuhnya. Kata sandi TIDAK PERNAH dikirim backend, jadi barisnya ada (sesuai
                  acuan) tapi isinya keterangan jujur, bukan nilai palsu di balik tombol mata. */}
              {isPppoe && (
                <>
                  <DRow label="PPPoE username" value={
                    d.pppoe_username
                      ? <PppoeUser value={d.pppoe_username} />
                      : "—"
                  } />
                  <DRow label="PPPoE password" value={<span className="text-faint">Tidak ditampilkan</span>} />
                </>
              )}
              <DRow label="Otentikasi" value={d.auth_type === "loid" ? `LOID · ${dash(d.loid)}` : d.auth_type.toUpperCase()} />
              <DRow label="Match state" value={dash(d.match_state)} />
              <DRow label="Config state" value={dash(d.config_state)} />
              <DRow label="Bias laser" value={
                d.bias_current_ma === null ? "—" : `${Number(d.bias_current_ma).toFixed(2)} mA`
              } />
              <DRow label="Terakhir online" value={fmtDateTime(d.last_seen_at)} />
              <DRow label="Last down" value={d.last_down_at
                ? `${dash(d.last_down_reason)} · ${fmtDateTime(d.last_down_at)}` : "—"} />
            </div>
          </div>
        </div>
      </div>

      {/* 2. TOOLBAR STATUS (desain acuan §2): label kiri rata kanan + tombol diagnostik.
          Logika/handler diagnostik tidak diubah — tetap lewat job CLI backend. */}
      <section className="rounded-md border bg-surface p-3.5">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:gap-4">
          <div className="md:w-[130px] md:shrink-0 md:pt-1 md:text-right">
            <h2 className="text-xs font-semibold uppercase tracking-[0.05em] text-fiber">
              Status
            </h2>
          </div>
          <div className="min-w-0 grow">
            <div className="flex flex-wrap items-center gap-1.5">
              <Button size="sm" onClick={() => runDiag("status")} disabled={diagRunning}>
                {DIAG_LABEL.status}{diagRunning && diagRunView === "status" ? " ..." : ""}
              </Button>
              {/* Running-config utuh memuat nilai konfigurasi sensitif: tombolnya hanya dirender
                  untuk admin/superadmin, dan backend tetap menolak role lain (403). */}
              {isManager && (
                <Button size="sm" onClick={() => runDiag("running")} disabled={diagRunning}>
                  {DIAG_LABEL.running}{diagRunning && diagRunView === "running" ? " ..." : ""}
                </Button>
              )}
              <Button size="sm" onClick={() => runDiag("software")} disabled={diagRunning}>
                {DIAG_LABEL.software}{diagRunning && diagRunView === "software" ? " ..." : ""}
              </Button>
              {/* Tombol TR-069 ada di acuan, tapi Nexfiber belum punya ACS internal
                  (DECISIONS.md): dirender MATI dengan alasan yang jelas, bukan tombol yang
                  menembak endpoint karangan. */}
              <Button size="sm" variant="secondary" disabled
                      title="Butuh profil ACS/TR-069 internal yang belum ada di Nexfiber">
                TR-069
              </Button>
              <span className="ml-auto flex items-center gap-1.5">
                {diagView && diagOutput && !diagRunning && (
                  <Button size="sm" variant="quiet"
                          onClick={() => navigator.clipboard?.writeText(diagOutput)}>
                    Salin
                  </Button>
                )}
                <Button size="sm" variant={live ? "fiber" : "secondary"} aria-pressed={live}
                        onClick={() => setLive(!live)}>
                  <Gear size={13} aria-hidden className={live ? "animate-spin" : ""} />
                  LIVE!
                </Button>
              </span>
            </div>
            {diagMsg && (
              <p className="mt-2 text-sm text-amber" role="status">{diagMsg}</p>
            )}
            {/* Panel realtime HANYA saat LIVE aktif (acuan screenshot ke-2): grafik Mbps +
                dua baris ringkasan arah. Saat LIVE mati panel ini TIDAK dirender sama sekali. */}
            {live && (
              <div className="mt-3 rounded-sm border bg-sunken p-3">
                <CardHead title="LIVE traffic"
                          note={`${traffic.points.length} sampel · tiap ${TRAFFIC_MS / 1000}s`} />
                <LiveChart points={traffic.points} />
                <div className="mt-2 flex flex-wrap items-center gap-3 border-t pt-2 font-mono text-xs">
                  <span className="flex items-center gap-1.5">
                    <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm bg-amber" />
                    Upload
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm bg-fiber" />
                    Download
                  </span>
                </div>
                <div className="mt-1.5 flex flex-col">
                  {/* out_octets = KELUAR dari ONU = upload pelanggan (schemas/onu_traffic.py). */}
                  <LiveRow dir="up" label="U Speed" color="text-amber"
                           speed={latest?.outMbps ?? null} max={liveMax?.out ?? null} />
                  <LiveRow dir="down" label="D Speed" color="text-fiber"
                           speed={latest?.inMbps ?? null} max={liveMax?.in ?? null} />
                </div>
                {traffic.error && <p className="mt-2 text-xs text-down">{traffic.error}</p>}
                <p className="mt-2 text-xs text-faint">
                  Pps dan Avg size butuh counter PAKET per-ONU yang belum ada di kontrak
                  backend (hanya octet yang dikirim), jadi keduanya tampil "—".
                </p>
              </div>
            )}
            {(diagView || diagRunning) && (
              <>
                <p className="mt-2 font-mono text-xs text-muted">
                  {DIAG_LABEL[diagRunView ?? diagView ?? "status"]}
                  {diagJobId !== null && ` · job #${diagJobId}`}
                  {diagStatus && ` · ${diagStatus}`}
                  {diagRunning && ` · ${diagSecs}s`}
                </p>
                <pre className="mt-1.5 max-h-[32rem] overflow-auto rounded-sm bg-sunken p-3 font-mono text-xs whitespace-pre">
                  {diagText()}
                </pre>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Trafik & sinyal: dua kartu sejajar, menumpuk di layar kecil */}
      <Section label="Traffic/Signal">
        <div className="flex flex-col gap-4 lg:flex-row">
          <ChartCard title="Traffic history" note="bits per second">
            {/* Histori trafik jam-jaman butuh penyimpanan sampel counter di DB yang BELUM ada
                di backend Nexfiber (tidak ada tabel/endpoint-nya). Kartu dibiarkan kosong
                dengan keterangan jujur — laju realtime ada di panel LIVE di atas. */}
            <p className="py-10 text-center text-muted">
              Belum ada histori trafik: backend belum menyimpan sampel counter per jam.
              Laju realtime bisa dilihat lewat tombol LIVE! di atas.
            </p>
          </ChartCard>
          <ChartCard title="Signal &amp; Status history" note={`dBm · rentang ${range}`}
            legend={
              <>
                <LegendRow color="bg-fiber" label="ONU Rx 1490nm" value={dbm(d.rx_power_dbm)} />
                <LegendRow color="bg-amber" label="OLT Rx 1310nm" value={dbm(d.olt_rx_power_dbm)} />
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
                  className={`border-b-2 px-2 py-1 text-xs ${range === value ? "border-fiber font-semibold text-fiber" : "border-transparent text-muted hover:text-ink"}`}>
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

      {/* Profil kecepatan */}
      <Section label="Profil Kecepatan">
        <div className="overflow-x-auto rounded-sm border">
          <table className="w-full min-w-[32rem] text-xs">
            <thead>
              <tr className="border-b bg-sunken font-mono text-xs uppercase text-muted">
                <th className={`${cell} w-[36%]`}>Download</th>
                <th className={`${cell} w-[36%]`}>Upload</th>
                <th className={cell}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className={`${cell} font-mono text-fiber`}>
                  {dash(d.download_profile_name)}
                  <span className="ml-2 text-muted">{dash(cleanProfileName(d.line_profile_id))}</span>
                </td>
                <td className={`${cell} font-mono text-fiber`}>
                  {dash(d.upload_profile_name)}
                  <span className="ml-2 text-muted">{dash(cleanProfileName(d.srv_profile_id))}</span>
                </td>
                <td className={cell}>
                  <Button size="sm" onClick={speedDialog}>Konfigurasi profil</Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      {/* Port Ethernet — jumlah port dari katalog ONU Types */}
      <Section label="Port Ethernet" note={specs ? specs.name : undefined}>
        {specs && specs.eth_ports > 0 ? (
          <>
            <div className="overflow-x-auto rounded-sm border">
              <table className="w-full min-w-[34rem] text-xs">
                <thead>
                  <tr className="border-b bg-sunken font-mono text-xs uppercase text-muted">
                    <th className={cell}>Port</th>
                    <th className={cell}>Admin state</th>
                    <th className={cell}>Mode</th>
                    <th className={cell}>Sumber DHCP</th>
                    <th className={cell}>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: specs.eth_ports }, (_, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className={`${cell} font-mono text-fiber`}>eth_0/{i + 1}</td>
                      <td className={`${cell} text-muted`}>—</td>
                      <td className={`${cell} font-mono`}>LAN</td>
                      <td className={`${cell} text-muted`}>—</td>
                      <td className={`${cell} text-faint`}>Segera</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1.5 text-xs text-muted">
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

      {/* WiFi */}
      <Section label="WiFi" note={specs ? `${specs.wifi_ssids} SSID` : undefined}>
        {specs && specs.wifi_ssids > 0 ? (
          <>
            <div className="overflow-x-auto rounded-sm border">
              <table className="w-full min-w-[34rem] text-xs">
                <thead>
                  <tr className="border-b bg-sunken font-mono text-xs uppercase text-muted">
                    <th className={cell}>Radio</th>
                    <th className={cell}>Admin state</th>
                    <th className={cell}>SSID</th>
                    <th className={cell}>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: specs.wifi_ssids }, (_, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className={`${cell} font-mono text-fiber`}>wifi_0/{i + 1}</td>
                      <td className={`${cell} text-muted`}>—</td>
                      <td className={`${cell} text-muted`}>—</td>
                      <td className={`${cell} text-faint`}>Segera</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1.5 text-xs text-muted">
              SSID dan password WiFi hanya bisa dibaca/diubah lewat TR-069: Phase 2.
            </p>
          </>
        ) : (
          <span className="text-muted">—</span>
        )}
      </Section>

      {/* 7. LAYANAN SEKUNDER (desain acuan §7): label rata kanan + nilai. Hanya nilai nyata
          dari katalog ONU Types; yang belum ada di backend ditandai "Segera". */}
      <Section label="Layanan">
        <div className="flex flex-col">
          <DRow label="Layanan VoIP" value={
            specs
              ? (specs.voip_ports > 0 ? `${specs.voip_ports} port` : "Tidak didukung tipe ONU")
              : <span className="text-faint">Tipe ONU belum terdaftar</span>
          } />
          <DRow label="IPTV" value={<span className="text-faint">Segera</span>} />
          <DRow label="CATV" value={
            specs?.catv
              ? <span className="text-up">Didukung</span>
              : specs
                ? "Tidak didukung tipe ONU"
                : <span className="text-faint">Tipe ONU belum terdaftar</span>
          } />
        </div>
      </Section>

      {/* 8. AKSI SIKLUS HIDUP (desain acuan §8). Perilaku & konfirmasi tidak diubah. */}
      <Section label="Aksi">
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" onClick={() => setConfirm("reboot")}>Reboot</Button>
          <Button size="sm" onClick={() => setConfirm("resync")}>Resync config</Button>
          <Button size="sm" onClick={infoDialog}>Ubah data pelanggan</Button>
          <Button size="sm" onClick={speedDialog}>Ubah speed</Button>
          <Button size="sm" onClick={vlanDialog}>Ubah VLAN</Button>
          {isManager && <Button size="sm" onClick={replaceDialog}>Replace ONU / ganti SN</Button>}
          <Button size="sm" onClick={() => setConfirm("state")}>
            {d.admin_state === "disabled" ? "Aktifkan ONU" : "Nonaktifkan ONU"}
          </Button>
          {isManager && (
            <Button size="sm" variant="danger" onClick={() => setConfirm("restore-factory")}>Restore factory</Button>
          )}
          {isManager && (
            <Button size="sm" variant="danger" onClick={() => setConfirm("delete")}>Hapus</Button>
          )}
        </div>
      </Section>

      <Panel title="Log aksi terakhir"
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
    </div>
  );
}
