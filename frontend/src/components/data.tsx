import { Globe, GlobeX, LinkBreak, Plug, Power, Prohibit, Question, Warning } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Button } from "./ui/button";

/** Satu-satunya peta status -> ikon/warna/label untuk seluruh aplikasi (AGENTS "DRY").
 *  Kunci = nilai enum backend: onus.status (online/offline/los/dying_gasp/power_off/
 *  unknown), onus.admin_state "disabled", dan olts.status (online/offline/unreachable).
 *  Warna BUKAN satu-satunya pembeda: bentuk ikon berbeda per status DAN label teks
 *  tampil di samping ikon secara default (withLabel=true) — title/sr-only hanya
 *  pelengkap, bukan satu-satunya pembawa label. Pasangan yang dulu duplikat ikon
 *  kini dibedakan: offline GlobeX vs unreachable Warning, dying_gasp Plug vs
 *  power_off Power (Power dari paket @phosphor-icons/react yang sama, bukan
 *  dependensi baru; ikon lain di peta ini sudah dipakai proyek). */
const ONU_STATUS: Record<string, [label: string, icon: Icon, color: string]> = {
  online: ["Online", Globe, "text-up"],
  offline: ["Offline", GlobeX, "text-down"],
  los: ["LOS — kabel/serat putus", LinkBreak, "text-down"],
  dying_gasp: ["Dying Gasp — listrik pelanggan mati", Plug, "text-down"],
  power_off: ["Mati listrik", Power, "text-down"],
  disabled: ["Dinonaktifkan operator", Prohibit, "text-idle"],
  unknown: ["Belum diketahui", Question, "text-idle"],
  unreachable: ["Tak terjangkau", Warning, "text-down"],
};

/** `reason` dipakai saat ada keterangan tambahan dari perangkat (mis. last_down_reason):
 *  ikut masuk tooltip + label pembaca layar, tidak mengubah ikon. */
export function StatusBadge(
  { status, reason, withLabel = true }:
  { status: string; reason?: string | null; withLabel?: boolean },
) {
  const [label, Ikon, color] = ONU_STATUS[status] ?? ["Belum diketahui", Question, "text-idle"];
  const full = reason ? `${label} (${reason})` : label;
  return (
    <span className={`inline-flex items-center gap-1.5 ${color}`} title={full}>
      <Ikon size={18} aria-hidden />
      <span className={withLabel ? "" : "sr-only"}>{full}</span>
    </span>
  );
}

export type RxBucket = "good" | "fair" | "weak" | "critical";

/** PRD 3.4.2 / DESIGN 3 (c3): one bucket rule everywhere. null = LOS / no reading.
 *  Batasnya WAJIB sama dengan rx_bucket() di backend/app/core/signal.py (filter tabel
 *  Configured + export CSV dihitung di server) — kalau salah satu diubah, ubah keduanya. */
export function rxBucket(dbm: number | null): RxBucket | null {
  if (dbm === null) return null;
  if (dbm > -8 || dbm <= -28) return "critical";
  if (dbm < -27) return "weak";
  if (dbm < -25) return "fair";
  return "good";
}

export const RX_BUCKETS: Record<RxBucket, { label: string; segments: number; color: string }> = {
  critical: { label: "Critical", segments: 1, color: "bg-down" },
  weak: { label: "Weak", segments: 1, color: "bg-warn" },
  fair: { label: "Fair", segments: 2, color: "bg-warn" },
  good: { label: "Good", segments: 3, color: "bg-up" },
};

/* Varian `big` SignalBar sudah dihapus: grep membuktikan tidak ada caller yang
 *  memakai big=true (hanya Configured yang memanggil, tanpa big). Pola sinyal
 *  besar adalah RxBox di OnuDetail — itu dokumentasi untuk DESIGN.md, bukan kode
 *  di sini (OnuDetail bukan file tahap ini). */
export function SignalBar({ dbm }: { dbm: number | null }) {
  const b = rxBucket(dbm);
  const { segments, color, label } = b ? RX_BUCKETS[b] : { segments: 0, color: "", label: "LOS" };
  return (
    <span className="inline-flex items-center gap-2 font-mono" title={label}>
      <span className="flex w-12 gap-px" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={`h-1 flex-1 transition-colors duration-300 ease-out motion-reduce:transition-none ${i < segments ? color : "bg-sunken"}`} />
        ))}
      </span>
      <span>{dbm === null ? "LOS" : dbm.toFixed(1)}</span>
    </span>
  );
}

