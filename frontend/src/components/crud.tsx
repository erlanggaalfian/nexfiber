/** Shared list+drawer CRUD bits for the Settings pages (DESIGN 12.8: judul + tambah, filter, tabel,
 *  drawer kanan 480px, hapus = dialog konfirmasi kecil). Satu sumber supaya tiap halaman tidak
 *  menulis ulang markup yang sama.
 */
import { CaretDown, X } from "@phosphor-icons/react";
import { Popover } from "radix-ui";
import type { ReactNode } from "react";
import { useState } from "react";
import { DONE, useJob } from "../lib/jobs";
import { ConfirmShell, DrawerShell } from "./onu/modals/ModalShell";
import { Empty, ErrorState, Skeleton } from "./data";
import { Button } from "./ui/button";

export const input = "h-8 w-full rounded-sm border border-line-strong bg-surface px-2 text-sm";
export const cell = "px-3 py-2 text-left align-middle";
export const filterInput =
  "h-8 rounded-sm border border-line-strong bg-surface px-2 text-sm placeholder:text-faint";

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-down">{error}</span>}
    </label>
  );
}

export function Drawer({ title, onClose, onSubmit, busy, error, children }: {
  title: string; onClose: () => void; onSubmit: () => void; busy?: boolean; error?: string;
  children: ReactNode;
}) {
  return (
    <DrawerShell title={title} onClose={onClose} onSubmit={onSubmit} busy={busy} error={error}>
      {children}
    </DrawerShell>
  );
}

export function Confirm({ title, body, action, onConfirm, onClose, error, busy, children }: {
  title: string; body: string; action: string; onConfirm: () => void; onClose: () => void;
  error?: string; busy?: boolean; children?: ReactNode;
}) {
  return (
    <ConfirmShell title={title} body={body} action={action} onConfirm={onConfirm}
                  onClose={onClose} error={error} busy={busy}>
      {children}
    </ConfirmShell>
  );
}

/** Jejak CLI satu aksi push ke OLT: perintah yang dikirim + respons mentah perangkat.
 *  Hanya untuk sesi saat ini (hilang saat drawer/dialog ditutup) — histori permanen tetap
 *  di halaman Logs. Dipakai tab VLANs dan Interfaces, jangan tulis ulang per halaman.
 */
export function JobTrace({ jobId }: { jobId: number | null }) {
  const { data: job } = useJob(jobId);
  if (jobId === null) return null;
  const trace = (job?.result as { debug_log?: { command?: string; output?: string } } | null)
    ?.debug_log;
  const done = job ? DONE.has(job.status) : false;
  const failed = job?.status === "failed";
  return (
    <div className={`mt-3 rounded-sm border px-3 py-2 text-xs ${failed ? "border-down" : ""}`}>
      <p className={failed ? "text-down" : "text-muted"}>
        Job #{jobId}: {job?.status ?? "menunggu"}
        {job?.error_message ? ` — ${job.error_message}` : ""}
      </p>
      {trace ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-muted hover:text-ink">Jejak CLI</summary>
          <pre className="mt-1 max-h-48 overflow-auto bg-sunken p-2 font-mono whitespace-pre-wrap">
            {`$ ${trace.command ?? "—"}\n${trace.output ?? ""}`.trim()}
          </pre>
        </details>
      ) : (
        done && <p className="mt-1 text-faint">Tidak ada jejak CLI untuk job ini.</p>
      )}
    </div>
  );
}

/** Panel tabel + state memuat/gagal/kosong, dipakai semua tabel Settings. */
export function TableCard<T>({ query, columns, empty, row, loadingText }: {
  query: { isPending: boolean; isError: boolean; error: Error | null; data?: T[]; refetch: () => void };
  columns: string[];
  empty: string;
  row: (item: T) => ReactNode;
  loadingText: string;
}) {
  const rows = query.data ?? [];
  return (
    <section className="entrance rounded-md border bg-surface">
      {query.isPending ? (
        <Skeleton text={loadingText} rows={4} />
      ) : query.isError ? (
        <ErrorState message={query.error?.message ?? "Gagal memuat"} onRetry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <Empty>{empty}</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="text-xs text-muted">
              <tr className="border-b">{columns.map((c) => <th key={c} className={cell}>{c}</th>)}</tr>
            </thead>
            <tbody>{rows.map(row)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Pola "5/8" + bar 48x4 (DESIGN 12.8), sama seperti signal bar. */
export function UsageBar({ used, capacity }: { used: number; capacity: number | null }) {
  const pct = capacity ? Math.min(used / capacity, 1) * 100 : 0;
  return (
    <span className="inline-flex items-center gap-2 font-mono">
      <span className="flex h-1 w-12 bg-sunken" aria-hidden>
        <span className={`h-1 ${pct >= 100 ? "bg-down" : "bg-fiber"}`} style={{ width: `${pct}%` }} />
      </span>
      {used}/{capacity ?? "—"}
    </span>
  );
}

/** Filter multi-pilih DESIGN 12.5: tombol kecil yang jadi "Status · 2" saat aktif,
 *  isinya checkbox. Dipakai semua filter tabel Configured supaya tidak ada tujuh
 *  variasi dropdown yang ditulis tangan. Kotak cari muncul sendiri saat pilihan
 *  lebih dari SEARCH_MIN — jadi tiap filter panjang (OLT/zone/splitter/VLAN)
 *  tersaring tanpa logic pencarian ditulis ulang di halaman.
 */
const SEARCH_MIN = 8;

export function MultiFilter({ label, options, value, onChange }: {
  label: string;
  options: { value: string; label: string }[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [q, setQ] = useState("");
  const toggle = (v: string) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  const needle = q.trim().toLowerCase();
  const shown = needle ? options.filter((o) => o.label.toLowerCase().includes(needle)) : options;
  return (
    <Popover.Root onOpenChange={(o) => !o && setQ("")}>
      <Popover.Trigger asChild>
        <Button size="sm" aria-label={`Filter ${label}`}>
          {value.length ? `${label} · ${value.length}` : label}
          <CaretDown size={12} aria-hidden />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={4}
          className="z-50 flex max-h-72 w-56 flex-col rounded-md border bg-surface p-2 shadow-modal data-[state=open]:animate-[fade-in_150ms_ease-out]"
        >
          {options.length > SEARCH_MIN && (
            <input
              className={`${input} mb-1`}
              placeholder="Cari ..."
              aria-label={`Cari ${label}`}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          )}
          <div className="min-h-0 flex-1 overflow-y-auto">
            {shown.length === 0 && (
              <p className="p-1 text-muted">{options.length === 0 ? "Belum ada pilihan" : "Tidak cocok"}</p>
            )}
            {shown.map((o) => (
              <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 hover:bg-sunken">
                <input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} />
                <span className="truncate">{o.label}</span>
              </label>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Chip filter aktif (DESIGN 12.5): "Status: Offline ✕". */
export function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border bg-sunken px-2 py-0.5 text-xs">
      {label}
      <button type="button" onClick={onRemove} aria-label={`Hapus filter ${label}`} className="text-muted hover:text-ink">
        <X size={10} aria-hidden />
      </button>
    </span>
  );
}
