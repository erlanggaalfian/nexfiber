# Analisis Adopsi Base Design System vibekoding → Nexfiber

Tanggal: 2026-10-31. Sumber: `~/workspace/vibekoding/design-system.md` (commit 68d88d4),
dibandingkan dengan `DESIGN.md` Nexfiber + kode `frontend/src` saat ini.

## 0. Prinsip adopsi (disetujui user)

**Yang diadopsi = pola, kontrak interaksi, dan skala peran. Yang TIDAK diadopsi = nilai hex warna.**
Warna tetap memakai palet Nexfiber saat ini. Ini selaras dengan filosofi vibekoding sendiri
(§2.1: "sistem palet, bukan warna tetap" — yang dikunci adalah peran & relasi antar warna).

### Pemetaan peran warna (vibekoding → Nexfiber)

| Peran vibekoding | Token Nexfiber | Nilai terang / gelap |
|---|---|---|
| `--color-primary` (500) | `--fiber` | `#0F5C4A` / `#4FB79B` |
| `--color-primary-hover` | hover fiber (opacity / darken) | — |
| `--color-accent` (monokromatik) | `--teal-glow` (hanya ring/garis 1–2px) | `#1D8A74` / `#3FD1B0` |
| Aksi komit (vibekoding tidak punya peran ini) | `--amber` | `#B4540A` / `#E08A3C` |
| `--color-bg-body` | `--bg-app` | `#F7F6F3` / `#131412` |
| `--color-bg-content` | `--bg-surface` | `#FFFFFF` / `#1B1C19` |
| `--color-bg-hover` | `--bg-sunken` | `#EFEDE8` / `#232420` |
| `--color-text-header/body/muted` | `--text` / `--text-muted` / `--text-faint` | sesuai token |
| `--color-border` | `--border` (+ `--border-strong`) | sesuai token |
| Status success/warning/danger/info | `--st-up/warn/down/idle` | sesuai token (hue tetap, tidak digeser) |

Catatan: vibekoding menurunkan skala primer 50–900 dari satu warna dasar via roda warna.
Nexfiber tidak memakai skala 50–900 (token tunggal per peran + varian gelap manual teruji kontras).
Skala tidak diwajibkan — peran di atas cukup. Opsi: bila nanti butuh varian (mis. latar tint primer),
turunkan dari `--fiber` dengan aturan lightness vibekoding, bukan hex baru ad hoc.

## 1. Yang sudah selaras — tidak perlu diubah

1. **Filosofi anti-slop**: sama persis (tanpa gradient/glass berlebih, tanpa pulse, transisi pendek).
2. **Mobile-first collapsed-first**: Nexfiber sudah punya (daftar ber-pembatas <768px, filter bottom-sheet,
   TableCard cabang kartu). Vibekoding §1.1 ≈ pola Nexfiber §12.10.
3. **Desktop tidak berubah**: sama.
4. **Navigasi bawah mobile**: Nexfiber sudah punya 5 tab di <1024px (vibekoding: 4–5 tab di ≤768px).
   Breakpoint Nexfiber (<1024px) dipertahankan — wilayah sentuh menurut audit 2026-10-28.
5. **Dialog bottom-sheet di mobile**: sudah ada (ModalShell/ConfirmShell, breakpoint <768px sejak design pass).
6. **Dark mode + toggle + localStorage + prefers-color-scheme**: sudah ada, teruji kontras.
7. **Token motion**: paralel (micro 100ms / hover 150ms / fade 200ms / panel 250ms); Nexfiber bahkan lebih
   kaya (entrance 300ms + stagger). Durasi vibekoding 100–200ms sudah tercakup.
8. **Tombol**: label sudah `font-semibold` (600) — sesuai tangga bobot vibekoding; radius kontrol sudah
   disamakan ke `md` (8px) pada audit 2026-10-28, min-height mobile 44–48px sudah ada.
9. **Pagination adaptif**: sudah ada (design pass terakhir).
10. **Bar data**: Nexfiber punya komponen `Bar` bersama (signal/usage) dengan transisi 300ms — sepadan
    dengan progress bar vibekoding §4.10. **Signal bar 4px adalah motif identitas — jangan diubah.**
11. **State data** (kosong/filter/loading/error/sebagian gagal): sudah didefinisikan di DESIGN §8.

## 2. Gap yang bisa diadopsi (prioritas)

### P1 — Komponen yang belum ada di Nexfiber
1. **Toast** (§4.7). DESIGN §13 mendefinisikan perilaku toast (kanan bawah, maks 3, hilang 5 detik,
   gagal menetap), tetapi **tidak ada komponen Toast di kode** (grep `toast` di `frontend/src` kosong).
   Adopsi pola vibekoding: di mobile toast diposisikan **di atas bottom nav 56px** agar tidak tertutup.
