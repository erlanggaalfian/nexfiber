import type { ButtonHTMLAttributes } from "react";

/* Toggle switch standar (adopsi vibekoding §4.9, dipetakan ke token Nexfiber):
   48×28px, knob 22px, geser 20px, transisi 100ms ease-out (motion-micro, §2.1).
   Track mati = --border-strong, menyala = --fiber, knob putih.
   Fokus memakai aturan global `:focus-visible` di styles/index.css
   (outline 2px solid --focus), jadi tidak ditulis ulang di sini.
   Catatan bentuk: track membulat penuh adalah kebutuhan fungsi kontrol switch
   (ruang gerak knob); larangan pill di DESIGN §6 menyasar badge/tombol/input,
   bukan switch — konsisten dengan spesifikasi adopsi yang disetujui. */
type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "onChange" | "onClick" | "role" | "type"> & {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  /** Nama aksesibel; dipakai sebagai aria-label bila aria-label tidak diisi eksplisit. */
  label?: string;
};

export function Switch({ checked, onCheckedChange, label, disabled = false, className = "", ...rest }: Props) {
  const { "aria-label": ariaLabel, ...restProps } = rest;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel ?? label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors duration-100 ease-out motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-fiber" : "bg-line-strong"
      } ${className}`}
      {...restProps}
    >
      {/* Knob 22px, inset 3px; menyala = geser 20px (48 - 22 - 3 - 3). */}
      <span
        aria-hidden
        className={`absolute top-[3px] left-[3px] size-[22px] rounded-full bg-white shadow-xs transition-transform duration-100 ease-out motion-reduce:transition-none ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}