/** SATU bar bersama (DRY): dipakai UsageBar (crud.tsx) dan OltSyncProgress.
 *  `pct` = persen 0–100 (dipotong di sini), `tone` = kelas warna isi, `className`
 *  = lebar track (w-12 untuk UsageBar, w-24 untuk sinkron). Transisi lebar 300ms
 *  yang sama di semua pemakai, dimatikan oleh prefers-reduced-motion. */
export function Bar({ pct, tone = "bg-fiber", className = "w-12" }: { pct: number; tone?: string; className?: string }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <span className={`flex h-1 ${className} bg-sunken`} aria-hidden>
      <span className={`h-1 transition-[width] duration-300 ease-out motion-reduce:transition-none ${tone}`} style={{ width: `${clamped}%` }} />
    </span>
  );
}

/* Header Panel = header sub-panel (uppercase text-xs muted), sengaja BERBEDA dari
 *  header section halaman (Block/Section di OnuDetail, base bold fiber) — dua level
 *  itu punya pekerjaan berbeda, jadi tidak disatukan. Panel punya padding default
 *  p-4; caller yang memberi className sendiri tetap di-append terakhir. Perhatian
 *  untuk verifikasi visual parent: tidak ada caller Panel yang memberi padding
 *  berbeda, jadi p-4 ini berlaku ke semua Panel termasuk yang di OltDetail yang
 *  isinya sudah px-4 sendiri (Row) — tampilannya perlu dicek, bukan diasumsikan. */
export function Panel({ title, action, children, className = "" }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`entrance rounded-lg border border-line/60 bg-surface p-4 shadow-xs ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-2 pb-2">
          <h2 className="text-xs font-medium uppercase tracking-[0.02em] text-muted">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/** DESIGN 11 title row. On mobile the top bar already shows the title, so h1 is visually hidden there. */
export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-3 flex min-h-12 flex-wrap items-center justify-between gap-2 max-lg:mb-0 max-lg:min-h-0">
      <h1 className="text-xl font-semibold max-lg:sr-only">{title}</h1>
      {children && <div className="flex items-center gap-2 max-lg:ml-auto">{children}</div>}
    </div>
  );
}

export function Skeleton({ rows = 3, text }: { rows?: number; text: string }) {
  return (
    <div className="p-4" aria-busy>
      <p className="mb-2 text-muted">{text}</p>
      {Array.from({ length: Math.min(rows, 8) }, (_, i) => (
        /* h-[42px]: setinggi baris tabel asli (§5/§8) supaya tinggi kartu tidak
           berubah saat data datang. Semua pemakai Skeleton adalah konteks
           tabel/daftar, jadi aman sebagai default global. */
        <div key={i} className="mb-1 h-[42px] rounded-sm bg-sunken" />
      ))}
    </div>
  );
}

/** Skeleton khusus kartu grafik: bentuknya meniru grafik (blok tinggi + baris
 *  sumbu tipis), bukan bar generik — jadi kartu tidak melompat tinggi/bentuk
 *  saat data datang. Tanpa pulse/shimmer (dilarang DESIGN.md). Pemakaian di
 *  kartu grafik OnuDetail bukan file tahap ini, jadi tidak diganti di sini. */
export function ChartSkeleton() {
  return (
    <div className="p-4" aria-busy>
      <div className="h-36 rounded-md border border-line/40 bg-sunken/20" />
      <div className="mt-2 h-1 rounded-sm bg-sunken/20" />
    </div>
  );
}

export function ErrorState({ message, cause, onRetry }: { message: string; cause?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3 p-4" role="alert">
      <p className="text-down">{message}</p>
      {onRetry && <Button onClick={onRetry}>Coba lagi</Button>}
      {cause && <p className="w-full text-xs text-muted">{cause}</p>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-3 p-4 text-muted">{children}</div>;
}

// en-GB gives HH:MM with a colon; id-ID would print 19.15.
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat("id-ID", { dateStyle: "short", timeStyle: "short" });

export const fmtTime = (iso: string | null) => (iso ? timeFmt.format(new Date(iso)) : "—");
export const fmtDateTime = (iso: string | null) => (iso ? dateTimeFmt.format(new Date(iso)) : "—");

export function fmtAgo(iso: string | null) {
  if (!iso) return "—";
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 60) return `${Math.max(m, 0)}m`;
  if (m < 1440) return `${Math.floor(m / 60)}j`;
  return `${Math.floor(m / 1440)}h`;
}

export const nf = new Intl.NumberFormat("id-ID");
