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
import { CaretDown, Eye, EyeSlash } from "@phosphor-icons/react";
import { Dialog } from "radix-ui";
import type { ReactNode } from "react";
import { useState } from "react";
import { input } from "../../crud";
import { Button } from "../../ui/button";

export const field = input;
export const selectCls = input;

/** Baris form: label kiri sempit (pola acuan `col-sm-3`), kontrol kanan; menumpuk di mobile. */
export function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="mb-2.5 grid gap-1 sm:grid-cols-12 sm:items-center sm:gap-x-3">
      <span className="text-xs font-semibold text-ink sm:col-span-4 sm:pt-0 sm:text-right">{label}</span>
      <div className="min-w-0 sm:col-span-8">
        {children}
        {hint && <p className="mt-0.5 text-xs text-faint">{hint}</p>}
      </div>
    </div>
  );
}

/** Pilihan radio: menumpuk di mobile (390px) supaya label panjang tidak pecah tak rapi,
 *  sebaris di `sm` ke atas. */
export function Radios<T extends string>(
  { name, value, options, onChange }:
  { name: string; value: T; options: { value: T; label: string; disabled?: boolean }[]; onChange: (v: T) => void },
) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:gap-x-3">
      {options.map((o) => (
        <label key={o.value} className="flex items-center gap-1.5 text-sm">
          <input type="radio" name={name} value={o.value} checked={value === o.value}
                 disabled={o.disabled} onChange={() => onChange(o.value)} />
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
      <input className={`${field} pr-7`} type={shown ? "text" : "password"} value={value}
             autoComplete="new-password" placeholder={placeholder} aria-label={label}
             onChange={(e) => onChange(e.target.value)} />
      <button type="button" onClick={() => setShown(!shown)} aria-pressed={shown}
              className="absolute right-2 text-fiber hover:opacity-80">
        {shown ? <EyeSlash size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
        <span className="sr-only">{shown ? `Sembunyikan ${label}` : `Tampilkan ${label}`}</span>
      </button>
    </span>
  );
}

/** Multiselect VLAN: kotak cari + "Pilih semua" + daftar checkbox (acuan: VLANs / Allowed VLANs).
 *  Opsi ditulis "ID - Nama"; VLAN management sudah disaring di `serviceVlanOptions`. */
export function VlanMulti(
  { options, value, onChange, label }:
  {
    options: { number: number; name: string }[];
    value: number[];
    onChange: (next: number[]) => void;
    label: string;
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
    <div className="rounded-sm border border-line-strong">
      <div className="flex items-center gap-2 border-b p-1.5">
        <input className={`${field} h-7`} placeholder="Cari VLAN ..." value={q} aria-label={`Cari ${label}`}
               onChange={(e) => setQ(e.target.value)} />
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
          <label key={o.number} className="flex cursor-pointer items-center gap-2 rounded-sm px-1 py-0.5 text-sm hover:bg-sunken">
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

/** Select sederhana dengan opsi "Jangan ubah"/placeholder di urutan pertama. */
export function Select(
  { value, onChange, placeholder, children, label }:
  { value: string; onChange: (v: string) => void; placeholder?: string; children: ReactNode; label?: string },
) {
  return (
    <span className="relative flex items-center">
      <select className={`${selectCls} appearance-none pr-6`} value={value} aria-label={label}
              onChange={(e) => onChange(e.target.value)}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {children}
      </select>
      <CaretDown size={12} aria-hidden className="pointer-events-none absolute right-2 text-faint" />
    </span>
  );
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
  /** Mati karena validasi lokal (mis. konfirmasi belum diketik). */
  disabled?: boolean;
  extra?: ReactNode;
  children?: ReactNode;
};

export function ModalShell({
  title, onClose, onSubmit, action = "Simpan", busy, error, supported = true, note,
  danger, disabled, extra, children,
}: ShellProps) {
  const unsupported = supported === false;
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-1.5rem)] w-[calc(100vw-1.5rem)] max-w-[560px] -translate-x-1/2 -translate-y-1/2 flex-col rounded-md border bg-surface shadow-modal data-[state=open]:animate-[fade-in_150ms_ease-out]"
        >
          <Dialog.Title className="border-b px-4 py-2.5 text-sm font-semibold">{title}</Dialog.Title>
          <form
            onSubmit={(e) => { e.preventDefault(); if (!unsupported) onSubmit?.(); }}
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              {children}
              {unsupported && (
                <p className="mt-2 text-xs text-amber" role="status">
                  Belum didukung{note ? ` — ${note}` : ""}
                </p>
              )}
              {error && <p className="mt-2 text-xs text-down" role="alert">{error}</p>}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2 border-t px-4 py-2.5">
              {extra && <span className="mr-auto">{extra}</span>}
              <Button size="sm" onClick={onClose}>Batal</Button>
              {onSubmit && (
                <Button size="sm" type="submit" variant={danger ? "danger" : "fiber"}
                        disabled={busy || unsupported || disabled}>
                  {busy ? "Mengirim ..." : action}
                </Button>
              )}
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
