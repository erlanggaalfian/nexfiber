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
  ArrowDown, ArrowLeft, ArrowSquareOut, ArrowUp, Eye, EyeSlash, Gear, Pencil, PlusCircle,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Drawer, Field, TableCard, cell, input } from "../components/crud";
import { OnuRearPanel } from "../components/onu/OnuRearPanel";
import {
  OnuActionModals, type ModalOnu, type OnuModalState,
} from "../components/onu/modals/OnuActionModals";
import {
  ErrorState, Panel, Skeleton, StatusBadge, fmtDateTime, nf, rxBucket, RX_BUCKETS,
} from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, ApiError, type OnuDetail as Detail, type OnuLog, type OnuType, type SignalPoint,
  type Splitter, type Zone,
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

/** Lebar kolom label = `dl-horizontal` acuan: label 160px + jarak 20px pada basis font
 *  15px. Basis Nexfiber 13px, jadi diskalakan dengan rasio yang sama -> 140px + 18px.
 *  Dipakai Section DAN DRow supaya SELURUH label halaman jatuh pada satu garis vertikal,
 *  sama seperti satu `<dl>` panjang di acuan.
 *
 *  Acuan menumpuk label di atas nilai ketika layar < 1000px (`@media (min-width:1000px)`
 *  pada `.dl-horizontal`); `lg` Tailwind (1024px) adalah ambang terdekat yang sudah ada,
 *  jadi tidak ada breakpoint baru yang ditambahkan. */
const LABEL_W = "lg:w-[140px]";
const ROW_GAP = "lg:gap-x-[18px]";
/** Tinggi baris acuan: line-height 1.4286 × ukuran font badan (13px) = 19px. */
const ROW_LH = "leading-[19px]";

/** Satu baris `dt`/`dd` acuan: label kolom kiri **rata kanan bold**, isi di kanan.
 *  TANPA kartu/rangka — acuan memakai `<dl>` datar di atas latar halaman, bukan panel. */
function Section(
  { label, note, children, className = "" }:
  { label: string; note?: string; children: React.ReactNode; className?: string },
) {
  return (
    <section className={`flex flex-col gap-0.5 lg:flex-row lg:items-start ${ROW_GAP} ${className}`}>
      <div className={`${LABEL_W} lg:shrink-0 lg:text-right`}>
        <h2 className={`font-semibold ${ROW_LH} text-ink`}>{label}</h2>
        {note && <p className="font-mono text-xs text-faint">{note}</p>}
      </div>
      <div className="min-w-0 grow">{children}</div>
    </section>
  );
}

/** Baris label/nilai di dalam blok dua kolom atas. Bentuknya sama dengan Section (label
 *  rata kanan bold pada kolom 140px, nilai di kanan) supaya kolom label halaman lurus;
 *  menumpuk jadi satu kolom di bawah `lg` seperti acuan. `onEdit` membuat seluruh baris
 *  bisa diklik — di acuan nilainya sendiri yang jadi tautan pembuka modal. */
function DRow(
  { label, value, onEdit }: { label: string; value: React.ReactNode; onEdit?: () => void },
) {
  const content = (
    <>
      <span className={`font-semibold ${ROW_LH} text-ink lg:text-right`}>{label}</span>
      <span className={`flex min-w-0 flex-wrap items-center gap-1.5 ${ROW_LH} text-muted`}>
        {onEdit && <Pencil size={12} aria-hidden className="text-faint" />}
        {value}
      </span>
    </>
  );
  const shape =
    `grid w-full lg:grid-cols-[140px_1fr] lg:items-baseline ${ROW_GAP}`;
  return onEdit ? (
    <button type="button" onClick={onEdit} className={`${shape} text-left hover:text-fiber`}>
      {content}
    </button>
  ) : (
    <div className={shape}>{content}</div>
  );
}

/** Tabel acuan = `table-bordered table-striped table-condensed`: rangka 1px di sekeliling,
 *  kepala kolom **bold** dengan garis bawah, baris ganjil berlatar, padding rapat
 *  (acuan 5px @15px -> 4px pada basis 13px Nexfiber). Perataan kolom TIDAK ikut di kelas
 *  dasar: `text-left`/`text-center` ditempel per kolom, karena dua utilitas perataan
 *  Tailwind punya kekhususan sama (urutan kelas di JSX tidak menentukan pemenang). */
