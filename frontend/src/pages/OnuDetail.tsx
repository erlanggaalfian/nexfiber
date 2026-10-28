/** Detail ONU — PRD 3.4.6. Satu halaman (tidak ada halaman detail kedua).
 *
 *  Tata letak mengikuti mock pemilik `onu-detail-mock.html` (grid label rata-kanan bold /
 *  nilai): bagian atas BLOK `Status Perangkat` full-width (kartu `Level Sinyal Rx` dua
 *  kolom + kartu telemetri 6 baris) → dua kolom `Identitas` | `Jaringan & Layanan`
 *  (`lg:col-span-6`) → section `Diagnostik` gaya mock (judul + sub di kolom 140px, tombol
 *  operasi kiri-kanan judul, + panel LIVE realtime saat LIVE aktif) → section
 *  `Trafik & Histori Sinyal` (dua kartu grafik + toggle rentang) → tabel Profil
 *  Kecepatan → Port Ethernet → WiFi →
 *  Layanan (VoIP/IPTV/CATV) → Aksi siklus hidup → Log aksi.
 *
 *  Label baris mengikuti TABEL RENAME pemilik (Bahasa Indonesia: `Tipe ONU`,
 *  `Preset konfigurasi`, `VLAN terpasang`, `Mode ONU`, `Setup WAN`, ...); akronim teknis
 *  (OLT/ONU/SN/PPPoE/TR069/VLAN/WiFi/IP) tetap. Kredensial PPPoE DUA baris terpisah
 *  (`Username PPPoE` / `Password PPPoE`); kata sandi mask default `**********` dengan
 *  satu tombol mata.
 *
 *  Penyesuaian pemilik terhadap desain acuan (sengaja TIDAK diikuti):
 *  - Shelf/Board, Slot, Port, GPON channel, Tx ONU, suhu, tegangan, MAC TIDAK ditampilkan;
 *  - Rx null = "LOS", tidak pernah digambar sebagai angka (mis. −30) yang tidak dibaca;
 *  - kolom identitas yang memang kosong ditulis `None` miring seperti acuan; baris
 *    spesifikasi koneksi memakai `Inactive`/"—" sesuai aturan pemilik;
 *  - baris kredensial PPPoE hanya muncul saat `wan_mode === "pppoe"`; username tampil apa
 *    adanya dari backend dan kata sandi selalu mask default (buka lewat tombol mata; tanpa
 *    nilai dari backend: `Hanya untuk manager`);
 *  - `Pps`/`Avg size` di panel LIVE = "—": kontrak counter backend hanya octet, tidak ada
 *    counter paket. Tidak ada OID/CLI baru yang ditambahkan ke perangkat untuk ini;
 *  - kartu `Traffic history` menggambar sampel bps yang BENAR-BENAR tersimpan di DB
 *    (`onu_traffic_history`, diisi job worker `sample_onu_traffic` tiap 5 menit lewat
 *    SNMP); titik tanpa laju (sampel pertama/wrap/sampler berhenti) memutus garis, tidak
 *    pernah digambar nol, dan pesan kosong hanya muncul kalau sampelnya memang belum ada;
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
  ArrowDown, ArrowSquareOut, ArrowUp, CaretDown, Eye, EyeSlash, Gear, Pencil,
  PlusCircle,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { Popover } from "radix-ui";
import { TitleIcon } from "../components/onu/icons";
import { OnuRearPanel } from "../components/onu/OnuRearPanel";
import {
  OnuActionModals, type ModalOnu, type OnuModalState,
} from "../components/onu/modals/OnuActionModals";
import {
  ChartSkeleton, ErrorState, Skeleton, StatusBadge, fmtDateTime, nf, rxBucket, RX_BUCKETS,
} from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, ApiError, qs, type OnuDetail as Detail, type OnuLog, type OnuType, type SignalPoint,
  type TrafficHistoryPoint, type Vlan,
} from "../lib/api";
import { Field, JobTrace } from "../components/crud";
import { ModalShell } from "../components/onu/modals/ModalShell";
import { useAuth } from "../lib/auth";
import { DONE, useJob } from "../lib/jobs";
import { cleanProfileName } from "../lib/profileName";
import { deltaMbps, type TrafficPoint, type TrafficSample } from "../lib/traffic";

type RangeKey = "24h" | "7d" | "30d";
const RANGES = [["24h", "24 jam"], ["7d", "7 hari"], ["30d", "30 hari"]] as const;
const RANGE_TITLE: Record<RangeKey, string> = {
  "24h": "24 jam terakhir", "7d": "7 hari terakhir", "30d": "30 hari terakhir",
};
/** Interval auto-refresh detail ONU dari database saat LIVE aktif. */
const LIVE_MS = 15_000;
/** Interval sampel counter trafik saat LIVE aktif (proposal §5: 5 detik, bukan 3). */
const TRAFFIC_MS = 5_000;
/** LIVE mati sendiri setelah ini supaya tab yang ditinggal terbuka tidak memolling OLT terus. */
const LIVE_MAX_MS = 10 * 60_000;
/** Titik grafik yang disimpan (10 menit @5s = 120). */
const TRAFFIC_KEEP = 120;
/** Entri log yang ditampilkan di pop up aksi (histori penuh tetap di halaman Logs). */
const LOG_POPUP_ROWS = 5;

const dash = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));
const mbps = (v: number) => `${v < 10 ? v.toFixed(2) : v.toFixed(1)} Mbps`;
/** Nilai legenda statistik memakai desimal koma seperti gaya pemilik (`5,38 Mbps · 0,28`). */
const comma = (v: number, digits: number) => v.toFixed(digits).replace(".", ",");
const mbpsId = (v: number) => `${comma(v, v < 10 ? 2 : 1)} Mbps`;

/** Nilai kosong baris spesifikasi koneksi: konvensi `dash()` ("—") yang diredupkan. */
const DASH = <span className="text-faint">—</span>;
const orDash = (v: unknown) =>
  v === null || v === undefined || v === "" ? DASH : <>{String(v)}</>;

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

/** Mode ONU: huruf kapital ada di teks (`Routing`/`Bridging`), bukan CSS. Nilai di luar
 *  daftar tampil apa adanya. Backend mengirim nilai EFEKTIF (CLI, atau default `routing`
 *  bila tidak terbaca CLI) plus `onu_mode_source`, jadi halaman tidak menebak sendiri. */
const ONU_MODE_LABEL: Record<string, string> = { routing: "Routing", bridging: "Bridging" };
const onuLabel = (mode: string | null) =>
  mode === null || mode === "" ? null : (ONU_MODE_LABEL[mode.toLowerCase()] ?? mode);

/** Mode IP manajemen pada acuan: `Static` / `DHCP`. Nilai lain tampil apa adanya. */
const MGMT_MODE_LABEL: Record<string, string> = {
  static: "Static", dhcp: "DHCP", inactive: "Inactive",
};

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

/** Satu baris `dt`/`dd` acuan: label kolom kiri **tebal redup rata kiri (mock)**, isi di kanan.
 *  TANPA kartu/rangka — acuan memakai `<dl>` datar di atas latar halaman, bukan panel. */
function Section(
  { label, note, action, card = false, children, className = "", id }:
  { label: string; note?: string; action?: React.ReactNode; card?: boolean; children: React.ReactNode; className?: string; id?: string },
) {
  // Varian kartu (mock Detail ONU pemilik): judul fiber + catatan/aksi di kepala kartu,
  // isi padat di dalam bingkai permukaan. Dipakai blok Profil Kecepatan ke bawah.
  if (card) {
    return (
      <section id={id} className={`entrance rounded-md border bg-surface p-4 transition-colors hover:border-line-strong ${className}`}>
        <div className="mb-3 flex items-center justify-between gap-2 border-b border-line pb-2.5">
          <h2 className="flex items-center gap-2 text-base font-bold text-fiber">
            <TitleIcon title={label} />{label}
          </h2>
          {action ?? (note ? <span className="font-mono text-xs text-muted">{note}</span> : null)}
        </div>
        {children}
      </section>
    );
  }
  return (
    <section id={id} className={`entrance flex flex-col gap-1 lg:flex-row lg:items-start ${ROW_GAP} ${className}`}>
      <div className={`${LABEL_W} lg:shrink-0 lg:text-right`}>
        {/* Judul fiber jadi jangkar pindai tanpa menambah garis atau panel. */}
        <h2 className="flex items-center gap-2 text-base font-bold text-fiber">
          <TitleIcon title={label} />{label}
        </h2>
        {note && <p className="font-mono text-xs text-faint">{note}</p>}
      </div>
      <div className="min-w-0 grow">{children}</div>
    </section>
  );
}

/** Blok berjudul bagian atas (Status Perangkat / Identitas / Jaringan & Layanan): kartu
 *  permukaan dengan judul fiber gaya Section, isinya baris label/nilai yang padat.
 *  `action` = isi kanan judul (badge status + tombol `Muat ulang` pada blok Status). */
function Block(
  { title, action, children, className = "" }:
  { title: string; action?: React.ReactNode; children: React.ReactNode; className?: string },
) {
  return (
    <section className={`entrance rounded-md border bg-surface p-4 transition-colors hover:border-line-strong ${className}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
        <h2 className="flex items-center gap-2 text-base font-bold text-fiber">
          <TitleIcon title={title} />{title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Baris label/nilai di dalam blok. Bentuknya sama dengan Section (label tebal redup rata
 *  kiri pada kolom 140px, nilai di kanan) supaya kolom label halaman lurus; menumpuk jadi satu
 *  kolom di bawah `lg` seperti acuan. Ikon pensil = satu-satunya titik buka modal: selalu
 *  tampil di mobile (target sentuh 44x44), di desktop baru muncul saat baris di-hover /
 *  difokus (tetap bisa di-tab, `focus-visible`). `aria-label`-nya label baris itu sendiri. */
function DRow(
  { label, value, dot, onEdit }:
  { label: string; value: React.ReactNode; dot?: "up" | "warn" | "down" | "idle"; onEdit?: () => void },
) {
  const shape = `group relative grid w-full lg:grid-cols-[140px_1fr] lg:items-baseline ${ROW_GAP} ${onEdit ? "min-h-[44px] lg:min-h-0" : ""}`;
  return (
    <div className={shape}>
      <span className={`font-semibold ${ROW_LH} text-muted`}>{label}</span>
      <span className={`flex min-w-0 flex-wrap items-center gap-1.5 pr-11 ${ROW_LH} text-muted`}>
        {dot && <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[dot]}`} />}
        {value}
      </span>
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          aria-label={label}
          className="absolute right-0 top-0 bottom-0 flex w-11 items-center justify-center rounded-sm text-faint transition-opacity duration-150 ease-out hover:bg-sunken hover:text-fiber focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-fiber lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100"
        >
          <Pencil size={12} aria-hidden />
        </button>
      )}
    </div>
  );
}

/** Titik status kecil baris telemetri (mock): `up` = normal, `down` = bermasalah,
 *  `warn` = nilai yang belum dikenal aplikasi, null = kosong (tanpa titik). Hanya peta
 *  tampilan — nilai asli tetap dikirim backend apa adanya. */
const stateTone = (v: unknown): "up" | "warn" | "down" | null => {
  const s = (v === null || v === undefined ? "" : String(v)).trim().toLowerCase();
  if (s === "") return null;
  if (["match", "matched", "configured", "success", "online", "ok", "up"].includes(s)) return "up";
  if (["mismatch", "unconfigured", "failed", "error", "offline", "los", "down"].includes(s)) return "down";
  return "warn";
};
/** Warna titik status statis (Tailwind perlu literal kelas, bukan string yang disusun saat
 *  jalan). `idle` = abu netral untuk status pasif (mis. TR069 Inactive). */
