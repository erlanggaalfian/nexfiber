/** Pembungkus semua modal aksi ONU + bagian form yang dipakai berulang.
 *
 *  Satu bentuk untuk 20+ modal: judul, isi yang bisa discroll, footer `Batal` + tombol aksi.
 *  Di bawah `sm` modal memakai lebar penuh layar (dikurangi margin) supaya 390px tidak
 *  pernah meluber ke samping; di desktop lebarnya dibatasi `max-w`.
 *
 *  Aksi yang driver-nya belum mendukung TIDAK disembunyikan: modalnya tetap terbuka supaya
 *  operator bisa melihat isinya, tombol simpannya mati dengan catatan "Belum didukung"
 *  (kontrak `GET /api/onus/{id}/actions`).
 */
import { CaretDown, Eye, EyeSlash, Info, Warning, X } from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import type { ReactNode } from "react";
import { useState } from "react";
import { Button } from "../../ui/button";

/** Kontrol form: SATU tinggi dengan crud.input (DESIGN §8: kontrol default
 *  32px desktop, 48px di bawah 768px). Nilai ini sengaja identik dengan
 *  crud.input — jangan diubah di satu tempat saja. */
export const field =
  "h-8 max-md:h-12 w-full min-w-0 rounded-sm border border-line-strong bg-surface px-3 text-sm";
export const selectCls = field;

/** Kotak catatan acuan (`.help-block` di dalam panel): kartu `surface` di atas badan `sunken`. */
export function Help({ children, warn }: { children: ReactNode; warn?: boolean }) {
  const Icon = warn ? Warning : Info;
  return (
    <p className={`flex items-start gap-1.5 text-xs ${warn ? "text-amber" : "text-muted"}`}>
      <Icon size={13} aria-hidden className="mt-0.5 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

/** Panel catatan penuh lebar (acuan `.attached-vlans-help`). */
export function HelpPanel({ children }: { children: ReactNode }) {
  return (
    <div className="mt-2.5 space-y-1 rounded-sm border border-line bg-surface px-3 py-2.5">{children}</div>
  );
}

/** Baris form acuan `form-horizontal`: label `col-sm-3` kanan + tebal, kontrol `col-sm-9`;
 *  menumpuk jadi satu kolom di mobile supaya 390px tidak pernah meluber. */
export function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3.5 grid gap-1 sm:grid-cols-12 sm:items-center sm:gap-x-4">
      <span className="text-sm font-semibold text-ink sm:col-span-3 sm:text-right">{label}</span>
      <div className="min-w-0 sm:col-span-9">
        {children}
        {hint && <div className="mt-1.5">{typeof hint === "string" ? <Help>{hint}</Help> : hint}</div>}
      </div>
    </div>
  );
}

/** Pilihan radio acuan `radio-inline`: sebaris dengan jarak 16px di `sm` ke atas, menumpuk di
 *  390px supaya label panjang ("Setup via ONU webpage") tidak pecah tak rapi. */
export function Radios<T extends string>(
  { name, value, options, onChange, autoFocus }:
  { name: string; value: T; options: { value: T; label: string; disabled?: boolean }[]; onChange: (v: T) => void; autoFocus?: boolean },
) {
  return (
    <div className="flex min-h-9 flex-col gap-1.5 py-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-1.5">
      {options.map((o, i) => (
        <label key={o.value} className="flex cursor-pointer items-center gap-1.5 text-sm">
          <input type="radio" name={name} value={o.value} checked={value === o.value}
                 disabled={o.disabled} autoFocus={autoFocus && i === 0}
                 onChange={() => onChange(o.value)} />
          <span className={o.disabled ? "text-faint" : ""}>{o.label}</span>
        </label>
      ))}
    </div>
  );
}

/** Kata sandi: hanya di state lokal pemanggil, tombol mata untuk melihat sementara.
 *  Tidak pernah ditulis ke URL/console — komponen ini tidak menyimpan apa pun sendiri. */