const THEAD = "border-b px-1.5 py-1 align-bottom font-semibold";
const TCELL = "px-1.5 py-1 align-top";
/** Baris ganjil berlatar (`table-striped`); tanpa garis antar-baris seperti acuan. */
const TROW = "odd:bg-sunken";

/** Kolom `Action` tabel acuan: TAUTAN "Configure" berikon plus, bukan tombol penuh.
 *  `aria-label` tetap menyebut port supaya titik buka modal tetap bisa ditunjuk pembaca
 *  layar (dan tes layout modal) dengan nama yang jelas. */
function ConfigureLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
            className="inline-flex items-center gap-1 text-fiber hover:underline">
      <PlusCircle size={13} aria-hidden />
      Konfigurasi
    </button>
  );
}

/** Judul kecil di dalam kartu grafik / panel LIVE. Acuan tidak memberi judul pada kartu
 *  grafiknya (legendanya yang menamai seri); di sini judul dipertahankan karena kartu
 *  Nexfiber juga memuat pemilih rentang, jadi tanpa judul isinya ambigu. */
function CardHead({ title, note, action }: { title: string; note?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-2">
      <h3 className="font-semibold">{title}</h3>
      {note && <span className="text-xs text-faint">{note}</span>}
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

/** Satu kotak sinyal Rx = `.so-meter` acuan: kotak kecil (±140px, rangka 1px, radius 4px,
 *  latar permukaan) berisi nama arah di atas dan nilai besar di bawah. Lebar acuan 140px
 *  pada basis 15px; diskalakan ke basis 13px Nexfiber -> 122px. Bucket & warna tetap dari
 *  RX_BUCKETS bersama (tidak pernah dihitung ulang di halaman ini). */
function RxBox({ title, value }: { title: string; value: number | null }) {
  const b = rxBucket(value);
  const meta = b ? RX_BUCKETS[b] : null;
  return (
    <div className="flex w-[122px] shrink-0 flex-col rounded-sm border bg-surface px-2 pt-0.5 pb-1.5">
      <span className="truncate text-xs text-muted" title={title}>{title}</span>
      <span className="flex items-baseline gap-1">
        <span className={`font-mono text-base font-semibold ${meta ? meta.color.replace("bg-", "text-") : "text-muted"}`}>
          {value === null ? "LOS" : value.toFixed(2)}
        </span>
        {value !== null && <span className="font-mono text-xs text-faint">dBm</span>}
      </span>
      <span className={`text-xs ${meta ? meta.color.replace("bg-", "text-") : "text-muted"}`}>
        {meta ? meta.label : "LOS"}
      </span>
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

/** Kartu grafik acuan (`.graph-item`): kotak putih berangka 1px, radius kecil, dua kartu
 *  sejajar lebar sama. Latar permukaan (bukan sunken) seperti interior grafik acuan. */
function ChartCard(
  { title, note, children, legend }:
  { title: string; note?: string; children: React.ReactNode; legend?: React.ReactNode },
) {
  return (
    <div className="min-w-0 flex-1 rounded-sm border bg-surface p-2.5">
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
  /** Modal aksi ONU (kontrak `/api/onus/{id}/actions`), satu state untuk semua modal. */
  const [modal, setModal] = useState<OnuModalState | null>(null);
  const [editing, setEditing] = useState<null | "info">(null);
  const [info, setInfo] = useState<InfoForm | null>(null);
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
  const zones = useQuery({ queryKey: ["zones"], queryFn: () => api<Zone[]>("/api/zones") });
  const splitters = useQuery({
    queryKey: ["splitters", "all"], queryFn: () => api<Splitter[]>("/api/splitters"),
  });
  /** Jumlah port Ethernet/SSID/VoIP/CATV berasal dari katalog ONU Types (master data nyata),
   *  bukan angka hardcode per tipe. */
  const onuTypes = useQuery({
    queryKey: ["onu-types"], queryFn: () => api<OnuType[]>("/api/onu-types"),
  });
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
  /** Modal lokasi: satu titik buka untuk semua baris lokasi/identitas kiri atas. */
  const locationDialog = () => setModal({ kind: "location" });
  /** Data yang dipakai modal aksi: subset detail, tanpa menyalin seluruh tipe halaman. */

  const modalOnu: ModalOnu = {
    id: d.id, serial_number: d.serial_number, onu_type_id: d.onu_type_id,
    external_id: d.external_id, olt_id: d.olt_id, olt_name: d.olt_name,
    slot: d.slot, port: d.port, onu_mode: d.onu_mode, wan_mode: d.wan_mode,
    mgmt_ip_mode: d.mgmt_ip_mode, vlan_id: d.vlan_id, ip_address: d.ip_address,
    download_profile_name: d.download_profile_name, upload_profile_name: d.upload_profile_name,
    zone_id: d.zone_id, splitter_id: d.splitter_id, splitter_port: d.splitter_port,
    name: d.name, customer_name: d.customer_name, address: d.address, contact: d.contact,
    latitude: d.latitude, longitude: d.longitude,
    attached_vlans: (vlanList ?? [])
      .map((v) => v.vlan_id)
      .filter((v): v is number => typeof v === "number"),
  };

  return (
    <div className="space-y-3">
      {/* Breadcrumb halaman: kembali + identitas ONU dalam satu baris padat.
          Header aplikasi & navigasi tidak disentuh — ini milik halaman ini saja. */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Link to="/configured" className="inline-flex items-center gap-1 text-fiber hover:underline">
          <ArrowLeft size={14} aria-hidden /> Kembali ke Configured
        </Link>
        <span className="text-faint">/</span>
        <span className="font-mono text-muted">{onuIf}</span>
      </div>

      {/* Judul halaman acuan: satu `h2` besar di atas isi, bukan di dalam kartu.
          Acuan 32px pada basis 15px; diskalakan ke basis 13px Nexfiber -> 26px.
          Di bawah `lg` judul ini DISEMBUNYIKAN karena MobileTopBar aplikasi sudah
          menampilkan judul halaman — dua judul sama akan jadi heading ganda. */}
      <h1 className="hidden text-[26px] leading-8 font-normal text-ink lg:block">
        Detail ONU
      </h1>

      {note && (
        <p className="text-muted" role="status">{note}</p>
      )}

      {/* 1. BAGIAN ATAS acuan: DUA kolom 50/50 sejajar (`col-sm-6`), DATAR di atas latar
          halaman — acuan tidak memakai panel/kartu di sini, hanya dua `<dl>`. Kiri identitas,
          kanan ilustrasi panel belakang + Status + `Rx signal levels` + spesifikasi koneksi.
          Menumpuk jadi satu kolom di bawah `lg`, sama seperti acuan di bawah 1000px. */}
      <div className="grid gap-x-4 gap-y-3 lg:grid-cols-2">
          <div className="flex min-w-0 flex-col">
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
                    onEdit={isManager ? () => setModal({ kind: "replace-sn" }) : undefined} />
              <DRow label="ONU type" value={orNone(d.onu_type)}
                    onEdit={isManager ? () => setModal({ kind: "onu-type" }) : undefined} />
              <DRow label="Configuration Preset" value={orNone(d.preset_name)} />
              <DRow label="Zone" value={fromMasterOrDescription(d.zone_name, meta?.zone)} onEdit={locationDialog} />
              <DRow label="Splitter" onEdit={locationDialog} value={
                d.splitter_name
                  ? `${d.splitter_name}${d.splitter_port ? ` · port ${d.splitter_port}` : ""}`
                  : fromMasterOrDescription(null, meta?.splitter)
              } />
              {/* Sector belum ada kolomnya di master data Nexfiber: baris tetap ada supaya
                  urutan acuan utuh, nilainya `None` karena memang tidak ada datanya. */}
              <DRow label="Sector" value={NONE} onEdit={locationDialog} />
              <DRow label="Name" value={orNone(d.customer_name ?? d.name)} onEdit={locationDialog} />
              <DRow label="Address or comment"
                    value={fromMasterOrDescription(d.address, meta?.address ?? d.description)}
                    onEdit={locationDialog} />
              <DRow label="Contact" value={orNone(d.contact ?? d.phone)} onEdit={locationDialog} />
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
              <DRow label="ONU external ID" value={orNone(d.external_id)}
                    onEdit={() => setModal({ kind: "external-id" })} />
              <DRow label="Lokasi" value={d.latitude !== null && d.longitude !== null
                ? <a className="text-fiber hover:underline" target="_blank" rel="noreferrer"
                     href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=17/${d.latitude}/${d.longitude}`}>
                    {Number(d.latitude).toFixed(5)}, {Number(d.longitude).toFixed(5)}
                  </a>
                : "—"} onEdit={locationDialog} />
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-2">
            {/* (a) Ilustrasi panel belakang modem — hanya bila katalog ONU Types tahu
                jumlah port nyatanya; tidak digambar dari tebakan. Acuan memasang fotonya
                di puncak kolom kanan, dengan lebar terbatas dan terpusat. */}
            {specs && (specs.eth_ports > 0 || specs.voip_ports > 0) && (
              <div className="lg:mx-auto lg:w-[62%]">
                <OnuRearPanel ethPorts={specs.eth_ports} voipPorts={specs.voip_ports}
                              online={d.status === "online" && d.admin_state !== "disabled"} />
              </div>
            )}

            {/* (b) Baris status acuan: lencana status + jarak + muat ulang, sejajar pada
                kolom nilai `dl` supaya lurus dengan baris di bawahnya. */}
            <div className={`grid lg:grid-cols-[140px_1fr] lg:items-baseline ${ROW_GAP}`}>
              <span className={`font-semibold ${ROW_LH} text-ink lg:text-right`}>Status</span>
              <span className="flex flex-wrap items-center gap-2">
                <StatusBadge status={statusKey} reason={d.last_down_reason} withLabel />
                <span className="font-mono text-xs text-muted">{fmtDistance(d.distance_m)}</span>
                <Button size="sm" variant="quiet" onClick={() => onu.refetch()} disabled={onu.isFetching}>
                  {onu.isFetching ? "Memuat ..." : "Muat ulang"}
                </Button>
                {live && (
                  <span className="font-mono text-xs text-fiber">auto-refresh {LIVE_MS / 1000}s</span>
                )}
              </span>
            </div>

            {/* (c) `Rx signal levels` acuan = DUA kotak kecil berdampingan (`.so-meter`,
                masing-masing ±140px, rangka 1px, radius 4px) langsung di bawah lencana
                status — bukan kartu berjudul. Judul/ambangnya jadi baris label `dl`. */}
            <div className={`grid lg:grid-cols-[140px_1fr] lg:items-baseline ${ROW_GAP}`}>
              <span className={`font-semibold ${ROW_LH} text-ink lg:text-right`}>Rx signal levels</span>
              <div className="min-w-0">
                <div className="flex flex-wrap gap-1.5">
                  <RxBox title="ONU Rx 1490nm" value={d.rx_power_dbm} />
                  <RxBox title="OLT Rx 1310nm" value={d.olt_rx_power_dbm} />
                </div>
                <p className="mt-0.5 text-xs text-faint">Normal −8,0 s/d −27,0 dBm</p>
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
              } onEdit={isManager ? () => setModal({ kind: "mgmt-ip" }) : undefined} />
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
              } onEdit={() => setModal({ kind: "attached-vlans" })} />
              {/* "Routing - WAN vlan: N" seperti acuan; nomor VLAN hanya ditempel bila ada. */}
              <DRow label="ONU mode" value={
                d.onu_mode === null || d.onu_mode === ""
                  ? "—"
                  : `${d.onu_mode}${wanVlan === null ? "" : ` - WAN vlan: ${wanVlan}`}`
              } onEdit={() => setModal({ kind: "onu-mode" })} />
              {/* WAN setup mode: label mode dari WAN_MODE_LABEL (huruf kapital di teks, bukan
                  CSS uppercase) + IP sebagai tautan tab baru. `webpage` tidak punya IP WAN. */}
              <DRow label="WAN setup mode" value={
                wanMode === null ? "—" : (
                  <>
                    <span>{wanMode}</span>
                    {wanHasIp && d.ip_address && <IpLink ip={d.ip_address} />}
                  </>
                )
              } onEdit={() => setModal({ kind: "onu-mode" })} />
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

      {/* 2. BARIS TOMBOL `Status` acuan: label `dl` di kiri, deretan tombol terisi penuh di
          kanan (acuan: biru untuk tiga diagnostik, abu untuk TR-069 mati, hijau untuk LIVE!).
          DATAR tanpa kartu, sama seperti acuan. Logika/handler diagnostik tidak diubah —
          tetap lewat job CLI backend, dan running-config tetap manager-only. */}
      <Section label="Status">
          <div className="min-w-0 grow">
            <div className="flex flex-wrap items-center gap-1.5">
              <Button size="sm" variant="fiber" onClick={() => runDiag("status")} disabled={diagRunning}>
                {DIAG_LABEL.status}{diagRunning && diagRunView === "status" ? " ..." : ""}
              </Button>
              {/* Running-config utuh memuat nilai konfigurasi sensitif: tombolnya hanya dirender
                  untuk admin/superadmin, dan backend tetap menolak role lain (403). */}
              {isManager && (
                <Button size="sm" variant="fiber" onClick={() => runDiag("running")} disabled={diagRunning}>
                  {DIAG_LABEL.running}{diagRunning && diagRunView === "running" ? " ..." : ""}
                </Button>
              )}
              <Button size="sm" variant="fiber" onClick={() => runDiag("software")} disabled={diagRunning}>
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
      </Section>

      {/* 3. `Traffic/Signal` acuan: dua kartu grafik berdampingan 50/50 (`.graphs-container`
          flex), menumpuk penuh di bawah 768px seperti aturan `@media` acuan. */}
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

      {/* 4. `Speed profiles` acuan: tabel berangka dengan kolom Download | Upload | Action,
          kolom Action berisi tautan "Configure" (bukan tombol penuh). */}
      <Section label="Profil Kecepatan">
        <div className="overflow-x-auto border">
          <table className="w-full min-w-[32rem] border-collapse">
            <thead>
              <tr>
                <th className={`${THEAD} w-[33%] text-left`}>Download</th>
                <th className={`${THEAD} w-[26%] text-left`}>Upload</th>
                <th className={`${THEAD} text-left`}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              <tr className={TROW}>
                <td className={`${TCELL} font-mono text-fiber`}>
                  {dash(d.download_profile_name)}
                  <span className="ml-2 text-muted">{dash(cleanProfileName(d.line_profile_id))}</span>
                </td>
                <td className={`${TCELL} font-mono text-fiber`}>
                  {dash(d.upload_profile_name)}
                  <span className="ml-2 text-muted">{dash(cleanProfileName(d.srv_profile_id))}</span>
                </td>
                <td className={TCELL}>
                  <ConfigureLink label="Konfigurasi profil kecepatan"
                                 onClick={() => setModal({ kind: "speed-profile" })} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      {/* 5. `Ethernet ports` acuan: Port | Admin state | Mode | DHCP | Action, kolom Action
          rata tengah berisi tautan "Configure". Jumlah port dari katalog ONU Types. */}
      <Section label="Port Ethernet" note={specs ? specs.name : undefined}>
        {specs && specs.eth_ports > 0 ? (
          <>
            <div className="overflow-x-auto border">
              <table className="w-full min-w-[34rem] border-collapse">
                <thead>
                  <tr>
                    <th className={`${THEAD} w-[14%] text-left`}>Port</th>
                    <th className={`${THEAD} w-[14%] text-left`}>Admin state</th>
                    <th className={`${THEAD} text-left`}>Mode</th>
                    <th className={`${THEAD} w-[14%] text-left`}>Sumber DHCP</th>
                    <th className={`${THEAD} w-[16%] text-center`}>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: specs.eth_ports }, (_, i) => (
                    <tr key={i} className={TROW}>
                      <td className={`${TCELL} font-mono text-fiber`}>eth_0/{i + 1}</td>
                      <td className={`${TCELL} text-muted`}>—</td>
                      <td className={`${TCELL} font-mono`}>LAN</td>
                      <td className={`${TCELL} text-muted`}>—</td>
                      <td className={`${TCELL} text-center`}>
                        <ConfigureLink label={`Konfigurasi eth_0/${i + 1}`}
                                       onClick={() => setModal({ kind: "eth-port", port: i + 1 })} />
                      </td>
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

      {/* 6. `WiFi` acuan: tabel sejenis dengan kolom SSID, Action rata tengah. */}
      <Section label="WiFi" note={specs ? `${specs.wifi_ssids} SSID` : undefined}>
        {specs && specs.wifi_ssids > 0 ? (
          <>
            <div className="overflow-x-auto border">
              <table className="w-full min-w-[34rem] border-collapse">
                <thead>
                  <tr>
                    <th className={`${THEAD} w-[12%] text-left`}>Radio</th>
                    <th className={`${THEAD} w-[14%] text-left`}>Admin state</th>
                    <th className={`${THEAD} text-left`}>SSID</th>
                    <th className={`${THEAD} w-[16%] text-center`}>Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: specs.wifi_ssids }, (_, i) => (
                    <tr key={i} className={TROW}>
                      <td className={`${TCELL} font-mono text-fiber`}>wifi_0/{i + 1}</td>
                      <td className={`${TCELL} text-muted`}>—</td>
                      <td className={`${TCELL} text-muted`}>—</td>
                      <td className={`${TCELL} text-center`}>
                        <ConfigureLink label={`Konfigurasi wifi_0/${i + 1}`}
                                       onClick={() => setModal({ kind: "wifi-port", port: i + 1 })} />
                      </td>
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

      {/* 7. LAYANAN SEKUNDER acuan (`VoIP`, `IPTV`, `CATV` di bawah tabel WiFi): baris
          label/nilai biasa. Hanya nilai nyata dari katalog ONU Types; yang backend-nya
          belum ada ditandai "Segera", tidak dikarang. */}
      <Section label="Layanan">
        <div className="flex flex-col">
          <DRow label="Layanan VoIP" value={
            specs
              ? (specs.voip_ports > 0 ? `${specs.voip_ports} port` : "Tidak didukung tipe ONU")
              : <span className="text-faint">Tipe ONU belum terdaftar</span>
          } onEdit={specs && specs.voip_ports > 0
            ? () => setModal({ kind: "voip-enable", port: 1 })
            : undefined} />
          <DRow label="IPTV" value={<span className="text-faint">Segera</span>}
                onEdit={() => setModal({ kind: "iptv" })} />
          <DRow label="CATV" value={
            specs?.catv
              ? <span className="text-up">Didukung</span>
              : specs
                ? "Tidak didukung tipe ONU"
                : <span className="text-faint">Tipe ONU belum terdaftar</span>
          } />
        </div>
      </Section>

      {/* 8. BARIS AKSI SIKLUS HIDUP acuan: deretan tombol terisi penuh BERWARNA MENURUT
          PERAN — kuning/amber untuk aksi mengganggu layanan (reboot, resync, restore,
          nonaktifkan) dan merah penuh untuk Hapus; sisanya netral. Tiap tombol tetap
          membuka modal konfirmasi (kontrak `/api/onus/{id}/actions/{kind}`), tidak ada
          aksi satu klik, dan tombol merusak tetap manager-only. */}
      <Section label="Aksi">
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="primary" onClick={() => setModal({ kind: "reboot" })}>Reboot</Button>
          <Button size="sm" variant="primary" onClick={() => setModal({ kind: "resync-config" })}>Resync config</Button>
          <Button size="sm" onClick={infoDialog}>Ubah data pelanggan</Button>
          <Button size="sm" onClick={locationDialog}>Ubah lokasi</Button>
          <Button size="sm" onClick={() => setModal({ kind: "speed-profile" })}>Ubah speed</Button>
          <Button size="sm" onClick={() => setModal({ kind: "attached-vlans" })}>Ubah VLAN</Button>
          <Button size="sm" onClick={() => setModal({ kind: "move" })}>Move ONU</Button>
          {isManager && (
            <Button size="sm" onClick={() => setModal({ kind: "replace-sn" })}>Replace ONU / ganti SN</Button>
          )}
          <Button size="sm" variant="primary"
                  onClick={() => setModal({ kind: d.admin_state === "disabled" ? "enable" : "disable" })}>
            {d.admin_state === "disabled" ? "Aktifkan ONU" : "Nonaktifkan ONU"}
          </Button>
          {isManager && (
            <Button size="sm" variant="primary" onClick={() => setModal({ kind: "restore-factory" })}>
              Restore factory
            </Button>
          )}
          {isManager && (
            <Button size="sm" variant="dangerSolid" onClick={() => setModal({ kind: "delete" })}>Hapus</Button>
          )}
        </div>
      </Section>

      {/* 9. BAGIAN BAWAH acuan (catatan/tiket): dipisah garis dari baris aksi, lalu isinya.
          Di Nexfiber isinya log aksi ONU — tetap memakai Panel/TableCard bersama. */}
      <div className="border-t pt-3">
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
      </div>

      {/* Semua modal aksi ONU dirender satu kali di sini; isinya dipilih oleh `modal`. */}
      <OnuActionModals state={modal} onu={modalOnu} onClose={() => setModal(null)}
                       onDone={(kind, r) => setNote(r?.detail ?? `Aksi ${kind} terkirim.`)} />

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
