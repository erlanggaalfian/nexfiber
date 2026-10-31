# Audit Konsistensi Desain — Nexfiber Frontend (2026-10-31)

Audit read-only oleh 4 agen paralel (tipografi & warna · spacing/radius/shadow · pola komponen & interaksi · motion/hover/aksesibilitas). Acuan: DESIGN.md. Tidak ada file diubah.

## Ringkasan

| Severity | Jumlah |
|---|---|
| BERAT | 0 |
| SEDANG | 5 |
| RINGAN | 19 (2 di antaranya catatan dokumentasi, bukan bug) |

## Temuan SEDANG (prioritas perbaikan)

1. **`rounded` polos tidak ter-render (10 titik)** — `pages/OnuDetail.tsx:299,388,1119,1409,1480,1576,1893,1954,1981,2033` (chip SN, chip VLAN, chip aksi, satu `<select>`). Di Tailwind v4 class `rounded` tanpa sufiks **tidak menghasilkan CSS** (verifikasi di `dist`), jadi elemen tampil siku 0px. Seharusnya `rounded-sm` (§6). Di file yang sama baris 433 sudah benar — inkonsistensi dalam satu file.
2. **Amber dipakai untuk teks peringatan (5 titik)** — `Layout.tsx:253` (banner koneksi terputus), `ModalShell.tsx:28,339` (hint warn), `Configured.tsx:305` (batas export CSV), `OnuDetail.tsx:1680` (diagnostik). Seharusnya `--st-warn`; amber dicadangkan untuk aksi yang mengubah jaringan (§3).
3. **Badge "Segera" memakai amber** — `OnuDetail.tsx:1981` (`border-amber/30 bg-amber/10 text-amber`). DESIGN §11: label "Segera" = teks `--text-faint`.
4. **Kontras gagal di dark mode** — `lib/auth.tsx:70` tombol "Ganti password" `bg-fiber text-white` tanpa `dark:text-on-fiber`; putih di atas `#4FB79B` ≈ 2,4:1, gagal AA (§3).
5. **Banner "sebagian gagal" hilang** — `Dashboard.tsx:366`: saat sebagian OLT gagal dipolling tidak ada banner "X dari N OLT gagal dipolling…" (§8 State data); hanya pengurutan offline di atas.

## Temuan RINGAN

**Motion/hover/a11y**
- R1. `Switch.tsx:28,33` — durasi 200ms, seharusnya 100ms (`motion-micro` untuk toggle, §2.1).
- R2. `button.tsx:10,11,18` — `text-white` mentah alih-alih token `text-on-fiber`/`text-on-amber`; `dangerSolid` memakai `dark:text-on-fiber` (salah semantik, kontras lolos). Render identik — inkonsistensi literal aturan §3.

**Tipografi & warna**
- R3. Ukuran px arbitrary: `text-[9px]`/`text-[10px]` (label mikro diagram `OnuRearPanel`, label sumbu grafik `OnuDetail`) — skala §4 tidak mendefinisikan; `text-[11px]` (3 titik) = padanan persis `text-xs`, seharusnya pakai token. `text-[15px]` logo bukan temuan (§11).
- R4. Amber sebagai warna seri grafik (`OnuDetail.tsx:465,664,769,773,1691,1701,1743,1769`) — tidak dilarang eksplisit §3 tapi mengencerkan makna amber; pertimbangkan dokumentasi.
- R5. `crud.tsx:249` — `Bar` usage ≥100% memakai `bg-down` (bukan state perangkat); borderline, pertimbangkan dokumentasi §3.
- R6. `lib/theme.ts:12` — hex literal untuk meta `theme-color`; dapat diterima (meta butuh literal, nilai benar) — catat saja.

**Spacing/radius/shadow**
- R7. `Dashboard.tsx:370` — section "Aktivitas terbaru" tanpa `shadow-xs`, kartu OLT di atasnya pakai — inkonsistensi bahasa kartu §8.
- R8. `ModalShell.tsx:38` (HelpPanel) & `crud.tsx:71` (JobTrace) — kotak `border` penuh di dalam modal berborder; seharusnya latar sunken tanpa border (de-boxing §6).
- R9. `Dashboard.tsx:363` & `GraphData.tsx:231` — `gap-4` (16px) antar panel/kartu; seharusnya `gap-3` (12px, §5).
- R10. `data.tsx:101` — `Panel` memakai `max-md:p-3`; §5 menetapkan padding panel 16px tanpa pengecualian mobile.
- R11. `OnuDetail.tsx:1732` — header section `mb-4`, section lain `mb-3` di file yang sama.
- R12. `LocationModal.tsx:134` — `sm:pl-[25%]` arbitrary; §12.4 menetapkan lebar label 112px.
- R13. `OnuRearPanel.tsx:40,53` — `rounded-full` pada LED diagram hardware (di luar token; diagram tidak dicakup DESIGN — dokumentasikan sebagai pengecualian atau biarkan).
- R14. Observasi: dua bobot border kartu — `Panel` hairline `border-line/60` (§6) vs `TableCard`/`Section` `border-line` penuh (§8). Keduanya keputusan tercatat, tampil berbeda di halaman yang sama.

