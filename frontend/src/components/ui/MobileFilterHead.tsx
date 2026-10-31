/** Kepala filter collapsible khusus mobile (adopsi pola vibekoding §3.3, memakai
 *  token Nexfiber — bukan hex/komponen vibekoding). Hanya tampil di bawah 768px
 *  (`md:hidden`); desktop memakai baris filter inline seperti biasa dan tidak
 *  tersentuh komponen ini sama sekali.
 *
 *  Kontrak: label "Filter" + hitungan "N aktif" + chevron yang berputar saat
 *  terbuka; toggle `aria-expanded`; panel berisi `children` (kontrol filter
 *  milik halaman) hanya di-mount saat terbuka. Ketuk pada kontrol di dalam
 *  panel tidak melipat panel — yang melipat hanya kepala.
 */
import { CaretDown } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { useState } from "react";

export function MobileFilterHead({ activeCount, children, className = "" }: {
  /** Jumlah filter yang sedang aktif (chip yang tampil di halaman). */
  activeCount: number;
  /** Kontrol filter milik halaman — dipakai ulang apa adanya, tanpa salinan logika. */
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`md:hidden ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-12 w-full items-center justify-between gap-2 rounded-md border border-line bg-surface px-3 text-base font-semibold text-ink hover:bg-sunken"
      >
        <span>Filter</span>
        <span className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted">{activeCount} aktif</span>
          <CaretDown
            size={16}
            aria-hidden
            className={`text-muted transition-transform duration-150 ease-out motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
          />
        </span>
      </button>
      {open && (
        <div className="mt-2 flex flex-wrap items-center gap-2">{children}</div>
      )}
    </div>
  );
}