2. **Toggle switch standar** (§4.9: 48×28px, knob 22px, geser 20px, 200ms, track off slate-300 / on primer,
   focus-visible outline 2px). Tidak ada komponen switch di Nexfiber (yang ada hanya checkbox 20px).
   Terapkan untuk setelan on/off (mis. OLT `is_active`).

### P2 — Pola interaksi yang belum ada
3. **Filter collapsible mobile dengan hitungan "N aktif"** (§3.3). Nexfiber Configured mobile memakai
   tombol Filter → bottom sheet berisi semua filter. Adopsi varian vibekoding (kepala lipat + count)
   sebagai pola alternatif/penyatu — satu kontrak untuk semua halaman daftar.
4. **Judul halaman bisa diketuk di mobile** (§3.5: subtitle muncul saat judul diketuk, desktop tidak
   berubah). Nexfiber belum punya; sudah terbukti di NetBackup. Adopsi untuk halaman dengan subtitle
   (mis. Dashboard "Diperbarui …", Detail OLT/ONU).

### P3 — Penyelarasan kecil
5. **Input mobile 16px** (§4.6, cegah auto-zoom iOS). Form Nexfiber sekarang 32px desktop / 48px mobile;
   perlu verifikasi `font-size` input di <768px — bila masih 13–14px, naikkan ke 16px di mobile saja.
6. **Tangga bobot** (§2.2: 800 hanya angka besar/H1 → 700 judul → 600 tombol/label → 400 body).
   Nexfiber sudah dekat (metric 600 mono, text-xl 600, tombol 600); audit sekali jalan untuk memastikan
   tidak ada judul yang memakai bobot di luar tangga ini.
7. **Kontrak lipat tunggal**: vibekoding memakai satu handler global `[data-toggle]`/`.m-item`.
   Nexfiber (React) memakai komponen lokal per halaman — itu wajar. Yang diadopsi adalah **kontraknya**:
   ketuk judul → buka; ketuk link/tombol/input di dalam item **tidak** melipat; `aria-expanded` di-toggle.
   Verifikasi `MobileCard`/`TableCard` sudah memenuhi kontrak ini.

### Tidak diadopsi — diputuskan Nexfiber menang (dengan alasan tercatat)
| Pola vibekoding | Keputusan | Alasan |
|---|---|---|
| Badge pill (999px, uppercase) §4.1 | **Tolak** | DESIGN §6: "Tidak ada pill"; StatusBadge = teks + titik 6px + radius-sm (keputusan terkunci) |
| Font Inter, body 16px §2.2 | **Tolak** | IBM Plex Sans 13px default adalah keputusan produk (kepadatan NOC, DESIGN §4) |
| Panel kaca buram menu mobile §4.5 | **Tolak** | Selera owner: tanpa glass/blur (DESIGN §7, §11.1 tanpa blur) |
| Top bar desktop 60px, link aktif warna saja §4.8 | **Tidak perlu** | Header Nexfiber 56px + garis bawah 2px fiber sudah setara & lebih spesifik |
| Breakpoint lipat 768px | **Pertahankan 1024px** | Wilayah sentuh Nexfiber <1024px (audit 2026-10-28); kartu <768px tetap |
| Skala primer 50–900 | **Tidak wajib** | Token peran tunggal Nexfiber sudah teruji kontras; skala hanya bila butuh varian |
| `user-scalable=no`, swipe-action, infinite scroll §6 | **Tetap ditolak** | Sudah ditolak kedua belah pihak |

## 3. Rencana penerapan (menunggu perintah "lanjut")

- **Tahap 1 — komponen baru (tanpa ubah visual yang ada):** Toast (P1.1) + Switch standar (P1.2).
  Verifikasi: build + check + screenshot pola di satu halaman.
- **Tahap 2 — pola interaksi:** filter collapsible "N aktif" (P2.3) + judul diketuk mobile (P2.4).
- **Tahap 3 — audit kecil:** font input mobile 16px (P3.5) + tangga bobot (P3.6) + kontrak lipat (P3.7);
  hasil audit dicatat di DESIGN.md bila ada perubahan token.
- VoIP tidak disentuh (instruksi user masih berlaku). Tidak ada perubahan backend.
- Setelah tahap 1–3: commit + push **hanya** atas perintah eksplisit (tidak ada standing authorization).

## 4. Skill vibekoding yang relevan ke depan

Dari 12 skill di `~/workspace/vibekoding/skills/`, yang melengkapi 4 skill Nexfiber yang sudah
terinstal: `desain-bersih` (anti-slop), `selera-visual` (art direction), `standar-web` (audit a11y/UX),
`micro-interaction`, `base-design-system`. Bisa dipakai berdampingan saat review tahap 3.