const TONE_DOT = { up: "bg-up", warn: "bg-warn", down: "bg-down", idle: "bg-idle" } as const;

/** Baris telemetri blok `Status Perangkat`: grid label 140px yang sama dengan DRow, plus
 *  titik status kecil di depan nilai berstatus. Bukan DRow: baris ini tanpa titik edit
 *  dan labelnya bukan baris identitas/spesifikasi. */
function TRow(
  { label, dot, children }:
  { label: string; dot?: "up" | "warn" | "down" | null; children: React.ReactNode },
) {
  return (
    <div className={`grid w-full py-1 lg:grid-cols-[140px_1fr] lg:items-baseline ${ROW_GAP} ${ROW_LH}`}>
      <span className={`font-semibold ${ROW_LH} text-muted`}>{label}</span>
      <span className="flex min-w-0 flex-wrap items-center gap-1.5 text-muted">
        {dot && <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE_DOT[dot]}`} />}
        {children}
      </span>
    </div>
  );
}

/** Tabel acuan = `table-bordered table-striped table-condensed` memakai kelas literal per
 *  tabel (kontrak "satu markup dua ukuran"), bukan konstanta yang disusun. */

/** Kolom `Action` tabel acuan: TAUTAN "Configure" berikon plus, bukan tombol penuh.
 *  `aria-label` tetap menyebut port supaya titik buka modal tetap bisa ditunjuk pembaca
 *  layar (dan tes layout modal) dengan nama yang jelas. */
/** Pop up "Log aksi terakhir": dibuka dari bawah blok aksi, isinya entri log terakhir ONU ini.
 *  Tiap baris = deskripsi aksi (tautan ke `/logs?q=<serial>`) + waktu + hasil. Teks deskripsi
 *  diturunkan dari `action` yang dikirim backend, bukan daftar karangan. */
const LOG_DESC: Record<string, string> = {
  "onu.update_info": "Update location details",
  "onu.refresh_detail": "Refresh ONU details",
  "onu.authorize": "Authorize ONU",
  "onu.reboot": "Reboot ONU",
  "onu.delete": "Delete ONU",
  "onu.restore_factory": "Restore ONU to factory defaults",
};
/** `onu.action.eth-port` -> "Eth port", `onu.read_status` -> "Read status". */
const logDesc = (action: string) => {
  if (LOG_DESC[action]) return LOG_DESC[action];
  const tail = action.replace(/^onu\.(action\.)?/, "").replace(/[-_]/g, " ");
  return tail === "" ? action : tail.charAt(0).toUpperCase() + tail.slice(1);
};

function LastLogPopover(
  { query, serial }: { query: UseQueryResult<OnuLog[]>; serial: string },
) {
  const rows = (query.data ?? []).slice(0, LOG_POPUP_ROWS);
  const href = `/logs?q=${encodeURIComponent(serial)}`;
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button type="button"
                className="inline-flex items-center gap-1.5 rounded border border-line bg-sunken/40 px-2.5 py-1 text-xs font-medium text-fiber transition-colors hover:bg-sunken min-h-11 sm:min-h-0">
          Log aksi terakhir
          <CaretDown size={12} aria-hidden />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        {/* Satu gaya popover dengan menu lain (Layout overlay: radius-md,
            shadow-overlay, item 36px/48px sentuh) — bukan panel kustom. */}
        <Popover.Content align="start" sideOffset={4} collisionPadding={8}
          className="z-50 w-[min(26rem,calc(100vw-2rem))] rounded-md border bg-surface p-1 shadow-overlay data-[state=open]:animate-[fade-in_150ms_ease-out]">
          {query.isPending && <p className="p-2 text-muted">Memuat log ...</p>}
          {query.isError && <p className="p-2 text-down">{query.error?.message}</p>}
          {!query.isPending && !query.isError && rows.length === 0 && (
            <p className="p-2 text-muted">Belum ada log untuk ONU ini.</p>
          )}
          <ul className="min-w-0">
            {rows.map((l) => (
              <li key={l.id} className="flex min-h-9 flex-wrap items-center gap-x-1.5 border-b px-2 py-1 last:border-0 max-md:min-h-12">
                <Link className="text-fiber hover:underline" to={href}>{logDesc(l.action)}</Link>
                <span className="text-xs text-muted">{fmtDateTime(l.created_at)}</span>
                {!l.success && <span className="text-xs text-down">gagal</span>}
              </li>
            ))}
          </ul>
          {rows.length > 0 && (
            <Link className="inline-block px-2 py-1 text-xs text-fiber hover:underline" to={href}>
              Buka di Logs
            </Link>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function ConfigureLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
            className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1 px-2 text-fiber hover:underline md:min-h-0 md:min-w-0 md:px-0">
      <PlusCircle size={13} aria-hidden />
      Atur
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

/** Kata sandi PPPoE: selalu MASK default `**********` — nilai asli tidak pernah tampil
 *  begitu halaman termuat; tombol mata membuka/menutupnya (nilai MEMANG dari backend
 *  `d.pppoe_password`, manager-only menurut RBAC backend). Tanpa nilai kata sandi tetap
 *  keterangan jujur `Hanya untuk manager`, tanpa tombol mata — tidak diganti contoh. */
function PppoePassword({ password }: { password: string | null }) {
  const [shown, setShown] = useState(false);
  if (!password) return <span className="text-faint">Hanya untuk manager</span>;
  return (
    <>
      <span className={`font-mono text-ink ${shown ? "" : "tracking-wider"}`}>
        {shown ? password : "**********"}
      </span>
      <button type="button" onClick={() => setShown(!shown)}
              aria-pressed={shown}
              aria-label={shown ? "Sembunyikan kata sandi PPPoE" : "Tampilkan kata sandi PPPoE"}
              className="flex min-h-11 min-w-11 items-center justify-center rounded-sm text-fiber hover:bg-sunken md:min-h-0 md:min-w-0"
              title={shown ? "Sembunyikan" : "Tampilkan"}>
        {shown ? <EyeSlash size={14} aria-hidden /> : <Eye size={14} aria-hidden />}
      </button>
    </>
  );
}

/** Tautan ke alamat IP perangkat: tab baru + ikon keluar seperti acuan. Dipakai untuk
 *  IP WAN dan IP manajemen; `http://` karena yang dituju halaman web ONU di LAN.
 *  `title` = tooltip judul tautan (mock). Chip seragam `bg-sunken border border-line
 *  text-fiber` untuk kedua baris (mock). */
function IpLink({ ip, title }: { ip: string; title?: string }) {
  return (
    <a className="inline-flex items-center gap-1 rounded border border-line bg-sunken px-1.5 py-0.5 font-mono text-[11px] font-semibold text-fiber hover:bg-surface"
       href={`http://${ip}`}
       target="_blank" rel="noopener noreferrer" title={title}>
      {ip}
      <ArrowSquareOut size={12} aria-hidden />
    </a>
  );
}

function fmtDistance(m: number | null) {
  if (m === null) return "—";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${nf.format(m)} m`;
}

/** Ringkasan histori satu garis Rx (ONU atau OLT): terendah / rata-rata / tertinggi
 *  + jumlah bacaan tidak online. Dipanggil sekali per garis, field jadi parameter. */
function rxStats(points: SignalPoint[], field: "rx_power_dbm" | "olt_rx_power_dbm") {
  const values = points.map((p) => p[field]).filter((v): v is number => v !== null);
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

/** Satu kartu sinyal Rx (mock `.so-meter` versi baru): nama arah + badge bucket di atas,
 *  nilai mono besar di bawah. Lebar mengikuti grid dua kolom induknya. Bucket & warna
 *  tetap dari RX_BUCKETS bersama (tidak pernah dihitung ulang di halaman ini). */
function RxBox({ title, value }: { title: string; value: number | null }) {
  const b = rxBucket(value);
  const meta = b ? RX_BUCKETS[b] : null;
  // Nilai kritis ditonjolkan merah kuat supaya terbaca sekilas.
  const strong = b === "critical";
  const tone = b === "good" ? "text-up" : b ? "text-warn" : "text-muted";
  return (
    <div className="min-w-0 rounded-md border bg-surface p-3">
      {/* flex-wrap: di 390px badge bisa turun baris — label tak pernah dipotong (mock). */}
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-1.5">
        <span className="text-xs font-medium leading-tight text-muted" title={title}>{title}</span>
        <span className={`shrink-0 rounded-sm border border-line bg-sunken px-1.5 py-0.5 text-[10px] font-semibold ${strong ? "text-down" : tone}`}>
          {meta ? meta.label : "LOS"}
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        {/* text-metric, bukan text-2xl: text-2xl tidak ada di tema (index.css mereset
            --text-*: initial dan hanya mendefinisikan xs/sm/base/lg/xl/metric), jadi
            nilai lama dirender 13px, bukan ~24px. dBm 1 desimal di semua permukaan. */}
        <span className={`font-mono text-metric font-bold ${strong ? "text-down" : tone}`}>
          {value === null ? "LOS" : value.toFixed(1)}
        </span>
        {value !== null && <span className="font-mono text-xs text-faint">dBm</span>}
      </div>
      {/* Segmen signal bar yang sama dengan tabel (48x4), di bawah angka, badge kata
          dipertahankan. Hanya pola segmennya yang dipakai — bukan komponen SignalBar
          utuh, karena komponen itu ikut merender angka dan akan menduplikasi nilai
          RxBox ini. */}
      <div className="mt-1.5 flex w-12 gap-px" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={`h-1 flex-1 transition-colors duration-300 ease-out motion-reduce:transition-none ${i < (meta ? meta.segments : 0) ? (meta ? meta.color : "") : "bg-sunken"}`} />
        ))}
      </div>
    </div>
  );
}

/** Grafik Rx: sparkline SVG dari histori, ambang sebagai garis putus.
 *  ponytail: tanpa library chart — satu polyline sudah menjawab "trennya turun atau tidak".
 *  skipped: tooltip per titik & zoom, tambah kalau operator memang memintanya. */
function RxChart({ points }: { points: SignalPoint[] }) {
  const SERIES = [
    { field: "rx_power_dbm", label: "ONU Rx", line: "text-fiber", dot: "fill-fiber" },
    { field: "olt_rx_power_dbm", label: "OLT Rx", line: "text-amber", dot: "fill-amber" },
  ] as const;
  // Satu sampel BUKAN "belum cukup data": sampler optik jalan tiap 15 menit, jadi sesaat
  // setelah worker restart memang baru ada 1 titik. Polyline 1 titik tidak tergambar, maka
  // titik tunggal digambar sebagai lingkaran. Pesan kosong hanya untuk 0 bacaan Rx total.
  const series = SERIES.map((s) => ({
    ...s,
    values: points.map((p) => p[s.field]).filter((v): v is number => v !== null),
  }));
  const all = series.flatMap((s) => s.values);
  if (all.length === 0) {
    return (
      <>
        <p className="py-6 text-center text-muted">
          Belum ada sampel Rx. Tunggu poll berikutnya.
        </p>
        <StatusStrip points={points} />
      </>
    );
  }
  const dataMin = Math.min(...all);
  const dataMax = Math.max(...all);
  const min = Math.min(dataMin - 1.5, -27.25);
  const max = Math.max(dataMax + 1.5, -24.75);
  const span = max - min;
  // Sumbu waktu nyata dari sampled_at: histori mencampur baris perubahan status (Rx
  // lama) dan baris optik 15 menit (Rx segar), jadi indeks seragam menyesatkan.
  const times = points.map((p) => Date.parse(p.sampled_at));
  const tStart = Math.min(...times.filter(Number.isFinite));
  const tEnd = Math.max(...times.filter(Number.isFinite));
  const x = (i: number) =>
    !Number.isFinite(times[i]) || tEnd === tStart ? 50 : ((times[i] - tStart) / (tEnd - tStart)) * 100;
  const y = (v: number) => 100 - ((v - min) / span) * 100;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => max - f * span);
  const range = `${fmtDateTime(points[0].sampled_at)} → ${fmtDateTime(points[points.length - 1].sampled_at)}`;
  // Titik non-null terakhir (ONU Rx dulu, fallback OLT Rx) untuk baris "Terakhir".
  const lastRxPoint = [...points].reverse().find((p) => p.rx_power_dbm !== null || p.olt_rx_power_dbm !== null);
  const lastRxValue = lastRxPoint
    ? (lastRxPoint.rx_power_dbm !== null ? lastRxPoint.rx_power_dbm : lastRxPoint.olt_rx_power_dbm)
    : null;
  return (
    <>
    <div className="my-2 flex gap-2.5">
      {/* Label sumbu Y di luar SVG: SVG non-uniform scale, teks di dalamnya ikut melar. */}
      <div className="flex h-36 w-8 shrink-0 flex-col justify-between py-1 text-right font-mono text-[10px] text-faint">
        {ticks.map((t, i) => <span key={i}>{t.toFixed(1)}</span>)}
      </div>
      <div className="min-w-0 grow rounded-sm border border-line/40 bg-sunken/20 p-1">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-36 w-full" role="img"
             aria-label={`Grafik Rx ONU dan OLT, ${all.length} titik, terendah ${dataMin.toFixed(1)} dBm`}>
          {ticks.map((t, i) => (
            <line key={i} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
                  strokeWidth="0.3" className="text-line" vectorEffect="non-scaling-stroke" />
          ))}
          {[-25, -27, -28].map((t) => (
            <line key={t} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
                  strokeWidth="0.4" strokeDasharray="2 2" className="text-muted" vectorEffect="non-scaling-stroke" />
          ))}
          {series.map((s) => {
            // Garis diputus di null (LOS/offline), seperti grafik trafik — sebelumnya
            // titik null dibuang lalu ujungnya disambung, sehingga LOS tidak terlihat.
            // Segmen satu titik digambar sebagai lingkaran (polyline 1 titik tak terlihat).
            if (s.values.length === 1) {
              const i = points.findIndex((p) => p[s.field] !== null);
              return <circle key={s.label} cx={x(i)} cy={y(s.values[0])} r="1.2" className={s.dot} vectorEffect="non-scaling-stroke" />;
            }
            const segments: string[][] = [];
            let current: string[] = [];
            points.forEach((p, i) => {
              if (p[s.field] === null) { if (current.length) segments.push(current); current = []; }
              else current.push(`${x(i)},${y(p[s.field] as number)}`);
            });
            if (current.length) segments.push(current);
            return (
              <g key={s.label}>
                {segments.map((seg, si) =>
                  seg.length === 1
                    ? <circle key={si} cx={seg[0].split(",")[0]} cy={seg[0].split(",")[1]} r="1.2" className={s.dot} vectorEffect="non-scaling-stroke" />
                    : <polyline key={si} points={seg.join(" ")} fill="none" stroke="currentColor" strokeWidth="1.2"
                                className={s.line} vectorEffect="non-scaling-stroke" />
                )}
              </g>
            );
          })}
        </svg>
        <p className="mt-1.5 flex justify-between px-1 font-mono text-[10px] text-faint">
          <span>dBm</span><span>{range}</span>
        </p>
      </div>
    </div>
    {/* Label garis ambang: kolom gutter Y hanya berisi angka tick, jadi labelnya
        ditulis sebagai baris keterangan di bawah grafik (bukan di dalam SVG yang
        non-uniform scale) — tetap text-faint 10px, tanpa tooltip/zoom/library baru. */}
    <p className="px-1 font-mono text-[10px] text-faint">Garis putus: −25 Fair · −27 Weak · −28 Critical</p>
    {lastRxPoint && lastRxValue !== null && (
      <p className="px-1 font-mono text-[10px] text-faint">Terakhir: {lastRxValue.toFixed(1)} dBm · {fmtDateTime(lastRxPoint.sampled_at)}</p>
    )}
    <StatusStrip points={points} />
    </>
  );
}

/** Bagian `Status history` dari kartu yang sama: satu pita blok per bacaan, hijau = online,
 *  merah = bacaan status lain (los/dying_gasp/offline). Datanya baris yang SAMA dengan
 *  grafik Rx (`onu_signal_history`, kolom `status`), jadi tidak ada panggilan tambahan.
 *  ponytail: pita proporsional-per-bacaan, bukan sumbu waktu nyata — jarak antar sampel
 *  seragam (1/15 menit). skipped: skala waktu nyata, tambah kalau operator memintanya. */
function StatusStrip({ points }: { points: SignalPoint[] }) {
  if (points.length === 0) return null;
  const downs = points.filter((p) => p.status !== "online").length;
  // Opsi (b) dari audit: pita tetap per bacaan (bukan proporsional waktu), tapi
  // ditambah teks downtime terpanjang + merah dipecah: los/dying_gasp = down,
  // offline/power_off/lainnya = warn, supaya "mati total" tidak sama dengan "putus".
  let longest = { count: 0, start: "", end: "" };
  let run = { count: 0, start: "" };
  points.forEach((p) => {
    if (p.status !== "online") {
      if (run.count === 0) run = { count: 1, start: p.sampled_at };
      else run.count += 1;
      if (run.count > longest.count) longest = { count: run.count, start: run.start, end: p.sampled_at };
    } else run = { count: 0, start: "" };
  });
  const tone = (s: string) =>
    s === "online" ? "bg-fiber" : s === "los" || s === "dying_gasp" ? "bg-down" : "bg-warn";
  return (
    <div className="mt-2">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <span className="text-xs font-medium">Status History (Uptime)</span>
        <span className="font-mono text-[10px] text-faint">{points.length} bacaan · {downs} tidak online</span>
      </div>
      {longest.count > 0 && (
        <p className="mb-1 font-mono text-[10px] text-faint">
          Downtime terpanjang: {longest.count} bacaan · {fmtDateTime(longest.start)} → {fmtDateTime(longest.end)}
        </p>
      )}
      <div className="flex h-2 w-full gap-px overflow-hidden rounded-sm bg-sunken" role="img"
           aria-label={`Status history ONU: ${points.length} bacaan, ${downs} tidak online`}>
        {points.map((p, i) => (
          <span key={i} title={`${new Date(p.sampled_at).toLocaleString("id-ID")} · ${p.status}`}
                className={`flex-1 ${p.status === "online" ? "bg-fiber" : tone(p.status)}`} />
        ))}
      </div>
    </div>
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
  // Sumbu X waktu nyata (bukan indeks sampel): gap >2x interval poll memutus garis,
  // supaya jeda sampling tidak digambar sebagai garis lurus yang menyesatkan.
  const tStart = points[0].t;
  const tEnd = points[points.length - 1].t;
  const x = (i: number) =>
    tEnd === tStart ? 50 : ((points[i].t - tStart) / (tEnd - tStart)) * 100;
  const y = (v: number) => 100 - (v / top) * 100;
  const segments = (pick: (p: TrafficPoint) => number) => {
    const segs: string[][] = [];
    let current: string[] = [];
    points.forEach((p, i) => {
      if (i > 0 && points[i].t - points[i - 1].t > 2 * TRAFFIC_MS) {
        if (current.length) segs.push(current);
        current = [];
      }
      current.push(`${x(i)},${y(pick(p))}`);
    });
    if (current.length) segs.push(current);
    return segs;
  };
  const range = `${fmtDateTime(new Date(tStart).toISOString())} → ${fmtDateTime(new Date(tEnd).toISOString())}`;
  // Titik terakhir sesi LIVE (t = epoch ms): out = upload, in = download.
  const lastLive = points.at(-1) ?? null;
  return (
    <>
    <div className="flex gap-2">
      {/* Label sumbu Y di luar SVG: SVG-nya non-uniform scale, teks di dalamnya ikut melar. */}
      <div className="flex h-40 w-12 shrink-0 flex-col justify-between py-0.5 text-right font-mono text-[10px] text-faint">
        {[...ticks].reverse().map((t, i) => <span key={i}>{axisTick(t)}</span>)}
      </div>
      <div className="min-w-0 grow rounded-sm border border-line/40 bg-sunken/20 p-1">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-40 w-full" role="img"
             aria-label={`Grafik trafik LIVE, ${points.length} sampel, puncak ${peak.toFixed(2)} Mbps`}>
          {ticks.map((t) => (
            <line key={t} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
                  strokeWidth="0.3" className="text-line" vectorEffect="non-scaling-stroke" />
          ))}
          {([["text-amber", (p: TrafficPoint) => p.outMbps], ["text-fiber", (p: TrafficPoint) => p.inMbps]] as const).map(([cls, pick]) => (
            <g key={cls}>
              {segments(pick).map((seg, si) =>
                seg.length === 1
                  ? <circle key={si} cx={seg[0].split(",")[0]} cy={seg[0].split(",")[1]} r="1.2" className={cls.replace("text-", "fill-")} vectorEffect="non-scaling-stroke" />
                  : <polyline key={si} points={seg.join(" ")} fill="none" stroke="currentColor" strokeWidth="1.5"
                              className={cls} vectorEffect="non-scaling-stroke" />
              )}
            </g>
          ))}
        </svg>
        <p className="mt-1.5 flex justify-between px-1 font-mono text-[10px] text-faint">
          <span>Mbps</span><span>{range}</span>
        </p>
      </div>
    </div>
    {lastLive && (
      <p className="mt-1 font-mono text-[10px] text-faint">
        Terakhir: Download {mbps(lastLive.inMbps)} · Upload {mbps(lastLive.outMbps)} · {fmtDateTime(new Date(lastLive.t).toISOString())}
      </p>
    )}
    </>
  );
}

/** Batas atas sumbu yang "rapi": 1, 2, 5 × 10^n tepat di atas nilai puncak. */
function niceTop(peak: number) {
  if (!(peak > 0)) return 1;
  const pow = 10 ** Math.floor(Math.log10(peak));
  for (const m of [1, 2, 5, 10]) if (peak <= m * pow) return m * pow;
  return 10 * pow;
}

/** Grafik `Traffic history`: dua polyline dari sampel bps yang BENAR-BENAR tersimpan di
 *  DB (sampler worker, ±5 menit sekali). Titik dengan `null` (laju tidak diketahui:
 *  sampel pertama, counter wrap, sampler berhenti) MEMUTUS garis — tidak pernah
 *  digambar sebagai nol.
 *
 *  ponytail: satu SVG polyline seperti RxChart/LiveChart, bukan library chart —
 *  pertanyaan operator ("kapan jenuh / kapan sepi") sudah terjawab garis.
 *  skipped: tooltip per titik, zoom; tambah kalau operator memintanya. */
function TrafficHistoryChart({ points }: { points: TrafficHistoryPoint[] }) {
  const rated = points.filter((p) => p.in_bps !== null || p.out_bps !== null);
  if (rated.length < 2) {
    return (
      <p className="py-10 text-center text-muted">
        {points.length === 0
          ? "Belum ada sampel trafik. Tunggu poll berikutnya."
          : "Sampel trafik belum cukup. Tunggu poll berikutnya."}
      </p>
    );
  }
  const peak = Math.max(...rated.flatMap((p) => [p.in_bps ?? 0, p.out_bps ?? 0])) / 1e6;
  const top = niceTop(peak);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  // Sumbu waktu nyata, seperti RxChart: indeks seragam menyembunyikan celah sampler.
  const times = points.map((p) => Date.parse(p.sampled_at));
  const tStart = Math.min(...times.filter(Number.isFinite));
  const tEnd = Math.max(...times.filter(Number.isFinite));
  const x = (i: number) =>
    !Number.isFinite(times[i]) || tEnd === tStart ? 50 : ((times[i] - tStart) / (tEnd - tStart)) * 100;
  const y = (mbpsValue: number) => 100 - (mbpsValue / top) * 100;
  /** Segmen terpisah per rentetan titik yang lajunya diketahui: jeda sampler = garis
   *  putus. Segmen diputus juga bila selisih waktu antar titik > 15 menit (3x interval
   *  sampler 5 menit) — menyambung melintasi celah itu akan mengarang trafik yang tidak
   *  pernah diukur. Titik terisolasi digambar sebagai lingkaran, bukan dibuang. */
  const segments = (pick: (p: TrafficHistoryPoint) => number | null) => {
    const lines: string[] = [];
    const dots: string[] = [];
    let current: string[] = [];
    const flush = () => {
      if (current.length === 1) dots.push(current[0]);
      else if (current.length > 1) lines.push(current.join(" "));
      current = [];
    };
    points.forEach((p, i) => {
      const v = pick(p);
      const gap = i > 0 && Number.isFinite(times[i]) && Number.isFinite(times[i - 1])
        && times[i] - times[i - 1] > 15 * 60 * 1000;
      if (v === null) flush();
      else if (gap) flush();
      if (v !== null) current.push(`${x(i)},${y(v / 1e6)}`);
    });
    flush();
    return { lines, dots };
  };
  const span = `${fmtDateTime(points[0].sampled_at)} → ${fmtDateTime(points[points.length - 1].sampled_at)}`;
  // Sampel terakhir yang lajunya diketahui di minimal satu arah.
  const lastTraffic = [...points].reverse().find((p) => p.in_bps !== null || p.out_bps !== null);
  return (
    <>
    <div className="my-2 flex gap-2.5">
      {/* Label sumbu Y di luar SVG: SVG-nya non-uniform scale, teks di dalamnya ikut melar. */}
      <div className="flex h-36 w-8 shrink-0 flex-col justify-between py-1 text-right font-mono text-[10px] text-faint">
        {[...ticks].reverse().map((t, i) => <span key={i}>{axisTick(t)}</span>)}
      </div>
      <div className="min-w-0 grow rounded-sm border border-line/40 bg-sunken/20 p-1">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-36 w-full" role="img"
             aria-label={`Grafik histori trafik, ${rated.length} sampel, puncak ${peak.toFixed(2)} Mbps`}>
          {ticks.map((t) => (
            <line key={t} x1="0" x2="100" y1={y(t)} y2={y(t)} stroke="currentColor"
                  strokeWidth="0.3" className="text-line" vectorEffect="non-scaling-stroke" />
          ))}
          {segments((p) => p.out_bps).lines.map((pts, i) => (
            <polyline key={`up-${i}`} points={pts} fill="none" stroke="currentColor"
                      strokeWidth="1.2" className="text-amber" vectorEffect="non-scaling-stroke" />
          ))}
          {segments((p) => p.out_bps).dots.map((pt, i) => (
            <circle key={`up-dot-${i}`} cx={pt.split(",")[0]} cy={pt.split(",")[1]} r="1.2"
                    className="fill-amber" vectorEffect="non-scaling-stroke" />
          ))}
          {segments((p) => p.in_bps).lines.map((pts, i) => (
            <polyline key={`down-${i}`} points={pts} fill="none" stroke="currentColor"
                      strokeWidth="1.2" className="text-fiber" vectorEffect="non-scaling-stroke" />
          ))}
          {segments((p) => p.in_bps).dots.map((pt, i) => (
            <circle key={`down-dot-${i}`} cx={pt.split(",")[0]} cy={pt.split(",")[1]} r="1.2"
                    className="fill-fiber" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        <p className="mt-1.5 flex justify-between px-1 font-mono text-[10px] text-faint">
          <span>Mbps</span><span>{span}</span>
        </p>
      </div>
    </div>
    {lastTraffic && (
      <p className="px-1 font-mono text-[10px] text-faint">
        Terakhir: Download {lastTraffic.in_bps !== null ? mbpsId(lastTraffic.in_bps / 1e6) : "—"} · Upload {lastTraffic.out_bps !== null ? mbpsId(lastTraffic.out_bps / 1e6) : "—"} · {fmtDateTime(lastTraffic.sampled_at)}
      </p>
    )}
    </>
  );
}

/** Ringkasan histori trafik: puncak & rata-rata per arah dari sampel yang lajunya diketahui. */
function trafficStats(points: TrafficHistoryPoint[]) {
  const pick = (f: (p: TrafficHistoryPoint) => number | null) =>
    points.map(f).filter((v): v is number => v !== null);
  const down = pick((p) => p.in_bps);
  const up = pick((p) => p.out_bps);
  if (down.length === 0 && up.length === 0) return null;
  const avg = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  return {
    // Jumlah baris sampel yang punya laju di minimal satu arah (bukan max per arah,
    // yang bukan jumlah baris bila satu arah lebih banyak terbaca).
    count: points.filter((p) => p.in_bps !== null || p.out_bps !== null).length,
    downMax: Math.max(0, ...down) / 1e6, downAvg: avg(down) / 1e6,
    upMax: Math.max(0, ...up) / 1e6, upAvg: avg(up) / 1e6,
  };
}

// Tick < 1 Mbps dengan 2 desimal (0.05 Mbps sebelumnya tampil "0.0" dan tak terbedakan).
const axisTick = (v: number) =>
  v === 0 ? "0" : v < 1 ? v.toFixed(2).replace(/0+$/, "").replace(/\.$/, "") : String(Number(v.toFixed(1)));

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

/** Kartu grafik acuan mock (`.graph-item`): kotak berangka 1px, judul tebal kiri + pemilih
 *  rentang kanan, latar permukaan seperti interior grafik. */
function ChartCard(
  { title, toggle, children, legend }:
  { title: string; toggle?: React.ReactNode; children: React.ReactNode; legend?: React.ReactNode },
) {
  return (
    <div className="min-w-0 rounded-md border bg-surface p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-ink">{title}</h3>
        {toggle}
      </div>
      {children}
      {legend && <div className="mt-3 grid gap-1.5 border-t pt-2.5 text-xs">{legend}</div>}
    </div>
  );
}

function LegendRow({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-2 text-muted">
        <span aria-hidden className={`inline-block size-2 rounded-full ${color}`} />
        {label}
      </span>
      <span className="font-mono font-medium text-ink">{value}</span>
    </div>
  );
}

/** Toggle rentang 24 jam / 7 hari / 30 hari gaya mock (segmen; aktif = permukaan + fiber).
 *  State lokal per kartu grafik; sumber data tetap endpoint histori/sinyal yang ada.
 *  Target sentuh 44px di mobile, segmen mengecil di desktop. */
function RangeToggle(
  { value, onChange, aria }: { value: RangeKey; onChange: (v: RangeKey) => void; aria: string },
) {
  return (
    <div role="tablist" aria-label={aria} className="flex flex-wrap gap-1 rounded-sm border bg-sunken/40 p-0.5">
      {RANGES.map(([v, label]) => (
        <button key={v} type="button" role="tab" aria-selected={value === v}
          onClick={() => onChange(v)}
          className={`min-h-11 rounded-sm px-2 py-0.5 text-xs sm:min-h-0 ${value === v
            ? "bg-surface font-semibold text-fiber shadow-xs"
            : "font-medium text-muted hover:text-ink"}`}>
          {label}
        </button>
      ))}
    </div>
  );
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
  if (p === null) return DASH;
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

/** Nomor VLAN yang BENAR-BENAR terpasang di perangkat — sumber centang awal modal
 *  "Update attached VLANs" dan VLAN WAN "Update ONU mode".
 *
 *  Beda dari `serviceVlans()` yang untuk TAMPILAN: di sini VLAN management TIDAK
 *  disaring. Alasannya keselamatan trafik, bukan kosmetik: `build_attached_vlans` di
 *  backend menulis ulang SELURUH daftar `service-port` ONU dari nilai yang dikirim.
 *  Kalau VLAN management dibuang dari centang awal, operator yang hanya menambah satu
 *  VLAN akan ikut MENGHAPUS service-port management ONU tanpa pernah melihatnya di
 *  dialog. Nomornya tetap tidak tampil sebagai pilihan (opsi modal disaring
 *  `serviceVlanOptions`), jadi tidak bisa di-uncheck — hanya ikut terkirim utuh.
 *
 *  `[]` saat backend belum mengirim daftar: tanpa data nyata jangan mengarang centang. */
function attachedVlanNumbers(d: DetailWithVlans): number[] {
  if (!Array.isArray(d.service_vlans)) return [];
  const seen = new Set<number>();
  for (const v of d.service_vlans) {
    if (typeof v.vlan_id === "number") seen.add(v.vlan_id);
  }
  return [...seen].sort((a, b) => a - b);
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
  // Penjaga in-flight: satu bulkwalk bisa 9-12 detik sementara interval live 5 detik,
  // jadi tanpa ini tick menumpuk dan baseline ditimpa sesuai urutan selesai.
  const inFlight = useRef(false);

  useEffect(() => {
    // Serial berubah = ONU lain: titik sesi lama tidak boleh tercampur sesi baru.
    setPoints([]);
    setLast(null);
    setError(null);
    prev.current = null;
    if (!enabled) {
      // Titik dibuang saat LIVE mati: "Max" di panel = maksimum sesi LIVE yang sedang jalan,
      // bukan sisa sesi sebelumnya yang sudah tidak terlihat di grafik.
      return;
    }
    let alive = true;
    const tick = async () => {
      // Tab tersembunyi: baseline basi — buang, supaya titik pertama setelah kembali
      // tidak memakai sampel lama. deltaMbps juga menolak delta > 60 detik.
      if (document.hidden) { prev.current = null; return; }
      if (inFlight.current) return;
      inFlight.current = true;
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
        // Fetch gagal juga membatalkan baseline: sampel berikutnya harus jadi baseline
        // baru, bukan dibandingkan dengan sampel sebelum kegagalan.
        prev.current = null;
        if (alive) setError(e instanceof Error ? e.message : "Gagal membaca counter trafik");
      } finally {
        inFlight.current = false;
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

/** Ubah VLAN primer (onu.vlan_id) lewat job set_onu_vlan — endpoint ini sebelumnya
 *  tidak punya UI sama sekali, hanya bisa dipanggil lewat API langsung. */
function PrimaryVlanModal({ serial, oltId, currentVlanId, onClose, onDone }: {
  serial: string; oltId: number; currentVlanId: number | null;
  onClose: () => void; onDone: (msg: string) => void;
}) {
  const [selected, setSelected] = useState(currentVlanId != null ? String(currentVlanId) : "");
  const [jobId, setJobId] = useState<number | null>(null);
  const vlans = useQuery({
    queryKey: ["vlans", oltId],
    queryFn: () => api<Vlan[]>(`/api/vlans${qs({ olt_id: oltId })}`),
  });
  const save = useMutation({
    mutationFn: () => api<{ job_id: number }>(`/api/onus/${serial}/vlan`, {
      method: "POST", json: { vlan_id: Number(selected) },
    }),
    // Seperti modal aksi job lainnya: jangan tutup saat job dibuat, tampilkan
    // status job dulu; catatan halaman baru diisi saat dialog status ditutup.
    onSuccess: (r) => { setJobId(r.job_id); },
  });
  const rows = (vlans.data ?? []).filter((v) => v.olt_id === oltId || v.olt_id == null);
  if (jobId !== null) {
    return (
      <ModalShell title={`Job ubah VLAN primer #${jobId}`}
                  onClose={() => { onDone(`Job ubah VLAN primer #${jobId} dibuat.`); onClose(); }}
                  closeLabel="Tutup">
        <JobTrace jobId={jobId} />
      </ModalShell>
    );
  }
  return (
    <ModalShell title="Ubah VLAN primer" onClose={onClose} action="Simpan"
                busy={save.isPending} error={save.error?.message ?? null}
                disabled={!selected || Number(selected) === currentVlanId}
                onSubmit={() => save.mutate()}>
      <Field label="VLAN">
        <select className="w-full rounded border border-line bg-surface px-2 py-1.5"
                value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Pilih VLAN ...</option>
          {rows.map((v) => (
            <option key={v.id} value={v.id}>VLAN {v.vlan_id}{v.name ? ` — ${v.name}` : ""}</option>
          ))}
        </select>
      </Field>
      {vlans.error && <p className="mt-2 text-xs text-down">{vlans.error.message}</p>}
    </ModalShell>
  );
}