export function PasswordInput(
  { value, onChange, placeholder, label }:
  { value: string; onChange: (v: string) => void; placeholder?: string; label: string },
) {
  const [shown, setShown] = useState(false);
  return (
    <span className="relative flex items-center">
      <input className={`${field} pr-11`} type={shown ? "text" : "password"} value={value}
             autoComplete="new-password" placeholder={placeholder} aria-label={label}
             onChange={(e) => onChange(e.target.value)} />
      {/* Target sentuh 44px (DESIGN §9): tombol 44×44 terpusat di dalam input,
          jadi di desktop (input 32px) ia sedikit meluber vertikal, tapi tetap
          di dalam baris form dan tidak menggeser field lain. */}
      <button type="button" onClick={() => setShown(!shown)} aria-pressed={shown}
              className="absolute right-0.5 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center text-fiber hover:opacity-80">
        {shown ? <EyeSlash size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
        <span className="sr-only">{shown ? `Sembunyikan ${label}` : `Tampilkan ${label}`}</span>
      </button>
    </span>
  );
}

/** Multiselect VLAN: kotak cari + "Pilih semua" + daftar checkbox (acuan: VLANs / Allowed VLANs).
 *  Opsi ditulis "ID - Nama"; VLAN management sudah disaring di `serviceVlanOptions`. */
export function VlanMulti(
  { options, value, onChange, label, autoFocus }:
  {
    options: { number: number; name: string }[];
    value: number[];
    onChange: (next: number[]) => void;
    label: string;
    autoFocus?: boolean;
  },
) {
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = needle
    ? options.filter((o) => `${o.number} - ${o.name}`.toLowerCase().includes(needle))
    : options;
  const allShown = shown.length > 0 && shown.every((o) => value.includes(o.number));
  const toggle = (n: number) =>
    onChange(value.includes(n) ? value.filter((x) => x !== n) : [...value, n].sort((a, b) => a - b));
  return (
    <div className="rounded-sm border border-line-strong bg-surface">
      <div className="flex items-center gap-2 border-b p-2">
        <input className={field} placeholder="Cari VLAN ..." value={q} aria-label={`Cari ${label}`}
               autoFocus={autoFocus} onChange={(e) => setQ(e.target.value)} />
        <Button size="sm" variant="quiet" className="shrink-0"
                onClick={() => onChange(allShown
                  ? value.filter((v) => !shown.some((o) => o.number === v))
                  : [...new Set([...value, ...shown.map((o) => o.number)])].sort((a, b) => a - b))}>
          {allShown ? "Kosongkan" : "Pilih semua"}
        </Button>
      </div>
      <div className="max-h-44 overflow-y-auto p-1">
        {shown.length === 0 && (
          <p className="p-1 text-xs text-muted">
            {options.length === 0 ? "Belum ada VLAN" : "Tidak cocok"}
          </p>
        )}
        {shown.map((o) => (
          <label key={o.number} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-0.5 text-sm hover:bg-sunken max-md:py-3">
            <input type="checkbox" checked={value.includes(o.number)} onChange={() => toggle(o.number)} />
            <span className="truncate font-mono text-xs">{o.number} - {o.name}</span>
          </label>
        ))}
      </div>
      {value.length > 0 && (
        <p className="border-t px-2 py-1 font-mono text-xs text-muted">{value.join(", ")}</p>
      )}
    </div>
  );
}

/** Select sederhana dengan opsi placeholder di urutan pertama (nilai kosong). */
export function Select(
  { value, onChange, placeholder, children, label, autoFocus }:
  { value: string; onChange: (v: string) => void; placeholder?: string; children: ReactNode; label?: string; autoFocus?: boolean },
) {
  return (
    <span className="relative flex items-center">
      <select className={`${selectCls} appearance-none pr-6`} value={value} aria-label={label}
              autoFocus={autoFocus} onChange={(e) => onChange(e.target.value)}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {children}
      </select>
      <CaretDown size={12} aria-hidden className="pointer-events-none absolute right-2 text-faint" />
    </span>
  );
}

/* ---------------------------------------------------------------------------
 * Kerangka bersama SEMUA pop up aplikasi (modal ONU, drawer Settings, dialog
 * konfirmasi, dialog detail Logs). Satu overlay, satu radius/shadow, satu
 * header (judul + silang), satu badan `sunken` yang bisa discroll, satu footer
 * kanan. Di bawah `sm` semuanya jadi bottom sheet penuh lebar (DESIGN §12.8).
 * Jangan menulis markup `Dialog.*` baru di halaman: pakai salah satu shell.
 * ------------------------------------------------------------------------- */
const OVERLAY =
  "fixed inset-0 z-40 bg-black/50 data-[state=open]:animate-[fade-in_150ms_ease-out] data-[state=closed]:animate-[dialog-fade-out_150ms_ease-in] motion-reduce:animate-none";
const PANEL = "fixed z-50 flex flex-col overflow-hidden border bg-surface shadow-modal";
/** Mobile (<768px, sama dengan batas kartu DESIGN §12.10): tempel ke bawah
 *  layar, sudut atas membulat, animasi naik, hormati safe-area. */
const SHEET =
  "max-md:inset-x-0 max-md:top-auto max-md:bottom-0 max-md:left-0 max-md:max-h-[88vh] max-md:w-full max-md:max-w-none max-md:translate-x-0 max-md:translate-y-0 max-md:rounded-t-md max-md:rounded-b-none max-md:border-x-0 max-md:border-b-0 max-md:pb-[env(safe-area-inset-bottom)]";
/* Dialog tengah: fade + naik 8px, 225ms. Keyframe-nya hanya menganimasikan
   `transform: translateY` — pemusatan -50%/-50% tetap dipegang utility Tailwind
   (properti `translate` di Tailwind v4), jadi keyframe yang menulis
   `translate(-50%, …)` penuh justru akan menggandakan offset selama animasi
   lalu melompat saat animasi selesai. Di mobile, aturan sheet-in di index.css
   tetap menang seperti sebelumnya; prefers-reduced-motion dimatikan global
   oleh index.css untuk konten dialog. */
const CENTER =
  "top-1/2 left-1/2 max-h-[calc(100vh-1.5rem)] w-[calc(100vw-1.5rem)] -translate-x-1/2 -translate-y-1/2 rounded-md data-[state=open]:animate-[dialog-center-in_225ms_ease-out] motion-reduce:animate-none";
const DRAWER =
  "inset-y-0 right-0 w-full max-w-[480px] border-l data-[state=closed]:animate-[drawer-out_200ms_ease-in] data-[state=open]:animate-[drawer-in_250ms_ease-out]";

export function ModalFrame({ variant = "center", width = "max-w-[600px]", title, onClose, onSubmit, footer, children }: {
  variant?: "center" | "drawer";
  /** Hanya dipakai `center`: kelas `max-w-*`. */
  width?: string;
  title: ReactNode;
  onClose: () => void;
  onSubmit?: () => void;
  footer: ReactNode;
  children?: ReactNode;
}) {
  return (
    <>
    {/* Keyframe dialog tengah + fade-out overlay didefinisikan di sini (bukan
        index.css, yang bukan milik area ini): opacity/transform saja, tanpa
        gradien/glass/pulse/loop. */}
    <style>{`@keyframes dialog-center-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } } @keyframes dialog-fade-out { from { opacity: 1; } to { opacity: 0; } }`}</style>
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={OVERLAY} />
        <Dialog.Content
          className={`${PANEL} ${variant === "drawer" ? DRAWER : `${CENTER} ${width}`} ${SHEET}`}
        >
          <div className="flex items-start justify-between gap-3 border-b px-5 py-3.5">
            <Dialog.Title className="text-lg font-semibold text-ink">{title}</Dialog.Title>
            <Dialog.Close
              className="-mr-1 flex size-11 shrink-0 items-center justify-center rounded-sm text-faint hover:text-ink"
              aria-label="Tutup"
            >
              <X size={16} aria-hidden />
            </Dialog.Close>
          </div>
          <form
            onSubmit={(e) => { e.preventDefault(); onSubmit?.(); }}
            className="flex min-h-0 flex-1 flex-col"
          >
            {/* Badan lebih teredam dari header+footer supaya form menonjol. */}
            <div className="min-h-0 flex-1 overflow-y-auto bg-sunken px-5 py-4">{children}</div>
            {/* HP: footer jadi kolom tombol penuh lebar (target sentuh 48px dari
                Button) supaya aksi tidak berdesakan di kanan sheet. */}
            <div className="flex flex-wrap items-center justify-end gap-2 border-t px-5 py-3 max-md:flex-col max-md:items-stretch max-md:[&>button]:w-full">
              {footer}
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    </>
  );
}

/** Pesan galat satu bentuk untuk semua pop up. */
export function ModalError({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-xs text-down" role="alert">{children}</p>;
}

/** Guard tutup (DESIGN §13): bila form kotor, silang/Esc/klik overlay/tombol
 *  tutup tidak langsung menutup — tampil dulu dialog konfirmasi kecil yang
 *  sudah ada (ConfirmShell). Bila form bersih, tutup langsung seperti biasa.
 *  Caller yang tidak mengisi `dirty` (dialog tanpa form) tidak kena guard.
 *  Catatan: drawer Settings yang lewat pembungkus crud Drawer/Confirm tidak
 *  meneruskan `dirty` (crud bukan milik area ini), jadi guard di sana belum
 *  aktif — lihat laporan parent. */
function useDiscardGuard(dirty: boolean | undefined, onClose: () => void) {
  const [discard, setDiscard] = useState(false);
  const requestClose = () => { if (dirty) setDiscard(true); else onClose(); };
  const discardDialog = discard ? (
    <ConfirmShell title="Buang perubahan?" body="Perubahan yang belum disimpan akan hilang."
                  action="Buang perubahan" danger
                  onConfirm={onClose} onClose={() => setDiscard(false)} />
  ) : null;
  return { requestClose, discardDialog };
}

export type ShellProps = {
  title: string;
  onClose: () => void;
  onSubmit?: () => void;
  /** Teks tombol aksi; default `Simpan`. */
  action?: string;
  busy?: boolean;
  error?: string | null;
  /** Dari `GET .../actions`: false = tombol mati + catatan. `null` = belum dimuat. */
  supported?: boolean | null;
  note?: string | null;
  /** Tombol aksi memakai gaya bahaya (hapus/factory). */
  danger?: boolean;
  /** Gaya peringatan kuning acuan (`btn-warning`/`btn-yellow`): reboot, disable, resync. */
  warn?: boolean;
  /** Acuan `configureNetworkPort` memakai dialog 900px, bukan 600px. */
  wide?: boolean;
  /** Mati karena validasi lokal (mis. konfirmasi belum diketik). */
  disabled?: boolean;
  /** Teks tombol tutup; default `Batal` untuk form, `Tutup` untuk dialog
   *  tanpa aksi simpan (diatur pemanggil lewat prop ini bila perlu). */
  closeLabel?: string;
  /** Teks tombol aksi saat `busy`; default `Mengirim ...`. */
  busyLabel?: string;
  /** True = form sudah diubah dari nilai awal: penutupan kena guard konfirmasi. */
  dirty?: boolean;
  extra?: ReactNode;
  children?: ReactNode;
};

export function ModalShell({
  title, onClose, onSubmit, action = "Simpan", busy, error, supported = true, note,
  danger, warn, wide, disabled, closeLabel = "Batal", busyLabel = "Mengirim ...", dirty, extra, children,
}: ShellProps) {
  const unsupported = supported === false;
  const { requestClose, discardDialog } = useDiscardGuard(dirty, onClose);
  return (
    <>
    <ModalFrame
      title={title}
      onClose={requestClose}
      /* Lebar acuan `.modal-dialog` 600px (900px untuk port ethernet, lihat `wide`). */
      width={wide ? "max-w-[900px]" : "max-w-[600px]"}
      onSubmit={unsupported ? undefined : onSubmit}
      footer={
        <>
          {/* Mobile (<768px): footer jadi kolom, jadi extra diurutkan terakhir
              (order-3) — aksi utama, batal, lalu aksi destruktif. Desktop
              tidak berubah: extra tetap di kiri lewat mr-auto. */}
          {extra && <span className="mr-auto max-md:order-3">{extra}</span>}
          {/* Tanpa tombol aksi, tombol tutup yang jadi aksi utama. */}
          <Button size="md" variant={onSubmit ? "quiet" : "fiber"} onClick={requestClose}>{closeLabel}</Button>
          {onSubmit && (
            <Button size="md" type="submit"
                    variant={danger ? "dangerSolid" : warn ? "primary" : "fiber"}
                    disabled={busy || unsupported || disabled}>
              {busy ? busyLabel : action}
            </Button>
          )}
        </>
      }
    >
      {children}
      {unsupported && (
        <p className="mt-2 text-xs text-amber" role="status">
          Belum didukung{note ? ` — ${note}` : ""}
        </p>
      )}
      {error && <ModalError>{error}</ModalError>}
    </ModalFrame>
    {discardDialog}
    </>
  );
}

/** Drawer kanan 480px (DESIGN §13) — tema sama dengan modal, hanya posisinya beda. */
export function DrawerShell({
  title, onClose, onSubmit, busy, error, disabled, dirty,
  action = "Simpan", busyLabel = "Menyimpan ...", closeLabel = "Batal", children,
}: {
  title: ReactNode; onClose: () => void; onSubmit: () => void;
  busy?: boolean; error?: string | null; disabled?: boolean; dirty?: boolean;
  action?: string; busyLabel?: string; closeLabel?: string; children?: ReactNode;
}) {
  const { requestClose, discardDialog } = useDiscardGuard(dirty, onClose);
  return (
    <>
    <ModalFrame
      variant="drawer"
      title={title}
      onClose={requestClose}
      onSubmit={onSubmit}
      footer={
        <>
          <Button size="md" variant="quiet" onClick={requestClose}>{closeLabel}</Button>
          <Button size="md" type="submit" variant="fiber" disabled={busy || disabled}>
            {busy ? busyLabel : action}
          </Button>
        </>
      }
    >
      {children}
      {error && <ModalError>{error}</ModalError>}
    </ModalFrame>
    {discardDialog}
    </>
  );
}

/** Dialog konfirmasi kecil (DESIGN §13: 400px, satu kalimat dampak, aksi di kanan). */
export function ConfirmShell({
  title, body, action, onConfirm, onClose, error, busy, disabled, danger = true,
  closeLabel = "Tutup", dirty, children,
}: {
  title: ReactNode; body?: ReactNode; action: string;
  onConfirm: () => void; onClose: () => void;
  error?: string | null; busy?: boolean; disabled?: boolean; danger?: boolean;
  closeLabel?: string; dirty?: boolean; children?: ReactNode;
}) {
  const { requestClose, discardDialog } = useDiscardGuard(dirty, onClose);
  return (
    <>
    <ModalFrame
      title={title}
      onClose={requestClose}
      width="max-w-[420px]"
      onSubmit={onConfirm}
      footer={
        <>
          <Button size="md" variant="quiet" onClick={requestClose}>{closeLabel}</Button>
          <Button size="md" type="submit" variant={danger ? "dangerSolid" : "primary"}
                  disabled={busy || disabled}>
            {action}
          </Button>
        </>
      }
    >
      {body && <p className="text-sm text-muted">{body}</p>}
      {children}
      {error && <ModalError>{error}</ModalError>}
    </ModalFrame>
    {discardDialog}
    </>
  );
}
