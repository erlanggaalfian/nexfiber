/** Shared list+dialog CRUD bits for the Settings pages (DESIGN 12.8: judul + tambah, filter, tabel,
 *  form edit = dialog tengah seperti modal, hapus = dialog konfirmasi kecil). Satu sumber supaya tiap halaman tidak
 *  menulis ulang markup yang sama.
 */
import { CaretDown, X } from "@phosphor-icons/react";
import { Popover } from "radix-ui";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { DONE, useJob } from "../lib/jobs";
import { ConfirmShell, DrawerShell } from "./onu/modals/ModalShell";
import { Bar, Empty, ErrorState, Skeleton } from "./data";
import { Button } from "./ui/button";

/* SATU tinggi form di seluruh aplikasi (DESIGN §8: kontrol default 32px):
   crud.input dan ModalShell.field memakai nilai yang sama persis; di bawah
   768px naik ke 48px (target sentuh DESIGN §9). min-w-0 mencegah input
   meluber di grid sempit (mis. lat/long AuthorizeOnu). */
export const input =
  "h-8 max-md:h-12 w-full min-w-0 rounded-md border border-line-strong bg-surface px-3 text-sm";
/* Dipertahankan untuk halaman yang masih memakainya; TableCard sendiri tidak
   lagi memakai token ini — padding selnya diatur .tbl di index.css. */
export const cell = "px-3 py-2 text-left align-middle";
export const filterInput =
  "h-8 max-md:h-12 min-w-0 rounded-md border border-line-strong bg-surface px-3 text-sm placeholder:text-faint";

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-down">{error}</span>}
    </label>
  );
}

export function Drawer({ title, onClose, onSubmit, busy, error, dirty, children }: {
  title: string; onClose: () => void; onSubmit: () => void; busy?: boolean; error?: string;
  dirty?: boolean; children: ReactNode;
}) {
  return (
    <DrawerShell title={title} onClose={onClose} onSubmit={onSubmit} busy={busy} error={error} dirty={dirty}>
      {children}
    </DrawerShell>
  );
}

export function Confirm({ title, body, action, onConfirm, onClose, error, busy, dirty, children }: {
  title: string; body: string; action: string; onConfirm: () => void; onClose: () => void;
  error?: string; busy?: boolean; dirty?: boolean; children?: ReactNode;
}) {
  return (
    <ConfirmShell title={title} body={body} action={action} onConfirm={onConfirm}
                  onClose={onClose} error={error} busy={busy} dirty={dirty}>
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
          <pre className="mt-1 max-h-48 overflow-auto border border-line bg-surface p-2 font-mono whitespace-pre-wrap">
            {`$ ${trace.command ?? "—"}\n${trace.output ?? ""}`.trim()}
          </pre>
        </details>
      ) : (
        done && <p className="mt-1 text-faint">Tidak ada jejak CLI untuk job ini.</p>
      )}
    </div>
  );
}

/** Kartu mobile DESIGN §12.10 (maks 3 baris: identitas+status, mono redup,
 *  angka penentu keputusan; min 72px, gap 8px, tanpa shadow). Pola yang sama
 *  dipakai semua `card` di bawah supaya kartu HP tidak ditulis ulang per halaman
 *  dengan struktur berbeda-beda. */
export function MobileCard({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  const cls = "min-h-[72px] rounded-lg border border-line/60 bg-surface px-3 py-2 shadow-xs";
  /* Bukan <button>: satu-satunya MobileCard yang bisa diklik (Configured) berisi
   *  checkbox di dalamnya, jadi <button> akan menelankan konten interaktif dan
   *  berisiko merusak checkbox itu. Sebagai gantinya: role + tabIndex + keyboard
   *  Enter/Space, dengan tampilan dan press yang sama persis. */
  const onKeyDown = onClick
    ? (e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); }
      }
    : undefined;
  return onClick ? (
    <article onClick={onClick} onKeyDown={onKeyDown} role="button" tabIndex={0} className={`${cls} cursor-pointer transition-transform duration-150 ease-out motion-reduce:transition-none active:scale-[0.99]`}>{children}</article>
  ) : (
    <article className={cls}>{children}</article>
  );
}

/** Panel tabel + state memuat/gagal/kosong, dipakai semua tabel Settings.
 *  `card` (opsional): bila diisi, di bawah 768px tabel diganti daftar kartu
 *  DESIGN §12.10 dan tabel hanya tampil di md ke atas; tanpa `card`, tabel
 *  tetap scroll horizontal di dalam container (bukan di level halaman). */
/** Kolom tabel: string polos, atau objek bila header butuh node sendiri
 *  (mis. checkbox select-all) atau class sembunyi di bawah 1280px — class yang
 *  sama wajib dipakai di <td> halaman itu, karena <th> dirender TableCard. */
export type TableColumn = string | { label: string; className?: string; header?: ReactNode };

