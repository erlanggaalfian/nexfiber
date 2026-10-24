import type { ReactNode } from "react";
import { Button } from "./ui/button";

const ONU_STATUS: Record<string, [string, string]> = {
  online: ["Online", "bg-up"],
  offline: ["Offline", "bg-down"],
  los: ["LOS", "bg-down"],
  dying_gasp: ["Dying Gasp", "bg-down"],
  power_off: ["Mati listrik", "bg-down"],
  unknown: ["Belum diketahui", "bg-idle"],
  unreachable: ["Tak terjangkau", "bg-down"],
};

export function StatusBadge({ status, compact = false }: { status: string; compact?: boolean }) {
  const [label, dot] = ONU_STATUS[status] ?? [status, "bg-idle"];
  return (
    <span className="inline-flex items-center gap-1.5" title={label}>
      <span className={`size-1.5 shrink-0 ${dot}`} aria-hidden />
      <span className={compact ? "sr-only" : ""}>{label}</span>
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

export function SignalBar({ dbm, big = false }: { dbm: number | null; big?: boolean }) {
  const b = rxBucket(dbm);
  const { segments, color, label } = b ? RX_BUCKETS[b] : { segments: 0, color: "", label: "LOS" };
  return (
    <span className="inline-flex items-center gap-2 font-mono" title={label}>
      <span className="flex w-12 gap-px" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={`h-1 flex-1 ${i < segments ? color : "bg-sunken"}`} />
        ))}
      </span>
      <span className={big ? "text-metric font-semibold" : ""}>{dbm === null ? "LOS" : dbm.toFixed(1)}</span>
      {big && dbm !== null && <span className="text-sm text-muted">dBm</span>}
    </span>
  );
}

export function Panel({ title, action, children, className = "" }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-md border bg-surface ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-2 border-b px-4 py-2">
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
    <div className="mb-3 flex min-h-12 flex-wrap items-center justify-between gap-2">
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
        <div key={i} className="mb-1 h-8 bg-sunken" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3 p-4" role="alert">
      <p className="text-down">{message}</p>
      {onRetry && <Button onClick={onRetry}>Coba lagi</Button>}
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
