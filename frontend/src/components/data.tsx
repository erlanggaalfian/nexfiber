import type { ReactNode } from "react";
import type { Thresholds } from "../lib/api";
import { Button } from "./ui/button";

export const DEFAULT_RX: Thresholds = { warn: -25, crit: -27 };

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

/** DESIGN.md Rx buckets: normal -8..-25, warn below -25..-27, bad below -27 or above -8. */
export function rxBucket(dbm: number | null, t: Thresholds): "up" | "warn" | "down" | null {
  if (dbm === null) return null;
  if (dbm > -8 || dbm < t.crit) return "down";
  if (dbm < t.warn) return "warn";
  return "up";
}

const BAR = { up: [3, "bg-up"], warn: [2, "bg-warn"], down: [1, "bg-down"] } as const;

export function SignalBar({ dbm, t = DEFAULT_RX, big = false }: { dbm: number | null; t?: Thresholds; big?: boolean }) {
  const b = rxBucket(dbm, t);
  const [filled, color] = b ? BAR[b] : [0, ""];
  return (
    <span className="inline-flex items-center gap-2 font-mono">
      <span className="flex w-12 gap-px" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={`h-1 flex-1 ${i < filled ? color : "bg-sunken"}`} />
        ))}
      </span>
      <span className={big ? "text-metric font-semibold" : ""}>{dbm === null ? "—" : dbm.toFixed(1)}</span>
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

const timeFmt = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit" });
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
