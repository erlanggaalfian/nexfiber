import type { ButtonHTMLAttributes } from "react";

/* Aturan hover per keluarga: tombol isi (fiber/primary/dangerSolid) hover:opacity-90,
   tombol garis (secondary/danger) hover:bg-sunken, quiet hover:underline.
   Teks di atas tombol isi: terang text-white, gelap token on-accent (dark:text-on-*)
   yang disediakan lapisan tema — token itu BUKAN didefinisikan di sini, jadi sampai
   lapisan tema menambahkannya, varian dark: di bawah belum menghasilkan CSS dan
   teks gelap tetap putih (tidak ada regresi, tapi kontras gelap belum terperbaiki). */
const VARIANTS = {
  fiber: "bg-fiber text-white dark:text-on-fiber font-semibold border border-fiber hover:opacity-90",
  primary: "bg-amber text-white dark:text-on-amber font-semibold border border-amber hover:opacity-90",
  secondary: "border border-line-strong text-ink hover:bg-sunken",
  quiet: "text-fiber hover:underline",
  danger: "border border-down text-down hover:bg-sunken",
  /** Aksi merusak sebagai tombol utama footer modal (acuan SmartOLT `btn-danger` terisi penuh).
   *  Token on-down khusus belum tersedia, jadi gelap memakai text-on-fiber sebagai
   *  teks tinta gelap di atas merah terang tema gelap (sesuai instruksi tahap ini). */
  dangerSolid: "bg-down text-white dark:text-on-fiber font-semibold border border-down hover:opacity-90",
};
/* DESIGN §8: tinggi kontrol desktop 28/32/40px; di bawah 768px semua tombol
   naik ke target sentuh 48px (DESIGN §9) lewat min-height, bukan tinggi baru. */
const SIZES = { sm: "h-7 px-2 max-md:min-h-12", md: "h-8 px-3 max-md:min-h-12", lg: "h-10 px-4 max-md:min-h-12" };

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
};

export const buttonClass = (variant: keyof typeof VARIANTS = "secondary", size: keyof typeof SIZES = "md") =>
  `inline-flex items-center justify-center gap-1.5 rounded-sm text-sm whitespace-nowrap transition duration-150 ease-out motion-reduce:transition-none active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 ${VARIANTS[variant]} ${SIZES[size]}`;

export function Button({ variant = "secondary", size = "md", className = "", type = "button", ...rest }: Props) {
  return <button type={type} className={`${buttonClass(variant, size)} ${className}`} {...rest} />;
}