**Komponen & interaksi**
- R15. `button.tsx:22` — kode memakai `rounded-md` (keputusan audit 2026-10-28) tapi DESIGN §8 masih menulis "radius-sm" untuk tombol — dokumen perlu diperbarui.
- R16. `OnuDetail.tsx:1407` — strip identitas tanpa tautan "← Configured" di desktop (§11); navigasi kembali hanya di top bar mobile.
- R17. `Toast`/`Switch` sudah terpasang tapi `useToast()`/`Switch` belum dipakai di alur nyata mana pun (§13/§15).
- R18. `data.tsx:125` — skeleton generik `h-8` (32px) vs tinggi baris asli 42px/50px (§8: skeleton setinggi baris asli).

## Bersih (tidak ada temuan)

- Shadow: semua token, tanpa arbitrary. Safe-area: semua titik (`env()`). Baris judul: 13 halaman konsisten via `PageTitle`.
- Uppercase: tracking ≤0,02em semua. Mono/tabular: serial, VLAN, PON, dBm, metrik — benar; `tabular-nums` global.
- Dark mode komponen baru (Toast/Switch/MobileFilterHead): 100% token → adaptif otomatis.
- Gradien/glow/glass: nol. `alert(`/`confirm(`: nol. Popup hand-rolled: nol (satu-satunya Dialog di ModalShell).
- Motion: durasi & easing dalam token; tanpa animasi looping; properti hanya opacity/transform (+ pengecualian §2.1 yang sah); `prefers-reduced-motion` menang atas utility (blok unlayered); hover satu aturan per keluarga; fokus terlihat; `Esc` native Radix; `aria-expanded` lengkap; stagger tidak bersarang, total tepat 500ms.
- Tombol: varian & tinggi & hover & konfirmasi destruktif (ketik SN) lolos. Badge: bukan pill; ikon pembeda lolos. Kartu mobile §12.10 lolos. Bottom nav §11.1 lolos. Form: satu tinggi input, validasi inline lolos. Pola lipat §15: satu kontrak, lolos.

## Usulan putaran perbaikan

Perbaiki 5 SEDANG + R1, R2, R7–R12, R15–R18 (semua kecil, frontend-only). R3/R4/R5/R13/R14/R6: dokumentasikan pengecualiannya di DESIGN.md, bukan diubah. Estimasi: 2 agen paralel (1: OnuDetail + Dashboard + theme/auth; 2: komponen ui + crud + ModalShell + docs), lalu parent verifikasi build + check.

## Status perbaikan (2026-10-31, ~15:00 WIB)

Dikerjakan 2 agen paralel + verifikasi parent. **Semua 5 SEDANG + 12 RINGAN yang actionable diperbaiki**; 7 RINGAN menjadi pengecualian tercatat di DESIGN.md (§8 diperbarui + §15.1 baru).

- SEDANG-1: 10× `rounded` polos → `rounded-sm` (OnuDetail.tsx). ✓
- SEDANG-2: 5 titik amber peringatan → `st-warn` (Layout, ModalShell ×2, Configured, OnuDetail diagnostik). ✓
- SEDANG-3: badge "Segera" amber → versi netral (`border-line bg-sunken text-muted`) via
  commit user 3fc5a55 — saat rebase, konflik dimenangkan versi user (bukan label faint
  dari agen). ✓
- SEDANG-4: tombol "Ganti password" + `dark:text-on-fiber` (auth.tsx). ✓
- SEDANG-5: banner "X dari N OLT gagal dipolling…" + daftar nama OLT di Dashboard (dari `q.data.olts[].status`, tanpa mengarang). ✓
- R1: Switch 200ms → 100ms. ✓ R2: button `text-white` → token on-fiber/on-amber. ✓
- R7: Aktivitas + `shadow-xs`. ✓ R8: HelpPanel & JobTrace de-boxing (bg-sunken, tanpa border). ✓
- R9: gap-4 → gap-3 (Dashboard, GraphData). ✓ R10: Panel `max-md:p-3` → `p-4`. ✓
- R11: OnuDetail header section `mb-4` → `mb-3`. ✓
- R12: LocationModal — disejajarkan via grid yang sama (tanpa nilai arbitrary), bukan 112px mentah. ✓
- R16: tautan "← Configured" desktop di OnuDetail. ✓ R18: Skeleton `h-8` → `h-[42px]`. ✓
- Pengecualian tercatat (§15.1): R3, R5, R6, R13, R14, `dangerSolid dark:text-on-fiber`;
  R17 = follow-up (toast butuh pelacakan origin job = fitur baru).
  KOREKSI pasca-rebase: pengecualian R4 (amber seri grafik) DICABUT — commit user 3fc5a55
  menghapus total amber dari grafik/legend (upload=ink, download=fiber, OLT Rx=ink);
  §15.1 diperbarui mencerminkan aturan tegas tersebut.
- Verifikasi parent: `npm run build` ✓, `npm run check` exit 0 ✓.
- REBASE: commit user 3fc5a55 ("Perbaikan palet warna", 2026-10-29) muncul di remote dan
  sudah mengerjakan sebagian SEDANG-2 (amber→warn) + R4 + badge "Segera" + hierarki tombol
  solid + `border-strong` ≥3:1 + hover tabel 55%. Rebase b49afe7 → 3fc5a55 dengan 2 konflik,
  keduanya dimenangkan versi user (banner `border-l-2 border-warn bg-sunken`; badge "Segera"
  netral). Hasil akhir diverifikasi: tidak ada sisa `*-amber` di luar badge Unconfigured
  dan varian `primary` (keduanya pengecualian sah aturan tegas).
- UNCOMMITTED/UNPUSHED — menunggu perintah push.