export function OnuDetail() {
  const { id: routeKey = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isManager } = useAuth();
  /** Rentang tiap kartu grafik = state lokal toggle (24 jam / 7 hari / 30 hari); memilih
   *  rentang di kartu Trafik tidak mengubah kartu Sinyal, begitu pula sebaliknya. Sumber
   *  data tetap endpoint histori/sinyal yang ada — rentang lain menampilkan apa adanya.
   *  Nilai awal dibaca dari query URL `?range` / `?srange` (deep-link), lalu ditulis balik
   *  saat toggle dipakai — state tetap lokal, URL hanya untuk membagikan tautan. */
  const [params, setParams] = useSearchParams();
  const rangeFromUrl = (key: string): RangeKey => {
    const v = params.get(key);
    return v === "7d" || v === "30d" ? v : "24h";
  };
  const [range, setRange] = useState<RangeKey>(() => rangeFromUrl("range"));
  const [srange, setSrange] = useState<RangeKey>(() => rangeFromUrl("srange"));
  /** Tulis balik rentang ke URL (replace, tanpa entri history baru). */
  const pickRange = (key: "range" | "srange", set: (v: RangeKey) => void) => (v: RangeKey) => {
    set(v);
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.set(key, v);
      return next;
    }, { replace: true });
  };
  /** Modal aksi ONU (kontrak `/api/onus/{id}/actions`), satu state untuk semua modal. */
  const [modal, setModal] = useState<OnuModalState | null>(null);
  const [vlanPrimerOpen, setVlanPrimerOpen] = useState(false);
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

  // Navigasi /onu/A -> /onu/B tanpa unmount: semua state sesi ONU lama harus dibuang,
  // kalau tidak chip IP, panel diagnostik, dan grafik LIVE milik A tampil di B.
  useEffect(() => {
    setLiveIp(null);
    setLiveWanIp(null);
    setNote("");
    setDiagView(null);
    setDiagJobId(null);
    setDiagRunView(null);
    setDiagMsg("");
    setDiagStart(null);
    setDiagSecs(0);
    setLive(false);
    setModal(null);
    setVlanPrimerOpen(false);
  }, [routeKey]);

  const onu = useQuery({
    queryKey: ["onu", routeKey],
    queryFn: () => api<DetailWithVlans>(detailPath(routeKey)),
    refetchInterval: live ? LIVE_MS : false,
  });
  /** Satu-satunya identitas untuk semua operasi: serial dari respons detail. */
  const serial = onu.data?.serial_number ?? "";
  /** IP terbaca perangkat (POST /api/onus/{id}/refresh-ip, sumber `show gpon remote-onu
   *  ip-host`) untuk tautan buka tab baru. `liveIp` = IP VLAN management (Mgmt IP),
   *  `liveWanIp` = IP host di VLAN non-management (Setup WAN). null = belum terbaca. */
  const [liveIp, setLiveIp] = useState<string | null>(null);
  const [liveWanIp, setLiveWanIp] = useState<string | null>(null);
  const fetchIp = () => {
    const id = onu.data?.id;
    if (!id) return;
    api<{ ip_address: string | null; wan_ip_address: string | null }>(
      `/api/onus/${id}/refresh-ip`, { method: "POST" })
      .then((r) => {
        setLiveIp(r.ip_address ?? null);
        setLiveWanIp(r.wan_ip_address ?? null);
      })
      // Jangan diam-diam: kalau pembacaan IP gagal, operator harus tahu bahwa
      // IP yang tampil masih dari cache, bukan hasil baca perangkat terbaru.
      .catch((e: Error) => setNote(`IP perangkat gagal dibaca: ${e.message}`));
  };
  // Refresh IP HANYA saat dibuka bila salah satu kolom masih kosong di cache DB — satu
  // POST mengisi dua-duanya (`ip_address` management + `wan_ip_address` non-management);
  // kalau sudah ada, tampilkan langsung dari cache, jangan tunggu SSH ke OLT.
  useEffect(() => {
    if (onu.data?.id && (!onu.data?.ip_address || !onu.data?.wan_ip_address)) fetchIp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onu.data?.id]);
  const signal = useQuery({
    queryKey: ["onu", serial, "signal", srange],
    queryFn: () => api<SignalPoint[]>(`/api/onus/${serial}/signal?range=${srange}`),
    enabled: serial !== "",
  });
  const logs = useQuery({
    queryKey: ["onu", serial, "logs"],
    queryFn: () => api<OnuLog[]>(`/api/onus/${serial}/logs?limit=50`),
    enabled: serial !== "",
  });
  /** Histori trafik dari sampel tersimpan (tanpa menyentuh OLT) — rentang sama dengan
   *  kartu sinyal supaya satu pemilih rentang mengatur kedua grafik. */
  const trafficHistory = useQuery({
    queryKey: ["onu", serial, "traffic-history", range],
    queryFn: () =>
      api<TrafficHistoryPoint[]>(`/api/onus/${serial}/traffic/history?range=${range}`),
    enabled: serial !== "",
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
        // Backend memakai 409 untuk dua penyebab berbeda: job sejenis masih diproses
        // ("masih diproses") vs ONU belum ter-provisioning ("not provisioned yet").
        setDiagMsg(e.message.includes("not provisioned")
          ? "ONU ini belum ter-provisioning (belum ada onu_index atau konfigurasi belum sukses)."
          : "Pembacaan untuk ONU ini masih berjalan, tunggu selesai.");
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

  /** Running-config sukses = backend sudah menyinkronkan mode WAN/PPPoE ke DB: muat ulang ONU. */
  const diagDone = diagJob.data?.status === "success" && diagView === "running" ? diagJob.data.id : null;
  useEffect(() => {
    if (diagDone !== null) qc.invalidateQueries({ queryKey: ["onu"] });
  }, [diagDone, qc]);

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
  const ipLive = liveIp ?? d.ip_address;
  const wanIpLive = liveWanIp ?? d.wan_ip_address;
  const stats = rxStats(signal.data ?? [], "rx_power_dbm");
  const oltStats = rxStats(signal.data ?? [], "olt_rx_power_dbm");
  const tStats = trafficStats(trafficHistory.data ?? []);
  // Katalog dicocokkan UTAMA lewat ID; nama hanya fallback bila ID tidak ada (nama
  // usang tidak boleh mengalahkan ID yang valid).
  const specs = (onuTypes.data ?? []).find((t) => t.id === d.onu_type_id)
    ?? (d.onu_type_id === null
      ? (onuTypes.data ?? []).find((t) => t.name.toLowerCase() === (d.onu_type ?? "").toLowerCase())
      : undefined);
  const statusKey = d.admin_state === "disabled" ? "disabled" : d.status;
  /** `null` = backend belum mengirim daftar VLAN (field `vlans`), bukan "tidak ada VLAN". */
  const vlanList = serviceVlans(d);
  const meta = d.device_metadata ?? null;
  const onuIf = `gpon-onu_1/${d.slot}/${d.port}${d.onu_index === null ? "" : `:${d.onu_index}`}`;
  const latest = traffic.points.at(-1) ?? null;
  /** "Max" di panel LIVE = puncak sejak LIVE dinyalakan (titik dibuang saat LIVE mati). */
  const liveMax = traffic.points.length === 0 ? null : {
    out: Math.max(...traffic.points.map((p) => p.outMbps)),
    in: Math.max(...traffic.points.map((p) => p.inMbps)),
  };
  /** Teks baris spesifikasi koneksi. Nilai mode datang EFEKTIF dari backend: hasil baca
   *  CLI/running-config, atau default pemilik (`routing` / `webpage`) bila tidak terbaca —
   *  `onu_mode_source`/`wan_mode_source` menyebut asalnya. Halaman tidak menambal sendiri. */
  const onuMode = onuLabel(d.onu_mode);
  const wanMode = wanLabel(d.wan_mode);
  const isPppoe = (d.wan_mode ?? "").toLowerCase() === "pppoe";
  /** `webpage` = konfigurasi dilakukan di halaman web ONU, tidak ada IP WAN yang dibaca OLT. */
  const wanHasIp = wanMode !== null && (d.wan_mode ?? "").toLowerCase() !== "webpage";
  /** Mgmt IP hanya punya mode Static/DHCP di acuan; nilai lain tampil apa adanya. */
  const mgmtMode = d.mgmt_ip_mode === null || d.mgmt_ip_mode === ""
    ? null
    : (MGMT_MODE_LABEL[d.mgmt_ip_mode.toLowerCase()] ?? d.mgmt_ip_mode);

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

  /** Modal lokasi: satu titik buka untuk semua baris lokasi/identitas kiri atas. */
  const locationDialog = () => setModal({ kind: "location" });
  /** Data yang dipakai modal aksi: subset detail, tanpa menyalin seluruh tipe halaman. */

  const modalOnu: ModalOnu = {
    id: d.id, serial_number: d.serial_number, onu_type_id: d.onu_type_id,
    external_id: d.external_id, olt_id: d.olt_id, olt_name: d.olt_name,
    slot: d.slot, port: d.port, onu_mode: d.onu_mode, wan_mode: d.wan_mode, pppoe_username: d.pppoe_username,
    wan_vlan: d.wan_vlan ?? null, pppoe_password: d.pppoe_password ?? null,
    mgmt_ip_mode: d.mgmt_ip_mode, ip_address: ipLive,
    download_profile_name: d.download_profile_name, upload_profile_name: d.upload_profile_name,
    download_speed_profile_id: d.download_speed_profile_id, upload_speed_profile_id: d.upload_speed_profile_id,
    zone_id: d.zone_id, splitter_id: d.splitter_id, splitter_port: d.splitter_port,
    name: d.name, customer_name: d.customer_name, address: d.address, contact: d.contact,
    latitude: d.latitude, longitude: d.longitude,
    attached_vlans: attachedVlanNumbers(d),
    port_configs: d.port_configs ?? null,
  };

  return (
    // pb-20 di mobile saja: bar aksi sticky (~60px) tidak boleh menutupi section
    // terakhir; desktop tetap tanpa padding bawah tambahan.
    <div className="space-y-3 pb-20 md:pb-0">
      {/* Judul halaman hanya untuk pembaca layar: teksnya diminta dihapus dari tampilan
          (desktop maupun mobile), heading dipertahankan demi hierarki aksesibilitas. */}
      <h1 className="sr-only">Detail ONU</h1>

      {note && (
        <p className="text-muted" role="status">{note}</p>
      )}

      {/* Strip identitas: satu baris wrap di mobile, di atas blok Status. StatusBadge
          DIPINDAH ke sini dari blok Status (tidak diduplikasi); urutan section di bawah
          tidak berubah. Nama = customer_name, fallback name; chip SN gaya yang sama
          dengan chip SN di blok Identitas. */}
      <div className="entrance flex flex-wrap items-center gap-2 rounded-md border bg-surface px-3 py-2">
        <span className="text-base font-semibold">{d.customer_name || d.name || "—"}</span>
        <StatusBadge status={statusKey} reason={d.last_down_reason} withLabel />
        <span className="rounded border border-line bg-sunken px-1.5 py-0.5 font-mono font-semibold text-fiber">{d.serial_number}</span>
        <Link className="text-fiber hover:underline" to={`/olt/${d.olt_id}`}>{d.olt_name}</Link>
        <span className="font-mono text-xs text-muted">{onuIf}</span>
      </div>

      {/* 1. BAGIAN ATAS mengikuti mock: blok `Status Perangkat` full-width (kartu `Level
          Sinyal Rx` dua kolom + kartu telemetri 6 baris), lalu dua blok bersebelahan
          `Identitas` | `Jaringan & Layanan` (masing-masing `lg:col-span-6` pada grid 12
          kolom). Menumpuk berurutan di bawah `lg`. Nilai kosong tetap `None` miring (blok
          identitas) atau "—" redup. */}
      <Block
        title="Status Perangkat"
        action={
          <div className="flex flex-wrap items-center gap-2">
            {live && (
              <span className="font-mono text-xs text-fiber">auto-refresh {LIVE_MS / 1000}s</span>
            )}
            <Button size="sm" variant="quiet" onClick={() => { onu.refetch(); fetchIp(); }} disabled={onu.isFetching}>
              {onu.isFetching ? "Memuat ..." : "Muat ulang"}
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3">
          {/* Kartu Level Sinyal Rx: DUA kolom (ONU Rx 1490nm / OLT Rx 1310nm), nilai mono
              besar + badge bucket berwarna; rentang normal di kanan judul kartu. */}
          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-muted">Level Sinyal Rx</span>
              <span className="font-mono text-[11px] text-faint">Normal −8,0 s/d −27,0 dBm</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <RxBox title="ONU Rx 1490nm" value={d.rx_power_dbm} />
              <RxBox title="OLT Rx 1310nm" value={d.olt_rx_power_dbm} />
            </div>
          </div>
          {/* Telemetri 6 baris dalam satu kartu (mock): label grid 140px, titik status kecil
              untuk nilai berstatus, nilai kosong "—" redup. */}
          <div className="divide-y divide-line rounded-md border bg-sunken/20 px-3.5 text-xs">
            <TRow label="Jarak kabel" dot={d.distance_m != null ? "up" : null}>
              <span className="font-mono">{d.distance_m != null ? fmtDistance(d.distance_m) : DASH}</span>
            </TRow>
            <TRow label="Status match" dot={stateTone(d.match_state)}>{orDash(d.match_state)}</TRow>
            <TRow label="Status konfigurasi" dot={stateTone(d.config_state)}>{orDash(d.config_state)}</TRow>
            <TRow label="Bias laser">
              {d.bias_current_ma === null ? DASH : (
                <span className="font-mono">{`${Number(d.bias_current_ma).toFixed(2)} mA`}</span>
              )}
            </TRow>
            <TRow label="Terakhir online">
              {d.last_seen_at ? <span className="font-mono">{fmtDateTime(d.last_seen_at)}</span> : DASH}
            </TRow>
            <TRow label="Terakhir down">
              {d.last_down_at ? `${dash(d.last_down_reason)} · ${fmtDateTime(d.last_down_at)}` : DASH}
            </TRow>
          </div>
        </div>
      </Block>

      <div className="entrance grid gap-4 lg:grid-cols-12 lg:items-start">
        <Block title="Identitas" className="lg:col-span-6"
               action={<span className="font-mono text-xs text-faint">ID: {d.id}</span>}>
          <div className="flex flex-col gap-1">
            <DRow label="OLT" value={
              <Link className="text-fiber hover:underline" to={`/olt/${d.olt_id}`}>{d.olt_name}</Link>
            } />
            <DRow label="ONU" value={
              <Link className="text-fiber hover:underline" to={`/configured?olt_id=${d.olt_id}`}>
                {onuIf}
              </Link>
            } />
            <DRow label="SN" value={<span className="rounded border border-line bg-sunken px-1.5 py-0.5 font-mono font-semibold text-fiber">{d.serial_number}</span>}
                  onEdit={isManager ? () => setModal({ kind: "replace-sn" }) : undefined} />
            <DRow label="Tipe ONU" value={orNone(d.onu_type)}
                  onEdit={isManager ? () => setModal({ kind: "onu-type" }) : undefined} />
            <DRow label="Preset konfigurasi" value={orNone(d.preset_name)} />
            {/* Nama/Kontak hanya dari field yang disunting modal Lokasi: fallback ke
                name/phone menampilkan nilai yang tidak bisa dihapus lewat pensil ini.
                Alamat: string description mentah (d.description) tidak lagi dipakai —
                hanya alamat hasil parse (meta?.address) bila backend mengirim
                device_metadata; bila master kosong dan metadata tidak ada, tampil "—". */}
            <DRow label="Nama pelanggan" value={orNone(d.customer_name)} onEdit={locationDialog} />
            <DRow label="Alamat"
                  value={fromMasterOrDescription(d.address, meta?.address)}
                  onEdit={locationDialog} />
            <DRow label="Kontak" value={orNone(d.contact)} onEdit={locationDialog} />
            <DRow label="Zona" value={fromMasterOrDescription(d.zone_name, meta?.zone)} onEdit={locationDialog} />
            <DRow label="Splitter" onEdit={locationDialog} value={
              d.splitter_name
                ? `${d.splitter_name}${d.splitter_port ? ` · port ${d.splitter_port}` : ""}`
                : fromMasterOrDescription(null, meta?.splitter)
            } />
            {/* Sektor belum ada kolomnya di master data Nexfiber: baris tetap ada supaya
                urutan acuan utuh, nilainya `None` karena memang tidak ada datanya.
                Tanpa pensil: pensil menyiratkan sektor bisa disunting padahal modal
                yang terbuka tidak punya field sektor. */}
            <DRow label="Sektor" value={NONE} />
            <DRow label="ID eksternal" value={orNone(d.external_id)}
                  onEdit={() => setModal({ kind: "external-id" })} />
            <DRow label="Tanggal otorisasi" value={
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
            <DRow label="Lokasi" value={d.latitude !== null && d.longitude !== null
              ? <a className="text-fiber hover:underline" target="_blank" rel="noreferrer"
                   href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=17/${d.latitude}/${d.longitude}`}>
                  {Number(d.latitude).toFixed(5)}, {Number(d.longitude).toFixed(5)}
                </a>
              : DASH} onEdit={locationDialog} />
          </div>
        </Block>

        <Block title="Jaringan & Layanan" className="lg:col-span-6">
          <div className="flex flex-col gap-1">
            {/* Panel Port Fisik (mock) = versi padat OnuRearPanel: PON menyala, LAN1..N,
                Reset, Power + chip "1 PON · N LAN". Hanya bila katalog ONU Types tahu
                jumlah port nyatanya — lebih baik kosong daripada port karangan. */}
            {specs && (specs.eth_ports > 0 || specs.voip_ports > 0) && (
              <OnuRearPanel ethPorts={specs.eth_ports} voipPorts={specs.voip_ports}
                            online={d.status === "online" && d.admin_state !== "disabled"} />
            )}
            {/* Mgmt IP mengikuti mock: "<Static|DHCP> - vlan: N" + chip IP hijau menuju
                Web GUI ONU. Mode kosong = perangkat tak melaporkan → tampil "None"
                (bukan fakta `Inactive`, bukan "belum terbaca"). */}
            <DRow label="Mgmt IP" value={
              <>
                {mgmtMode === null ? <span className="text-faint">None</span> : (
                  <span>
                    {mgmtMode}
                    {d.mgmt_vlan != null && ` - vlan: ${d.mgmt_vlan}`}
                  </span>
                )}
                {/* IP live tetap ditampilkan meski mode null: IP yang berhasil dibaca
                    tidak boleh disembunyikan hanya karena modenya tidak dilaporkan. */}
                {ipLive && (
                  <IpLink ip={ipLive} title={`Buka Web GUI ONU (${ipLive})`} />
                )}
              </>
            } onEdit={isManager ? () => setModal({ kind: "mgmt-ip" }) : undefined} />
            {/* Nexfiber belum punya profil ACS/TR-069 internal (DECISIONS.md), jadi nilainya
                selalu `Inactive` apa adanya dengan titik netral — bukan badge "via Mgmt IP"
                milik aplikasi lain. */}
            <DRow label="Profil TR069" value={<>Inactive <span className="text-faint">· Segera rilis</span></>} dot="idle" />
            <DRow label="Otentikasi" value={d.auth_type === "loid" ? `LOID · ${dash(d.loid)}` : d.auth_type.toUpperCase()} />
            <DRow label="VLAN terpasang" value={
              vlanList === null ? (
                <>
                  <span>{dash(d.vlan_number)}</span>
                  <span className="text-faint">daftar lengkap belum dikirim backend</span>
                </>
              ) : vlanList.length === 0 ? (
                DASH
              ) : (
                <>
                  {vlanList.map((v) => (
                    <span key={v.vlan_id} className="inline-flex items-center rounded border border-line bg-sunken px-2 py-0.5 font-mono font-semibold text-ink"
                          title={v.name ?? undefined}>
                      VLAN {v.vlan_id}
                      {v.in_master === false && <span className="ml-0.5 text-warn">*</span>}
                    </span>
                  ))}
                  {vlanList.some((v) => v.in_master === false) && (
                    <span className="text-faint">* belum terdaftar di master VLAN</span>
                  )}
                </>
              )
            } onEdit={() => setModal({ kind: "attached-vlans" })} />
            <DRow label="VLAN primer" value={dash(d.vlan_number)}
                  onEdit={isManager ? () => setVlanPrimerOpen(true) : undefined} />
            {/* Mode ONU: nilai efektif dari backend (CLI atau default `routing`), cukup
                modenya saja — nomor VLAN sudah tampil di baris VLAN terpasang. */}
            <DRow label="Mode ONU" value={onuMode === null ? DASH : onuMode}
                  onEdit={() => setModal({ kind: "onu-mode" })} />
            {/* Setup WAN: label mode dari WAN_MODE_LABEL (huruf kapital di teks, bukan
                CSS uppercase) + chip IP tab baru — IP dari host di VLAN NON-management
                (`wanIpLive`), BUKAN IP management. `webpage` tidak punya IP WAN; IP WAN
                belum terbaca = mode tetap tampil tanpa chip. */}
            <DRow label="Setup WAN" value={
              wanMode === null ? DASH : (
                <>
                  <span>{wanMode}</span>
                  {wanHasIp && wanIpLive && (
                    <IpLink ip={wanIpLive} title="Buka IP WAN modem di tab baru" />
                  )}
                </>
              )
            } onEdit={() => setModal({ kind: "onu-mode" })} />
            {/* Kredensial PPPoE hanya untuk mode pppoe; static/dhcp/webpage menyembunyikan
                dua baris ini sepenuhnya. DUA baris terpisah (mock): username apa adanya dari
                backend, kata sandi mask default + tombol mata. Keduanya disunting lewat modal
                "Update ONU mode" (satu form untuk mode WAN + kredensial PPPoE). */}
            {isPppoe && (
              <>
                <DRow label="Username PPPoE" value={
                  d.pppoe_username ? <span className="font-mono text-ink">{d.pppoe_username}</span> : DASH
                } onEdit={() => setModal({ kind: "onu-mode" })} />
                <DRow label="Password PPPoE" value={<PppoePassword key={d.serial_number} password={d.pppoe_password ?? null} />}
                      onEdit={() => setModal({ kind: "onu-mode" })} />
              </>
            )}
          </div>
        </Block>
      </div>

      {/* 2. `Diagnostik` gaya mock pemilik: judul + sub "Operasi & status live" di kolom
          140px kiri, tombol operasi hijau mengisi baris, TR-069 mati + LIVE! di ujung kanan.
          Logika/handler diagnostik TIDAK diubah — tetap lewat job CLI backend, dan
          running-config tetap manager-only. */}
      <section className="entrance rounded-md border bg-surface p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="lg:w-[140px] lg:shrink-0">
            <h2 className="flex items-center gap-1.5 text-base font-bold text-fiber"><TitleIcon title="Diagnostik" />Diagnostik</h2>
            <p className="mt-0.5 text-xs text-faint">Operasi & status live</p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 grow">
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-1.5">
              <div className="grid grid-cols-2 gap-2 [&>*:last-child:nth-child(odd)]:col-span-2 sm:flex sm:flex-wrap sm:gap-1.5">
                <Button className="min-h-11 w-full sm:min-h-0 sm:w-auto" size="sm" variant="fiber"
                        onClick={() => runDiag("status")} disabled={diagRunning}>
                  {DIAG_LABEL.status}{diagRunning && diagRunView === "status" ? " ..." : ""}
                </Button>
                {/* Running-config utuh memuat nilai konfigurasi sensitif: tombolnya hanya dirender
                    untuk admin/superadmin, dan backend tetap menolak role lain (403). */}
                {isManager && (
                  <Button className="min-h-11 w-full sm:min-h-0 sm:w-auto" size="sm" variant="fiber"
                          onClick={() => runDiag("running")} disabled={diagRunning}>
                    {DIAG_LABEL.running}{diagRunning && diagRunView === "running" ? " ..." : ""}
                  </Button>
                )}
                <Button className="min-h-11 w-full sm:min-h-0 sm:w-auto" size="sm" variant="fiber"
                        onClick={() => runDiag("software")} disabled={diagRunning}>
                  {DIAG_LABEL.software}{diagRunning && diagRunView === "software" ? " ..." : ""}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2 [&>*:last-child:nth-child(odd)]:col-span-2 sm:ml-auto sm:flex sm:items-center sm:gap-1.5">
                {/* Tombol TR-069 ada di acuan, tapi Nexfiber belum punya ACS internal
                    (DECISIONS.md): dirender MATI dengan alasan yang jelas, bukan tombol yang
                    menembak endpoint karangan. */}
                <Button className="min-h-11 w-full sm:min-h-0 sm:w-auto" size="sm" variant="secondary" disabled
                        title="Butuh profil ACS/TR-069 internal yang belum ada di Nexfiber">
                TR-069
              </Button>
                {diagView && diagOutput && !diagRunning && (
                  <Button className="min-h-11 w-full sm:min-h-0 sm:w-auto" size="sm" variant="quiet"
                          onClick={() => navigator.clipboard?.writeText(diagOutput)}>
                    Salin
                  </Button>
                )}
                <Button className="min-h-11 w-full sm:min-h-0 sm:w-auto" size="sm"
                        variant={live ? "fiber" : "secondary"} aria-pressed={live}
                        onClick={() => setLive(!live)}>
                  <Gear size={13} aria-hidden />
                  LIVE!
                </Button>
              </div>
            </div>
          </div>
        </div>
            {diagMsg && (
              <p className="mt-2 text-sm text-amber" role="status">{diagMsg}</p>
            )}
            {/* Panel realtime HANYA saat LIVE aktif (acuan screenshot ke-2): grafik Mbps +
                dua baris ringkasan arah. Saat LIVE mati panel ini TIDAK dirender sama sekali. */}
            {live && (
              <div className="entrance mt-3 rounded-sm border bg-sunken p-3">
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
      </section>

      {/* 3. `Trafik & Histori Sinyal` gaya mock: judul + "Rentang ..." di kanan, dua kartu
          grafik sejajar lg:grid-cols-2 (menumpuk di bawah lg). Sumber data tetap endpoint
          histori/sinyal yang ada; grafik hanya menggambar sampel yang benar-benar tersimpan. */}
      <section className="entrance rounded-md border bg-surface p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b pb-2.5">
          <h2 className="flex items-center gap-2 text-base font-bold text-fiber"><TitleIcon title="Trafik & Histori Sinyal" />Trafik & Histori Sinyal</h2>
          <span className="font-mono text-xs text-muted">Trafik {RANGE_TITLE[range]} · Sinyal {RANGE_TITLE[srange]}</span>
        </div>
        <div className="stagger grid gap-5 lg:grid-cols-2">
          <ChartCard title={`Trafik ${RANGE_TITLE[range]}`}
            toggle={<RangeToggle value={range} onChange={pickRange("range", setRange)} aria="Rentang histori trafik" />}
            legend={
              <>
                <LegendRow color="bg-fiber" label={`Download maks · rata-rata (${range})`}
                  value={tStats ? `${mbpsId(tStats.downMax)} · ${mbpsId(tStats.downAvg)}` : "—"} />
                <LegendRow color="bg-amber" label={`Upload maks · rata-rata (${range})`}
                  value={tStats ? `${mbpsId(tStats.upMax)} · ${mbpsId(tStats.upAvg)}` : "—"} />
                <LegendRow color="bg-line-strong" label="Sampel dengan laju terbaca"
                  value={tStats ? String(tStats.count) : "0"} />
              </>
            }>
            {/* Sampel counter dikumpulkan sampler worker (job `sample_onu_traffic`, 5 menit
                sekali, 2 bulkwalk per OLT) dan disimpan di `onu_traffic_history`. Halaman
                ini hanya menggambar sampel yang ADA — pesan kosong hanya muncul kalau
                sampelnya memang belum terkumpul. */}
            {trafficHistory.isPending ? (
              <ChartSkeleton />
            ) : trafficHistory.isError ? (
              <ErrorState message="Histori trafik gagal dimuat." onRetry={() => trafficHistory.refetch()} />
            ) : (
              <TrafficHistoryChart points={trafficHistory.data ?? []} />
            )}
          </ChartCard>
          <ChartCard title={`Sinyal ${RANGE_TITLE[srange]}`}
            toggle={<RangeToggle value={srange} onChange={pickRange("srange", setSrange)} aria="Rentang histori sinyal" />}
            legend={
              <>
                <LegendRow color="bg-fiber" label="ONU Rx 1490nm (min · rata-rata · maks)"
                  value={stats
                    ? `${comma(stats.min, 1)} · ${comma(stats.avg, 1)} · ${comma(stats.max, 1)}`
                    : "—"} />
                <LegendRow color="bg-amber" label="OLT Rx 1310nm (min · rata-rata · maks)"
                  value={oltStats
                    ? `${comma(oltStats.min, 1)} · ${comma(oltStats.avg, 1)} · ${comma(oltStats.max, 1)}`
                    : "—"} />
              </>
            }>
            {signal.isPending ? (
              <ChartSkeleton />
            ) : signal.isError ? (
              <ErrorState message="Histori sinyal gagal dimuat." onRetry={() => signal.refetch()} />
            ) : (
              <RxChart points={signal.data ?? []} />
            )}
          </ChartCard>
        </div>
      </section>

      {/* 5. SPEED PROFILE (mock pemilik): 3 kolom, nama profil mono hijau + nama asli
          perangkat kecil abu dalam kurung. */}
      <Section label="Profil Kecepatan" note="Rate-limit QoS" card>
        <div className="mb-2 hidden overflow-x-auto rounded border border-line md:block">
          <table className="w-full table-fixed border-collapse text-left">
            <thead>
              <tr className="border-b border-line bg-sunken text-muted">
                <th className="w-[42%] px-4 py-2.5 font-semibold">Download</th>
                <th className="w-[42%] px-4 py-2.5 font-semibold">Upload</th>
                <th className="w-[16%] px-4 py-2.5 text-center font-semibold">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60">
              <tr className="hover:bg-sunken/40">
                <td className="px-4 py-2.5 font-mono">
                  <span className="font-semibold text-fiber">{dash(d.download_profile_name)}</span>
                  <span className="ml-2 text-xs text-faint">({dash(cleanProfileName(d.line_profile_id))})</span>
                </td>
                <td className="px-4 py-2.5 font-mono">
                  <span className="font-semibold text-fiber">{dash(d.upload_profile_name)}</span>
                  <span className="ml-2 text-xs text-faint">({dash(cleanProfileName(d.srv_profile_id))})</span>
                </td>
                <td className="px-4 py-2.5 text-center">
                  <ConfigureLink label="Konfigurasi profil kecepatan"
                                 onClick={() => setModal({ kind: "speed-profile" })} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-x-3 border bg-surface px-3 py-2 md:hidden">
          <div className="min-w-0">
            <p className="text-xs text-muted">Download</p>
            <p className="truncate font-mono text-fiber">{dash(d.download_profile_name)}</p>
            <p className="truncate font-mono text-xs text-faint">({dash(cleanProfileName(d.line_profile_id))})</p>
          </div>
          <div className="min-w-0 border-l pl-3">
            <p className="text-xs text-muted">Upload</p>
            <p className="truncate font-mono text-fiber">{dash(d.upload_profile_name)}</p>
            <p className="truncate font-mono text-xs text-faint">({dash(cleanProfileName(d.srv_profile_id))})</p>
          </div>
          <div className="col-span-2 mt-1 flex justify-end">
            <ConfigureLink label="Konfigurasi profil kecepatan"
                           onClick={() => setModal({ kind: "speed-profile" })} />
          </div>
        </div>
      </Section>

      {/* 6. Port Ethernet + WiFi sejajar dua kolom (mock pemilik), kartu padat di mobile. */}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <Section label="Port Ethernet" note={specs ? specs.name : undefined} card>
        {specs && specs.eth_ports > 0 ? (
          <>
            <div className="mb-2 hidden overflow-x-auto rounded border border-line md:block">
              <table className="w-full table-fixed border-collapse text-left">
                <thead>
                  <tr className="border-b border-line bg-sunken text-muted">
                    <th className="w-[30%] px-3 py-2 font-semibold">Port</th>
                    <th className="w-[30%] px-3 py-2 font-semibold">Status</th>
                    <th className="w-[20%] px-3 py-2 font-semibold">Mode</th>
                    <th className="w-[20%] px-3 py-2 text-center font-semibold">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60">
                  {Array.from({ length: specs.eth_ports }, (_, i) => {
                    const cfg = d.port_configs?.eth?.[String(i + 1)];
                    return (
                    <tr key={i} className="hover:bg-sunken/40">
                      <td className="px-3 py-2">
                        <span className="font-semibold text-ink">LAN {i + 1}</span>
                        <span className="ml-1.5 font-mono text-xs text-faint">eth_0/{i + 1}</span>
                      </td>
                      <td className="px-3 py-2 text-muted">{cfg ? (cfg.enabled ? "Aktif" : "Nonaktif") : "—"}</td>
                      <td className="px-3 py-2 text-muted">{cfg?.mode ? ({ lan: "LAN", access: "Access", hybrid: "Hybrid", trunk: "Trunk", transparent: "Transparent" } as Record<string, string>)[cfg.mode] ?? cfg.mode : "—"}</td>
                      <td className="px-3 py-2 text-center">
                        <ConfigureLink label={`Konfigurasi eth_0/${i + 1}`}
                                       onClick={() => setModal({ kind: "eth-port", port: i + 1 })} />
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="grid min-w-0 gap-2 md:hidden">
              {Array.from({ length: specs.eth_ports }, (_, i) => {
                const cfg = d.port_configs?.eth?.[String(i + 1)];
                return (
                <article key={i} className="min-w-0 border bg-surface px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="min-w-0 grow">
                      <p className="font-semibold text-ink">LAN {i + 1}</p>
                      <p className="truncate font-mono text-xs text-muted">eth_0/{i + 1}</p>
                    </div>
                    <ConfigureLink label={`Konfigurasi eth_0/${i + 1}`}
                                   onClick={() => setModal({ kind: "eth-port", port: i + 1 })} />
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-2 text-xs">
                    <p><span className="text-muted">Status</span><br />{cfg ? (cfg.enabled ? "Aktif" : "Nonaktif") : "—"}</p>
                    <p><span className="text-muted">Mode</span><br />{cfg?.mode ? ({ lan: "LAN", access: "Access", hybrid: "Hybrid", trunk: "Trunk", transparent: "Transparent" } as Record<string, string>)[cfg.mode] ?? cfg.mode : "—"}</p>
                  </div>
                </article>
                );
              })}
            </div>
            <span className="inline-block rounded border border-line bg-sunken px-2 py-0.5 text-xs text-muted">
              {d.port_configs?.eth && Object.keys(d.port_configs.eth).length > 0 ? "Terakhir ditulis Nexfiber" : "Belum dibaca dari OLT"}
            </span>
          </>
        ) : (
          <span className="text-muted">
            {specs ? "Tidak ada port Ethernet" : "Tipe ONU belum terdaftar di ONU Types."}
          </span>
        )}
      </Section>

      <Section label="WiFi (WLAN)" note={specs ? `${specs.wifi_ssids} SSID` : undefined} card>
        {specs && specs.wifi_ssids > 0 ? (
          <>
            <div className="mb-2 hidden overflow-x-auto rounded border border-line md:block">
              <table className="w-full table-fixed border-collapse text-left">
                <thead>
                  <tr className="border-b border-line bg-sunken text-muted">
                    <th className="w-[40%] px-3 py-2 font-semibold">Radio</th>
                    <th className="w-[40%] px-3 py-2 font-semibold">Status</th>
                    <th className="w-[20%] px-3 py-2 text-center font-semibold">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60">
                  {Array.from({ length: specs.wifi_ssids }, (_, i) => {
                    const cfg = d.port_configs?.wifi?.[String(i + 1)];
                    return (
                    <tr key={i} className="hover:bg-sunken/40">
                      <td className="px-3 py-2">
                        <span className="font-semibold text-ink">SSID {i + 1}</span>
                        <span className="ml-1.5 font-mono text-xs text-faint">wifi_0/{i + 1}</span>
                      </td>
                      <td className="px-3 py-2 text-muted">{cfg ? (cfg.enabled ? "Aktif" : "Nonaktif") + (cfg.ssid ? ` · ${cfg.ssid}` : "") : "—"}</td>
                      <td className="px-3 py-2 text-center">
                        <ConfigureLink label={`Konfigurasi wifi_0/${i + 1}`}
                                       onClick={() => setModal({ kind: "wifi-port", port: i + 1 })} />
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="grid min-w-0 gap-2 md:hidden">
              {Array.from({ length: specs.wifi_ssids }, (_, i) => {
                const cfg = d.port_configs?.wifi?.[String(i + 1)];
                return (
                <article key={i} className="min-w-0 border bg-surface px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="min-w-0 grow">
                      <p className="font-semibold text-ink">SSID {i + 1}</p>
                      <p className="truncate font-mono text-xs text-muted">wifi_0/{i + 1}</p>
                    </div>
                    <ConfigureLink label={`Konfigurasi wifi_0/${i + 1}`}
                                   onClick={() => setModal({ kind: "wifi-port", port: i + 1 })} />
                  </div>
                  <p className="mt-1 text-xs"><span className="text-muted">Status</span><br />{cfg ? (cfg.enabled ? "Aktif" : "Nonaktif") + (cfg.ssid ? ` · ${cfg.ssid}` : "") : "—"}</p>
                </article>
                );
              })}
            </div>
            <span className="inline-block rounded border border-line bg-sunken px-2 py-0.5 text-xs text-muted">
              {d.port_configs?.wifi && Object.keys(d.port_configs.wifi).length > 0 ? "Terakhir ditulis Nexfiber" : "Perlu TR-069"}
            </span>
          </>
        ) : (
          <span className="text-muted">
            {specs ? "Tidak ada SSID WiFi" : "Tipe ONU belum terdaftar di ONU Types."}
          </span>
        )}
        </Section>
      </div>

      {/* 7. Layanan Tambahan (mock pemilik): VoIP/CATV hanya nilai nyata dari katalog ONU
          Types; yang tidak didukung tipe ONUnya ditulis miring redup, yang backend-nya
          belum ada diberi lencana "Segera", tidak dikarang. */}
      <Section label="Layanan Tambahan" card>
        <div className="flex flex-col">
          <DRow label="Layanan VoIP" value={
            specs
              ? (specs.voip_ports > 0
                  ? `${specs.voip_ports} port`
                  : <span className="text-faint italic">Tidak didukung tipe ONU</span>)
              : <span className="text-faint">Tipe ONU belum terdaftar</span>
          } onEdit={specs && specs.voip_ports > 0
            ? () => setModal({ kind: "voip-enable", port: 1 })
            : undefined} />
          <DRow label="IPTV" value={
            <span className="inline-flex items-center rounded border border-amber/30 bg-amber/10 px-2 py-0.5 text-xs font-medium text-amber">
              Segera
            </span>
          } onEdit={() => setModal({ kind: "iptv" })} />
          <DRow label="CATV" value={
            specs?.catv
              ? <span className="text-up">Didukung</span>
              : specs
                ? <span className="text-faint italic">Tidak didukung tipe ONU</span>
                : <span className="text-faint">Tipe ONU belum terdaftar</span>
          } />
        </div>
      </Section>

      {/* 8. Aksi ONU (mock pemilik): dua panel sejajar, rutin vs destruktif. Semua tetap
          membuka modal konfirmasi yang sudah ada (payload/endpoint tidak berubah), tombol
          merusak tetap manager-only. "Log aksi terakhir" = pop up dari tombol di kepala
          section, entri menaut ke `/logs?q=<serial>`. */}
      <Section label="Aksi ONU" card id="aksi-onu" action={<LastLogPopover query={logs} serial={d.serial_number} />}>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="flex flex-col justify-between rounded-md border bg-sunken/20 p-3.5">
            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-muted">Aksi Operasional</span>
                <span className="font-mono text-xs text-faint">Rutin &amp; sinkronisasi</span>
              </div>
              <p className="mb-3 text-xs text-faint">
                Tindakan pemeliharaan standar tanpa menghapus profil langganan pelanggan.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-line/60 pt-2"
                 aria-label="Aksi operasional">
              <Button className="min-h-11 grow sm:grow-0" size="sm" variant="secondary"
                      onClick={() => setModal({ kind: "reboot" })}>
                Reboot
              </Button>
              <Button className="min-h-11 grow sm:grow-0" size="sm" variant="secondary"
                      onClick={() => setModal({ kind: "resync-config" })}>
                Resync config
              </Button>
              {isManager && (
                <Button className="min-h-11 grow sm:grow-0" size="sm" variant="secondary"
                        onClick={() => setModal({ kind: "move" })}>
                  Pindah PON
                </Button>
              )}
            </div>
          </div>
          <div className="flex flex-col justify-between rounded-md border border-down p-3.5">
            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-down">Aksi Destruktif</span>
                <span className="rounded border border-down px-1.5 py-0.5 text-xs font-semibold text-down">
                  Zona Kritis
                </span>
              </div>
              <p className="mb-3 text-xs text-faint">
                Operasi dapat memutus layanan Internet dan mereset konfigurasi ONU.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-line/60 pt-2"
                 aria-label="Aksi destruktif">
              <Button className="min-h-11 grow sm:grow-0" size="sm"
                      variant={d.admin_state === "disabled" ? "secondary" : "danger"}
                      onClick={() => setModal({ kind: d.admin_state === "disabled" ? "enable" : "disable" })}>
                {d.admin_state === "disabled" ? "Aktifkan ONU" : "Nonaktifkan ONU"}
              </Button>
              {isManager && (
                <Button className="min-h-11 grow sm:grow-0" size="sm" variant="danger"
                        onClick={() => setModal({ kind: "restore-factory" })}>
                  Restore default
                </Button>
              )}
              {isManager && (
                <Button className="min-h-11 grow sm:grow-0" size="sm" variant="danger"
                        onClick={() => setModal({ kind: "delete" })}>
                  Hapus
                </Button>
              )}
            </div>
          </div>
        </div>
      </Section>

      {/* Bar aksi sticky mobile-only: hanya aksi rutin (Reboot, Resync config) +
          anchor ke section Aksi penuh. Aksi destruktif TIDAK PERNAH di bar ini.
          Desktop tidak berubah (bar md:hidden). */}
      <div className="fixed inset-x-0 bottom-0 z-40 flex items-center gap-2 border-t bg-surface px-3 py-2 md:hidden">
        <Button className="grow" size="sm" variant="secondary"
                onClick={() => setModal({ kind: "reboot" })}>
          Reboot
        </Button>
        <Button className="grow" size="sm" variant="secondary"
                onClick={() => setModal({ kind: "resync-config" })}>
          Resync config
        </Button>
        <a href="#aksi-onu" className="flex min-h-11 shrink-0 items-center px-1 text-sm font-medium text-fiber hover:underline">
          Semua aksi
        </a>
      </div>

      {/* Semua modal aksi ONU dirender satu kali di sini; isinya dipilih oleh `modal`. */}
      <OnuActionModals state={modal} onu={modalOnu} onClose={() => setModal(null)}
                       onDone={(kind, r) => {
                         // Setelah Hapus sukses, ONU tidak ada lagi: refetch detail hanya
                         // akan jadi ErrorState 404, jadi pergi ke daftar Configured.
                         // Setelah Replace-SN lewat URL serial, URL lama juga tidak ketemu
                         // lagi — ID numerik tidak berubah, jadi itu URL yang benar.
                         if (kind === "delete") { navigate("/configured"); return; }
                         if (kind === "replace-sn" && d.id != null) { navigate(`/onu/${d.id}`); return; }
                         setNote(r?.detail ?? `Aksi ${kind} terkirim.`);
                       }} />
      {vlanPrimerOpen && onu.data && (
        <PrimaryVlanModal serial={onu.data.serial_number} oltId={onu.data.olt_id}
                          currentVlanId={onu.data.vlan_id}
                          onClose={() => setVlanPrimerOpen(false)} onDone={setNote} />
      )}
    </div>
  );
}