/* Windowing TableCard (DESIGN "Virtualisasi wajib di atas 200 baris"):
 *  ambang dihitung dari baris yang benar-benar ter-mount, bukan dari jumlah
 *  data: TableCard me-mount DUA cabang (kartu mobile + baris tabel, satu
 *  disembunyikan CSS) sehingga 100 baris data = 200 baris ter-render. Di atas
 *  ambang itu hanya 50 baris pertama yang dirender, lalu sentinel di ujung
 *  section (IntersectionObserver, rootMargin 600px) menambah 50 baris tiap
 *  kali pengguna mendekati ujung — tanpa library baru, tanpa tinggi baris
 *  tetap (kartu mobile tingginya variabel, jadi virtualisasi posisi-absolut
 *  dengan tinggi estimasi akan melompat saat estimasi meleset).
 *  Yang sengaja TIDAK berubah: thead (termasuk checkbox select-all) selalu
 *  dirender penuh, urutan/sortir tetap dari server, filter di luar TableCard,
 *  dan kolom hidden di bawah 1280px tetap dari class halaman. `shown` tidak
 *  di-reset saat data berubah (mis. auto-refresh 60 detik): me-reset akan
 *  melipat daftar saat pengguna sedang scroll dalam; slice memotong sendiri
 *  bila data menyusut, dan bila filter berubah daftar baru tetap tampil penuh
 *  bila di bawah ambang. Tanpa IntersectionObserver (browser sangat lama)
 *  tampil tombol "Muat baris lagi" sebagai fallback — di browser modern
 *  tombol ini tidak pernah muncul. */
const TABLE_WINDOW_AT = 100;
const TABLE_CHUNK = 50;

export function TableCard<T>({ query, columns, empty, emptyAction, row, card, loadingText }: {
  query: { isPending: boolean; isError: boolean; error: Error | null; data?: T[]; refetch: () => void };
  columns: TableColumn[];
  empty: string;
  emptyAction?: ReactNode;
  row: (item: T) => ReactNode;
  card?: (item: T) => ReactNode;
  loadingText: string;
}) {
  const rows = query.data ?? [];
  const windowing = rows.length > TABLE_WINDOW_AT;
  const [shown, setShown] = useState(TABLE_CHUNK);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const shownRows = windowing ? rows.slice(0, shown) : rows;
  useEffect(() => {
    if (!windowing) return;
    const el = sentinelRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setShown((s) => Math.min(s + TABLE_CHUNK, rows.length));
      }
    }, { rootMargin: "600px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [windowing, rows.length]);
  return (
    <section className="entrance rounded-lg border border-line/60 bg-surface shadow-xs">
      {query.isPending ? (
        <Skeleton text={loadingText} rows={4} />
      ) : query.isError ? (
        <ErrorState message={query.error?.message ?? "Gagal memuat"} onRetry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <Empty>{empty}{emptyAction}</Empty>
      ) : (
        <>
          {card && (
            <div className="grid gap-2 p-2 md:hidden">{shownRows.map(card)}</div>
          )}
          <div className={`overflow-x-auto ${card ? "hidden md:block" : ""}`}>
            <table className="tbl tbl--sticky">
              {/* Padding/garis/hover tabel diatur di bagian TABEL TERPUSAT
               *  di frontend/src/styles/index.css — itu sumber kebenarannya,
               *  jangan menulis ulang bg, padding, atau border di
               *  <table>/<th> di sini. Header tabel sengaja TIDAK sticky
               *  (putusan user 2026-10-29: konten tidak boleh tertutup
               *  header; sticky + pembungkus overflow-x selalu rusak di satu
               *  browser, laporan 2026-10-28/29). thead hanya pembungkus
               *  tanpa class dan <tr> header sengaja tanpa border. Tabel
               *  memakai border-separate, dan garis digambar lewat sel karena
               *  border di <tr> diabaikan di model itu. Jangan kembalikan ke
               *  border-collapse. Class per kolom (col.className) tetap
               *  dipertahankan apa adanya di tiap <th>. */}
              <thead>
                <tr>{columns.map((c, i) => {
                  const col = typeof c === "string" ? { label: c } : c;
                  return <th key={col.label || i} scope="col" className={col.className ?? ""}>{col.header ?? col.label}</th>;
                })}</tr>
              </thead>
              <tbody>{shownRows.map(row)}</tbody>
            </table>
          </div>
          {windowing && shown < rows.length && (
            typeof IntersectionObserver === "undefined" ? (
              <div className="p-2">
                <Button size="sm" variant="quiet"
                        onClick={() => setShown((s) => Math.min(s + TABLE_CHUNK, rows.length))}>
                  Muat {Math.min(TABLE_CHUNK, rows.length - shown)} baris lagi ({rows.length - shown} tersisa)
                </Button>
              </div>
            ) : (
              <div ref={sentinelRef} aria-hidden />
            )
          )}
        </>
      )}
    </section>
  );
}

/** Pola "5/8" + bar 48x4 (DESIGN 12.8), sama seperti signal bar.
 *  Bar-nya kini Bar bersama dari data.tsx (bukan salinan markup sendiri). */
export function UsageBar({ used, capacity }: { used: number; capacity: number | null }) {
  const pct = capacity ? Math.min(used / capacity, 1) * 100 : 0;
  return (
    <span className="inline-flex items-center gap-2 font-mono">
      <Bar pct={pct} tone={pct >= 100 ? "bg-down" : "bg-fiber"} className="w-12" />
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
        {/* size md = 32px, sama dengan filterInput Settings — bukan sm 28px. */}
        <Button size="md" aria-label={`Filter ${label}`}>
          {value.length ? `${label} · ${value.length}` : label}
          <CaretDown size={12} aria-hidden />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={4}
          collisionPadding={8}
          className="z-50 flex max-h-72 w-56 flex-col rounded-md border bg-surface p-2 shadow-overlay data-[state=open]:animate-[fade-in_150ms_ease-out]"
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
              <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 hover:bg-sunken max-md:py-3">
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
      <button type="button" onClick={onRemove} aria-label={`Hapus filter ${label}`} className="-m-1 p-1 text-muted hover:text-ink">
        <X size={10} aria-hidden />
      </button>
    </span>
  );
}
