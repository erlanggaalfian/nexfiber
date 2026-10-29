# DESIGN.md: Nexfiber

Dokumen arah desain dan tata letak layar. Pasangan `PRD-FINAL.md` (v4): PRD menentukan **apa** isi tiap halaman (§3.3–§3.7), dokumen ini menentukan **bagaimana tampilannya**. Bila bertentangan soal tampilan, dokumen ini yang menang; soal fitur/hak akses, PRD yang menang. `antislop.md` dipakai sebagai filter di atas keduanya.

Selera pemilik produk (wajib diikuti):
- **Simpel, padat, modern.** Satu layar menjawab satu pekerjaan.
- **Tanpa teks penjelas panjang.** Label pendek; keterangan hanya bila mencegah salah aksi, maksimal satu baris.
- **Tanpa popup bantuan / tooltip "?"** di samping label.
- **Tanpa garis pemisah berlebih.** Pemisahan memakai jarak dan latar; garis hanya di tabel dan tepi panel.
- **Tanpa penomoran berulang** (tidak ada "1. … 2. …" di judul section, langkah, atau kartu).
- Tata letak dikerjakan **persis** seperti wireframe §11–§12; elemen yang sejajar di wireframe harus sejajar di build.

## 1. Identitas

- **Produk**: konsol operasional manajemen OLT/ONU untuk tim NOC ISP fiber (GPON).
- **Pengguna**: Superadmin, Admin (pemilik OLT), User (operator & teknisi lapangan). Internal, bukan publik.
- **Pekerjaan layar**: menemukan ONU/OLT yang bermasalah, membaca angka sinyal, dan mengambil satu tindakan (otorisasi, reboot, ubah speed/VLAN).
- **Karakter**: panel instrumen, bukan brosur. Padat, tenang, terbaca saat mata lelah jam 3 pagi.
- **Motif identitas**: *signal bar*: balok horizontal 3 segmen setinggi 4px yang memetakan Rx power ke bucket (Good / Fair / Weak / Critical / LOS, sama dengan PRD §3.4.2). Dipakai konsisten di tabel, kartu detail, dan ringkasan OLT. Kartu Level Sinyal Rx di Detail ONU memakai segmen yang sama di bawah angka, bukan hanya badge kata. Alasan: satu bahasa visual untuk satu-satunya angka yang paling sering dibaca operator, dan ia membawa informasi (bukan dekorasi garis warna).
- **Bahasa antarmuka**: Indonesia; nama teknis (ONU, VLAN, PON, SSID, OLT) tetap seperti di CLI. Tombol tutup form = Batal, dialog baca-saja = Tutup.

## 2. Dial

`Dial: ENERGY 1 / RHYTHM 1 / MOTION 2`

- **ENERGY 1**: alasan: aplikasi kerja harian; sapaan visual mengambil perhatian yang seharusnya milik data alarm.
- **RHYTHM 1**: alasan: operator memindai layar yang sama ratusan kali per shift; posisi elemen yang stabil mempercepat muscle memory. Variasi komposisi diizinkan hanya antar jenis layar (dashboard vs tabel vs detail), bukan antar section di dalam satu layar.
- **MOTION 2**: hover/focus/transisi state (seperti sebelumnya) **plus** entrance animation bertujuan (fade+rise saat halaman/kartu/baris pertama muncul, stagger antar kartu) dan depth 3D ringan di kartu/panel saat hover (lift halus, bukan skeuomorphism). Tidak ada gerak abadi/looping (tanpa pulse, tanpa parallax scroll, tanpa particle) — motion selalu berakhir, maksimal sekali per kemunculan elemen. Alasan upgrade dari MOTION 1: entrance/stagger yang pendek (≤500ms, sekali saja) membantu mata menangkap struktur baru tanpa menyerupai alarm; depth hover memberi afforadance "ini bisa diklik" tanpa menambah elemen dekoratif. Lihat §2.1 untuk token presisi. Spesifikasi lengkap di `animation-principles`/`web-design` skill, diterapkan dengan filter antislop (tidak ada animasi tanpa tujuan).

Karakter datang dari tipografi, densitas, motif signal bar, **dan sekarang juga dari depth/motion terkontrol** — bukan dari energi warna atau gerak dekoratif.

### 2.1 Token motion

| Token | Durasi | Easing | Pakai |
|---|---|---|---|
| `motion-micro` | 100ms | `ease-out` | Toggle, checkbox, badge status berubah |
| `motion-hover` | 150ms | `ease-out` | Hover tombol/baris/kartu, depth lift |
| `motion-fade` | 200ms | `ease-out` masuk / `ease-in` keluar | Toast, dropdown, tooltip |
| `motion-panel` | 250ms | `ease-out` masuk / `ease-in` keluar | Drawer, modal, popover |
| `motion-entrance` | 300ms | `ease-out` | Fade+rise 8px saat kartu/section pertama tampil |
| `motion-stagger` | 40–60ms delay/item, maks 5 item | `ease-out` | Urutan kartu ringkasan Dashboard, baris tabel pertama kali termuat |

Aturan: total durasi satu sekuens stagger tidak boleh lebih dari 500ms. Semua token di atas wajib respect `prefers-reduced-motion: reduce` (durasi jadi ~0, tanpa translate). Properti yang dianimasikan dibatasi `opacity`, `transform` (translate/scale) — tidak pernah `width`/`height`/`top`/`left` (hindari layout thrash). Pengecualian yang disengaja: umpan tekan tombol/kartu yang bisa diklik memakai scale 0.98–0.99 selama 150ms, dan bar data (signal/usage) menganimasikan perubahan warna/lebar selama 300ms supaya perubahan data tidak melompat — keduanya tetap berakhir, tanpa animasi looping. Tahap 2 (2026-10-28): transisi warna latar 150ms juga diizinkan untuk baris tabel dan kartu yang berubah warna saat hover, diatur satu kali secara global di CSS (bukan per halaman) supaya semua tabel terasa sama; permukaan bersama (`Panel`, kartu auth, grup Lainnya) memakai entrance yang sama dengan `TableCard` dan halaman lain. Dialog tengah: fade + naik 8px dari titik tengahnya, 200–250ms; overlay ikut fade saat tutup. Stagger tidak boleh bersarang (Dashboard: stagger hanya di dalam strip/baris sinyal, bukan di parent + di dalamnya).

## 3. Palet

Dua warna inti + satu aksen + netral. Netral tidak dihitung sebagai warna inti (R-29).

### Netral (light, default)

| Token | Hex | Pakai |
|---|---|---|
| `--bg-app` | `#F7F6F3` | Latar aplikasi. Alasan: putih hangat mengurangi silau LCD dibanding `#FFFFFF` murni pada shift panjang. |
| `--bg-surface` | `#FFFFFF` | Tabel, panel, kartu. Alasan: kontras halus terhadap `--bg-app` memisahkan bidang tanpa perlu shadow. |
| `--bg-sunken` | `#EFEDE8` | Header tabel, baris zebra opsional, kode blok. |
| `--border` | `#D9D5CC` | Garis tabel dan panel. |
| `--border-strong` | `#8C8476` | Pemisah struktural, batas input (≥3:1 WCAG 1.4.11; dark `#6B6D64`). |
| `--text` | `#1C1B18` | Teks utama. Kontras 17.2:1 di `--bg-surface`, 15.9:1 di `--bg-app`. |
| `--text-muted` | `#5B574E` | Label, satuan, metadata. Kontras 7.2:1 / 6.7:1. |
| `--text-faint` | `#6B675B` | Placeholder saja, tidak pernah untuk data. Kontras 5.7:1 / 5.2:1 / 4.8:1 di `--bg-sunken`. |

### Inti

| Token | Hex | Pakai |
|---|---|---|
| `--ink` | `#1C1B18` | Warna inti 1: teks, ikon, garis. Alasan: grafit kehijauan, bukan hitam netral, agar menyatu dengan latar hangat. |
| `--fiber` | `#0F5C4A` | Warna inti 2: nav aktif, link, judul section, state terpilih. Alasan: hijau tua optik, merujuk serat/konektor APC; bukan biru korporat default dan lolos AA sebagai teks (7.9:1 di putih, 7.3:1 di `--bg-app`). |

### Aksen (dua, dipakai di momen kunci — ditambah satu untuk ekspresi, bukan menggantikan amber)

| Token | Hex | Pakai |
|---|---|---|
| `--amber` | `#B4540A` | Tombol aksi primer komit (Authorize, Reboot, Apply), penanda baris terpilih. Alasan: satu-satunya warna yang berarti "tindakan ini mengubah jaringan"; dilarang muncul di ikon, link, atau latar dekoratif. Teks putih di atasnya 4.98:1 (AA lolos); karena itu label tombol primer minimum 13px/600. Teks di atas amber wajib memakai token `--on-amber`, bukan `text-white` mentah (di dark mode amber jauh lebih terang, putih di atasnya gagal AA). Pengecualian Dashboard saja: sel urgent memakai aksen atas 2px token status (termasuk amber untuk Unconfigured sebagai "perlu tindakan", bukan kegagalan). Aturan tegas (2026-10-29): amber HANYA untuk aksi komit yang mengubah jaringan (Authorize, Reboot, Apply) dan penanda "perlu tindakan" (badge Unconfigured, counter) — dilarang untuk ikon, link, grafik, legend, marker dekoratif, teks peringatan UI (memakai `--st-warn`), atau badge informatif. |
| `--teal-glow` | `#1D8A74` | **Baru.** Satu-satunya tambahan ekspresif: ring tipis 1px di kartu metric Dashboard saat hover (depth, §2.1), dan highlight garis atas 2px pada kartu yang baru menerima data real-time (sekali, hilang 2s). Tidak pernah dipakai di teks atau ikon (hanya border/ring tipis) agar tidak bersaing dengan `--fiber`/`--amber` sebagai bahasa aksi. |

### Status (bahasa data, bukan palet dekorasi)

Dipakai hanya untuk state perangkat, selalu berpasangan dengan teks/ikon (tidak pernah warna saja).

| Token | Hex | Arti | Kontras |
|---|---|---|---|
| `--st-up` | `#1F6B3A` | Online, Rx normal | 6.5:1 |
| `--st-warn` | `#8A5B00` | Perangkat mendekati ambang (Rx mendekati ambang, high CRC) + peringatan UI | 5.9:1 |
| `--st-down` | `#A02020` | LOS, Dying Gasp, offline | 7.7:1 |
| `--st-idle` | `#5B574E` | Belum diotorisasi, disabled | 7.2:1 |

Kontras diukur terhadap `--bg-surface` `#FFFFFF`; semua tetap di atas 4.5:1 terhadap `--bg-app` `#F7F6F3`. Konsolidasi peringatan UI (2026-10-29): semua teks peringatan UI (banner koneksi terputus, catatan "Belum didukung", pesan diagnostik, peringatan batas export) masuk ke `--st-warn` lewat util `text-warn`/`bg-warn`/`border-warn` — maknanya diperluas jadi "peringatan UI + perangkat mendekati ambang"; amber tidak pernah dipakai untuk peringatan.

Ambang Rx ONU (GPON, dBm) yang memetakan status, sebagai nilai default yang dapat dikonfigurasi per OLT:

| Rentang | Status |
|---|---|
| -8 s/d -25 | **Good** (`--st-up`, 3 segmen) |
| di bawah -25 s/d -27 | **Fair** (`--st-warn`, 2 segmen) |
| di bawah -27 s/d -28 | **Weak** (`--st-warn`, 1 segmen) |
| -28 ke bawah, atau di atas -8 (terlalu kuat) | **Critical** (`--st-down`, 1 segmen) |
| LOS / tanpa nilai | kosong + teks `LOS` |
| tanpa sinyal / LOS / Dying Gasp | down (`--st-down`, label berbeda) |

Alasan: ambang teknis ditulis di DESIGN.md supaya warna tidak pernah ditentukan ad hoc di dalam komponen, dan supaya operator tahu angka yang dipakai UI sama dengan angka di tiket.

### Dark theme

Dark bukan default, tapi wajib ada dan wajib berfungsi penuh (R-21, R-34). Alasan: shift malam di ruang NOC gelap adalah kebutuhan nyata, bukan tren.

| Token | Hex |
|---|---|
| `--bg-app` | `#131412` |
| `--bg-surface` | `#1B1C19` |
| `--bg-sunken` | `#232420` |
| `--border` | `#33352F` |
| `--text` | `#E8E6DF` (13.7:1) |
| `--text-muted` | `#A9A69C` (7.0:1) |
| `--fiber` | `#4FB79B` |
| `--amber` | `#E08A3C` |
| `--teal-glow` | `#3FD1B0` |
| `--st-up` | `#56B870` |
| `--st-warn` | `#D9A33A` |
| `--st-down` | `#E4707A` |
| `--st-idle` | `#8E8B82` |

Toggle: `Sistem / Terang / Gelap`, tersimpan per browser (localStorage) — bukan per pengguna (kolom per pengguna belum ada; itu pekerjaan backend). Tema diterapkan saat load dari nilai tersimpan, default awal Sistem, termasuk di halaman Login/Setup. Tabel gelap juga memuat `--border-strong: #4a4c45` dan `--text-faint: #8e8b82` (nilai yang sudah dipakai kode), serta token teks-di-atas-aksen `--on-amber` (terang `#ffffff`, gelap `#1b1c19`) dan `--on-fiber` (terang `#ffffff`, gelap `#131412`): tombol isi di dark mode memakai teks token ini, bukan putih. Keduanya diuji kontras sebelum rilis.

### Hierarki tombol solid

- `fiber` solid = CTA utama standar (Tambah / Simpan non-jaringan).
- `primary` (`--amber`) solid = aksi komit ubah jaringan saja (Authorize, Reboot, Apply, dan sejenisnya).
- `dangerSolid` = aksi destruktif.
- `secondary` / `quiet` = aksi sekunder dan pendukung.
- Satu baris aksi = satu tombol solid dominan. Bila satu baris/layar memuat dua tombol solid yang bersaing, yang bukan aksi komit diturunkan ke `secondary`. Definisi varian di `button.tsx` tidak berubah — aturan ini soal pemakaian per halaman.

### Larangan palet

Tanpa gradien sebagai warna primer, tanpa latar radial, tanpa background grid/blueprint, tanpa glow menyebar (box-shadow blur besar berwarna). Alasan: tidak ada hierarki yang dilayani; di layar penuh angka, efek itu hanya menambah noise. Pengecualian tunggal (§2.1, `--teal-glow`): ring/garis tipis 1–2px saat hover/update data — ini sinyal state, bukan dekorasi, dan dibatasi ukurannya persis supaya tidak menjadi glow.

## 4. Tipografi

| Peran | Font | Alasan satu baris |
|---|---|---|
| UI / teks | **IBM Plex Sans** | Dirancang untuk antarmuka teknis, tinggi-x besar, angka tabular bawaan, dan bukan font default model. |
| Angka & identifier | **IBM Plex Mono** | Serial ONU, MAC, PON port, dBm, VLAN butuh lebar karakter tetap supaya kolom sejajar dan salah baca `0/O` turun. |

Fallback: `ui-sans-serif, system-ui` dan `ui-monospace, SFMono-Regular`.

Skala (rem, root 16px):

| Token | Size / line-height | Weight | Pakai |
|---|---|---|---|
| `text-xs` | 11px / 16px | 500 | Label kolom, satuan, meta |
| `text-sm` | 13px / 18px | 400 | Isi tabel, body padat (default aplikasi) |
| `text-base` | 14px / 20px | 400 | Teks form, body panel |
| `text-lg` | 16px / 22px | 600 | Judul panel |
| `text-xl` | 20px / 26px | 600 | Judul halaman |
| `text-metric` | 28px / 32px | 600, mono, tabular | Angka tunggal yang dibaca dari jauh |

Aturan:

- Default aplikasi 13px, bukan 16px. Alasan: layar kerja yang menampilkan 40+ baris sekaligus; 16px memaksa scrolling yang menambah waktu pencarian.
- Uppercase hanya untuk label kolom tabel, tracking `0.02em` maksimum. Alasan: label pendek butuh pembeda dari isi; tracking lebar adalah gaya, bukan keterbacaan.
- Semua angka memakai `font-variant-numeric: tabular-nums`.
- Tanpa heading mono berukuran besar. Alasan: mono di sini adalah fungsi (penjajaran data), bukan estetika terminal.

## 5. Spacing

Basis 4px. Skala: `4, 8, 12, 16, 24, 32, 48`.

| Konteks | Nilai |
|---|---|
| Padding sel tabel | `12px 12px` (basis `.tbl`; varian lapang `--roomy` vertikal `16px`) |
| Tinggi baris tabel (default) | `42px` (teks 18px + padding vertikal 24px) |
| Tinggi baris tabel (lapang, `--roomy`) | `50px` (teks 18px + padding vertikal 32px) |
| Padding panel/kartu | `16px` |
| Jarak antar panel | `12px` |
| Padding halaman | `16px` (desktop), `12px` (<1024px) |
| Jarak antar grup form | `24px` |
| Gap label ke input | `4px` |

Alasan: ritme spasi ketat (12/16) menjaga kepadatan informasi; jarak besar (24/32) disimpan hanya untuk memisahkan grup form dan batas section di layar detail, sehingga spasi tetap membawa arti struktur.

## 6. Border radius

Tiga tingkat, bukan satu.

| Token | Nilai | Pakai | Alasan |
|---|---|---|---|
| `radius-0` | `0` | Sel tabel, header tabel | Grid data dibaca sebagai matriks; sudut membulat memecah garis baca. |
| `radius-sm` | `3px` | Input, select, tombol, badge status | Cukup untuk menandai elemen interaktif, tidak menghapus bentuk persegi. |
| `radius-md` | `8px` | Popover, dropdown | Lapisan mengambang kecil tetap 8px agar tidak terlihat seperti kartu. |
| `radius-lg` | `12px` | Panel, kartu, modal, bottom sheet (sudut atas) | Lapisan permukaan utama. Dipakai sejak de-boxing 2026-10-28: radius 8px + border penuh di semua permukaan membuat seluruh aplikasi terasa kotak; 12px + hairline lebih lembut tanpa mengubah layout. Jangan menulis angka radius lain per komponen — pakai token ini. |
| `radius-nav` | `16px` | Indikator navigasi bawah | Satu-satunya bentuk membulat penuh di app (lihat §11.1). |

Tidak ada pill. Alasan: bentuk kapsul menghapus perbedaan antara badge, tombol, dan input di layar yang penuh kontrol kecil. Pita status history memakai `radius-sm`, bukan pill.

**De-boxing (2026-10-28, keluhan user "masih terkesan kotak-kotak"):** kartu/panel memakai `rounded-lg` + hairline `border-line/60` (bukan border penuh `--border`), sehingga tepi lebih lembut di terang dan tetap terbaca di gelap. Header Panel tanpa garis `border-b` (judul + jarak sudah cukup sebagai pemisah). Larangan bersarang: tabel/kartu/daftar di dalam kartu tidak menggambar border penuh sendiri — pembungkus tabel desktop di dalam Section, daftar inset `bg-sunken`, dan kartu port mobile di dalam Section kehilangan bordernya sendiri (atau hanya memakai hairline bila memang daftar mandiri).

**Audit menyeluruh 2026-10-28 (keluhan kedua user, sama):** hierarki radius ditegaskan — kartu/modal `lg` (12px) > kontrol (tombol, input, select, popover, kontainer `VlanMulti`) `md` (8px) > chip/badge/elemen kecil `sm` (3px) > pill navigasi bawah `nav` (16px); kontrol `rounded-sm` (3px) di atas kartu `rounded-lg` adalah sumber kesan kotak yang tersisa dan sudah disamakan ke `md`. Di dalam kartu berborder, elemen anak tidak memakai border penuh sendiri: pakai latar `sunken/20` tanpa border; area grafik di dalam kartu inset memakai `bg-surface` tanpa border. Pengecualian §7 yang baru: `Panel` memakai `shadow-xs` permanen yang hemat (lihat §7) — satu-satunya pengecualian dari larangan bayangan permanen, diputuskan karena user dua kali menilai hasil tanpa shadow belum modern; tidak ada shadow baru yang kuat dan tidak ada glow. `TableCard` dan `MobileCard` TIDAK lagi memakai `shadow-xs` sejak bahasa tabel berbasis pembatas 2026-10-29 (lihat §8).

## 7. Shadow & depth

Dua level shadow untuk elevasi nyata (dropdown, modal), **plus** satu level depth-hover baru untuk motif 3D ringan di kartu interaktif (§2.1 MOTION 2).

| Token | Nilai | Pakai |
|---|---|---|
| `shadow-overlay` | `0 4px 12px rgba(28,27,24,0.14)` | Dropdown, popover, context menu |
| `shadow-modal` | `0 12px 32px rgba(28,27,24,0.22)` | Dialog, drawer |
| `shadow-hover-lift` | `0 6px 16px rgba(28,27,24,0.12)` + `translateY(-2px)` | Kartu metric Dashboard, kartu Settings saat `:hover`/`:focus-visible`, transisi `motion-hover` (150ms) |
| `shadow-xs` | `0 1px 2px rgba(28,27,24,0.06)` | **Satu-satunya** shadow permanen yang diizinkan: `Panel` (audit menyeluruh 2026-10-28; di tema gelap di-override ke hitam 0.35 karena nilai terang tidak terlihat di atas permukaan gelap). `TableCard`/`MobileCard` dikeluarkan dari pengecualian ini sejak bahasa tabel berbasis pembatas 2026-10-29 (§8) |

Panel, kartu statis, tabel, dan header tetap **tidak** memakai shadow saat diam — KECUALI `Panel` di atas yang memakai `shadow-xs` hemat; tabel dan daftar mobile tidak memakai shadow sama sekali sejak bahasa pembatas 2026-10-29 (§8); pemisahan selain itu tetap memakai `--border` dan perbedaan latar (layer `--bg-surface`/`--bg-sunken`, lihat §3 untuk depth lewat warna). `shadow-hover-lift` HANYA aktif saat interaksi (hover/focus), bukan status diam — alasan: elevasi harus berarti "ini responsif", bukan hiasan permanen. Nilai shadow di tema gelap lebih pekat (overlay 0,35, modal 0,5); shadow tetap hitam netral, bukan glow berwarna. Popover/dropdown memakai `shadow-overlay`, bukan `shadow-modal` (yang hanya untuk dialog).

Fokus: `outline: 2px solid var(--fiber); outline-offset: 1px` di light, `--amber` di dark. Tidak pernah `outline: none` tanpa pengganti. Item dropdown yang difokuskan/disorot keyboard memakai outline 2px token fokus di samping latar sunken, bukan hanya perubahan warna latar.

## 8. Komponen dasar

### Tombol

| Varian | Tampilan | Pakai |
|---|---|---|
| Primer | isi `--amber`, teks `--on-amber`, radius-sm, hover `opacity-90` | Satu per layar, untuk aksi yang mengubah jaringan |
| Sekunder | border `--border-strong`, teks `--ink`, hover `bg-sunken` | Aksi aman (Export, Refresh, Filter) |
| Tenang | teks `--fiber`, tanpa border, hover underline | Aksi dalam baris tabel |
| Destruktif | isi `--st-down` untuk aksi utama destruktif (Delete, Restore factory, dan aksi yang menghapus setelan pelanggan), border `--st-down` untuk varian garis, konfirmasi wajib | Deauthorize, Factory reset, Hapus user |

Tinggi: 28px (dalam tabel), 32px (default), 40px (form submit). Tap target mobile minimum 44px. Satu aturan hover per keluarga (isi: opacity-90; garis: bg-sunken; tenang: underline) — primer amber tidak boleh tanpa hover.
Tanpa panah dekoratif di tombol. Alasan: tidak ada tombol di aplikasi ini yang arah visualnya membantu.

### Badge status

Teks + titik 6px berwarna status, radius-sm, tanpa glow, tanpa uppercase lebar, tanpa animasi pulse. Titik menandai state perangkat nyata (R-31). Satu-satunya elemen yang boleh "berkedip" adalah banner alarm kritis baru, sekali selama 2 detik lalu berhenti. Alasan: perhatian ditarik saat kejadian, bukan terus-menerus. Default di tabel adalah berlabel (teks di samping ikon); ikon-saja hanya bila ruang terbukti tidak cukup. Pengecualian atas permintaan user (2026-10-28): kolom Status tabel Configured ikon-saja, keterangan lengkap muncul saat hover (atribut title StatusBadge) dan tetap tersedia untuk pembaca layar (sr-only); kartu mobile Configured tetap berlabel karena sentuhan tidak punya hover. Pasangan status yang mudah tertukar wajib berikon berbeda (offline ≠ unreachable, dying-gasp ≠ power-off).

### Signal bar (motif)

Balok lebar 48px tinggi 4px, radius 0, terbagi jadi segmen terisi sesuai bucket Rx, warna mengikuti token status, dengan nilai dBm mono di sebelahnya. Selalu berdampingan dengan angka, tidak pernah menggantikan angka. Alasan: operator butuh nilai eksak untuk tiket; bar hanya mempercepat pemindaian. dBm ditampilkan 1 desimal di semua permukaan UI (data mentah tetap utuh). Satu komponen `Bar` bersama untuk semua bar persentase (UsageBar, sync, metric OLT) dengan transisi lebar 300ms yang sama.

### Panel

`Panel` = header sub-panel (uppercase text-xs muted); `Block`/`Section` = header section halaman (base bold fiber). Keduanya sengaja berbeda level, jangan disatukan. `Panel` default padding `p-4`.

### Tabel

Sumber kebenaran ada di `frontend/src/styles/index.css`, bagian TABEL TERPUSAT — jangan menulis ulang padding/border/hover tabel per halaman. Halaman hanya memakai class di bawah (aturan basis ditulis dengan `:where()` supaya utility per-sel seperti `text-center`, `font-mono`, `hidden lg:table-cell`, `w-[...]` tetap bisa meng-override):

Prinsip (arahan user 2026-10-29, menggantikan bahasa frameless dari putaran sebelumnya atas persetujuan contoh kartu Gemini 2026-10-29): tabel disajikan dalam SATU kartu lembut. Bahasa frameless sebelumnya (tabel tanpa bingkai) diganti karena contoh yang disetujui user memakai kartu lembut — dan kartu itulah yang dibaca sebagai modern. Kontainer kartu: `rounded-lg` (padanan `rounded-xl` contoh; `rounded-xl` tidak ada di tema yang dibatasi token ini), `border-line`, `bg-surface`, `shadow-xs` (padanan `shadow-sm` contoh; `shadow-sm` tidak ada di tema ini), `overflow-hidden`, di atas latar halaman app. Di dalam kartu: header berlatar tint `sunken` dengan label uppercase tracking-wider semibold muted dan satu garis bawah `line-strong`; baris hanya hairline antar-baris; sel lega px-6 py-4. Modern dicapai lewat struktur, ruang, dan tipografi — tanpa gradient, tanpa glass, tanpa glow, tanpa pulse/animasi loop. Token contoh (gray/blue) TIDAK dipakai: seluruh bahasa ini memakai token Nexfiber (app/surface/sunken/line/line-strong/ink/muted/fiber).

- `.tbl` — basis semua tabel: `border-separate` + `border-spacing: 0`, lebar penuh, isi token aplikasi 13px/18px; header token aplikasi 11px/16px, warna `--text-muted`, semibold, uppercase, tracking-wider, latar tint `--bg-sunken`; sel padding `1rem` vertikal dan `1.5rem` horizontal (px-6 py-4 ala contoh), rata kiri, `vertical-align: middle`. Header dipisah oleh SATU garis yang jelas (`border-bottom` 1px `--border-strong`); garis antar-baris hanya hairline lewat sel (`border-bottom` 1px `--border`, baris terakhir tanpa garis). Kombinator anak (`>`) supaya tidak bocor ke tabel bersarang di dalam sel. Dipakai semua tabel, termasuk `TableCard`. `TableCard` (`frontend/src/components/crud.tsx`, satu-satunya pembungkus tabel daftar) memakai class `tbl`; section-nya adalah kartu lembut (`entrance overflow-hidden rounded-lg border border-line bg-surface shadow-xs`) yang juga menampung cabang daftar mobile. Checkbox header/baris `size-5` (20px, kompromi kerapatan vs keterjangkauan, lihat §9). Aksi dalam baris memakai teks tautan tenang warna fiber (`variant="quiet"`), bukan tombol dan bukan biru contoh — termasuk aksi destruktif (Hapus/Nonaktifkan di Settings), yang isyarat merahnya hilang dari baris tetapi dialog konfirmasinya tetap ada (keputusan koordinator 2026-10-29, bisa dibalik bila user ingin isyarat destruktif dipertahankan sebagai tautan merah). Token `cell` di `crud.tsx` dipertahankan untuk halaman yang masih memakainya; `TableCard` sendiri tidak lagi memakainya karena padding sel sudah diatur `.tbl`.
- `.tbl--fixed` — `table-layout: fixed`; dipakai bila lebar kolom harus patuh pada lebar yang ditentukan, bukan melebar mengikuti isi. Contoh: tabel Eth/WiFi dan tabel Speed Profile di OnuDetail.
- `.tbl--roomy` — padding vertikal `1.25rem`, horizontal tetap `1.5rem`; dipakai tabel yang butuh napas lebih, contohnya Eth/WiFi OnuDetail.
- Kartu pembungkus per tabel (satu kartu lembut yang sama, bukan gaya baru per halaman): `TableCard` (agen komponen, kartu section); section OLT Dashboard (judul kartu pola header: `bg-sunken` uppercase tracked muted + `border-line-strong`, padding px-6 py-4 sejajar kolom tabel); pembungkus tabel UserManagement; OltDetail tab Monitoring "Port PON" dan tab Konfigurasi "Kartu" (Panel pembungkusnya dihapus menjadi section + kepala polos, agar tidak bingkai ganda dengan kartu TableCard); Section/Block OnuDetail (bingkai diseragamkan ke kartu baru — `border-line` + `shadow-xs` — header fiber-bold dipertahankan, karena komponennya lokal halaman itu dan dipakai bersama section non-tabel); tabel ONU di dalam SplitterDrawer sengaja TANPA kartu sendiri karena sudah berada di dalam modal berbingkai.
- Sel utama dua baris: hanya bila data sel itu memang punya baris kedua alami (Eth/WiFi OnuDetail: nama port semibold + identifier mono faint di bawahnya; label "Terakhir ditulis Nexfiber" dan fallback yang sudah ada dibiarkan apa adanya). Jangan mengarang subjudul, jangan memindah data antar-kolom (nama pelanggan Configured tidak ditumpuk dengan serial karena serial adalah kolomnya sendiri), jangan menambah kolom.
- Adaptasi dari contoh yang diputuskan parent 2026-10-29 (dicatat agar bisa dibatalkan user): (1) model separate dipertahankan, bukan collapse contoh (dilarang DECISIONS.md); (2) header tidak pernah sticky; (3) StatusBadge bukan pill badge contoh (titik + label + ikon pembeda tetap, Configured tetap ikon-saja); (4) mobile tetap daftar ber-pembatas, bukan horizontal scroll contoh; (5) Configured tetap wrap; (6) token Nexfiber, bukan gray/blue contoh; (7) `rounded-lg`/`shadow-xs` sebagai padanan `rounded-xl`/`shadow-sm` contoh yang tidak ada di tema.
- Modifier yang DIHAPUS TOTAL (2026-10-29, jangan dihidupkan lagi): `.tbl--sticky` dan `.tbl--inset`. Header tabel TIDAK PERNAH sticky — dilarang `position: sticky` di `th`/`thead` atau mekanisme apa pun yang menutupi baris data (putusan terkunci DECISIONS.md 2026-10-29; bila header "harus menempel" diminta lagi, diskusikan dulu dengan user). `.tbl--inset` tidak lagi membedakan apa pun: semua tabel kini berada di dalam kartu, jadi tidak ada lagi varian tanpa-bingkai yang perlu ditandai. (Bahasa frameless putaran sebelumnya sudah diganti total oleh bahasa kartu; jangan menghidupkan kembali aturan frameless.) Variabel `--tbl-sticky-top` ikut dihapus (tidak ada pemakai lain; header aplikasi di `Layout.tsx` memakai calc literal sendiri).
- Jangan kembali ke `border-collapse`: di model collapse, garis dan perilaku header ditangani Chrome secara tidak andal (baris menumpuk/ghost di atas header, laporan 2026-10-28). Di model separate, border di `<tr>` diabaikan browser, jadi garis header dan garis antar-baris digambar lewat sel.
- Pengecualian yang dipertahankan, jangan diseragamkan: (1) Configured memakai WRAP (`break-words`) untuk nama pelanggan, OLT, splitter/ODP, zone, dan kolom panjang lain di tabel DAN daftar mobile — BUKAN `truncate`; aturan `truncate` umum di bawah tetap berlaku untuk tabel lain. (2) Kolom Status tabel Configured tetap ikon-saja (keterangan lengkap di `title` + `sr-only`, lihat aturan badge status); kartu mobile Configured tetap berlabel karena sentuhan tidak punya hover. (3) Daftar mobile ber-pembatas sebagai ganti tabel di bawah 768px (cabang `card` `TableCard` + `MobileCard`): container memakai `divide-y divide-line/60` (pembatas antar baris, bukan kotak per baris), tiap `MobileCard` tanpa bingkai/latar/shadow sendiri dan tanpa tinggi minimum, padding vertikal `py-3`, dan kini berada di dalam kartu tabel (bukan kartu per baris); perilaku klik + keyboard dan press scale 0.99 untuk varian yang bisa diklik dipertahankan. (4) Kolom yang disembunyikan di breakpoint tertentu (mis. kolom sekunder di 1024–1279px, lihat §9; utility `hidden …:table-cell` yang sama wajib dipakai di `<th>` dan `<td>` halaman itu). (5) Hover baris kini dari `.tbl` (lihat di bawah), bukan class per baris/per halaman.
- Sel tabel yang nilainya bisa panjang (nama pelanggan, nama OLT/splitter/zone, keterangan log) wajib dibungkus `span` block `truncate` dengan `max-w` eksplisit dan atribut `title` berisi nilai penuh. Truncate langsung di `<td>` tidak boleh dipakai: pada layout tabel auto ia tidak menahan kolom melebar.
- Virtualisasi wajib di atas 200 baris (ambang dihitung dari baris yang benar-benar ter-mount: `TableCard` me-mount dua cabang — kartu mobile + baris tabel — sehingga 100 baris data = 200 baris ter-render; di atas ambang itu hanya 50 baris pertama yang dirender, lalu sentinel menambah 50 baris tiap kali pengguna mendekati ujung).
- Zebra mati secara default; pemisah baris memakai garis 1px `--border` (header memakai `--border-strong`, lihat di atas). Alasan: zebra menambah getaran visual saat scroll cepat.
- Hover baris: latar `--bg-sunken`, dari `.tbl` sendiri (bukan class per baris/per halaman). Baris terpilih: latar `--bg-sunken` + garis kiri 2px `--amber` (penanda state nyata, bukan dekorasi).
- Pengurutan: indikator panah kecil pada kolom aktif saja.
- Select-all ada di header kolom pertama, bukan di bawah tabel.
- Pemicu filter setinggi 32px, sama dengan input filter Settings.

### State data (wajib di setiap tampilan data)

| State | Isi |
|---|---|
| Kosong (belum ada data) | Sebab + satu aksi: "Belum ada OLT terdaftar. Tambahkan OLT untuk mulai menarik data ONU." |
| Kosong (filter) | "Tidak ada ONU yang cocok dengan filter ini." + tombol Hapus filter |
| Loading | Skeleton baris setinggi baris asli, maksimal 8 baris, plus teks "Menarik data dari OLT ...". Skeleton Dashboard meniru bentuk strip + baris sinyal + tabel, bukan bar generik; kartu grafik memakai varian skeleton grafik (blok + baris sumbu), tanpa shimmer/pulse |
| Error | Penyebab + tindakan: "Gagal terhubung ke [nama OLT] (timeout 10s). Coba lagi atau periksa jalur manajemen." + tombol Coba lagi |
| Sebagian gagal | Banner di atas tabel: "3 dari 12 OLT gagal dipolling. Data di bawah mungkin kedaluwarsa." + daftar OLT |

### Data placeholder

Selama belum terhubung ke perangkat nyata, sel kosong dibiarkan kosong atau diberi `[DATA NYATA]`. Dilarang mengisi tabel dengan serial/pelanggan/angka Rx karangan yang terlihat realistis.

## 9. Breakpoint

| Lebar | Perilaku |
|---|---|
| >= 1280px | Header penuh (semua menu tampil), konten max-width 1440px di tengah |
| 1024 s/d 1279px | Header penuh, label "● Sistem aktif" menyusut jadi titik saja, kolom tabel sekunder disembunyikan. Urutan sembunyikan: Configured — Splitter, lalu Zone, lalu Rx OLT; Interfaces — Media, lalu Duplex; Kartu — HW, lalu SW. Status, identitas, PON, dan Rx ONU selalu terlihat |
| 768 s/d 1023px | Menu header hilang, diganti **navigasi bawah** (§11.1); header jadi top bar ringkas |
| < 768px | Sama dengan di atas + tabel jadi daftar ber-pembatas (§12.10), aksi lewat bottom sheet, target sentuh 48px |

Tanpa overflow horizontal di level halaman; scroll horizontal hanya di dalam container tabel.

**Target sentuh mengikuti navigasi, bukan breakpoint kartu (audit 2026-10-28):** selama navigasi bawah tampil (< 1024px, `lg`), semua kontrol interaktif minimal 44–48px. Jangan memakai `md:` (768px) untuk mengecilkan target sentuh — 768–1023px masih wilayah sentuh. **Safe-area:** tinggi top bar mobile memakai `calc(3.5rem + env(safe-area-inset-top))` (calc literal di `Layout.tsx`; header tabel TIDAK PERNAH sticky sejak 2026-10-29, jadi tidak ada lagi offset sticky `<th>` maupun variabel `--tbl-sticky-top` — keduanya dihapus, lihat §8); padding bawah konten halaman tab memakai `calc(6rem + env(safe-area-inset-bottom))` agar tidak tertutup bottom nav di HP ber-notch; bar aksi sticky mobile (bulk bar, Reboot/Resync) memakai padding bawah `calc(… + env(safe-area-inset-bottom))`, bukan angka mentah. Bar aksi bawah ini bukan header tabel dan dipertahankan. **Pengecualian yang tetap berlaku:** tombol hapus `FilterChip` dikecualikan dari target 44px penuh (tombol ✕ ~18px) agar chip tidak membengkak; checkbox pilih tabel/kartu memakai 20px sebagai kompromi kerapatan vs keterjangkauan. **Urutan footer pop up di mobile (kolom):** aksi utama, batal, destruktif terakhir — diwujudkan lewat order mobile di footer shell (DOM-nya batal dulu, visualnya utama dulu).

## 10. Aksesibilitas

- Header punya `skip link` "Langsung ke konten" untuk keyboard; menu header adalah `nav` dengan `aria-current="page"` di menu aktif; dropdown Settings bisa dibuka dengan `Enter`/`↓` dan ditutup `Esc`.
- Kontras teks minimum 4.5:1, teks besar 3:1, sudah diverifikasi pada tabel token di atas untuk kedua tema.
- Status tidak pernah disampaikan oleh warna saja: selalu ada teks dan/atau bentuk.
- Seluruh alur dapat dioperasikan dengan keyboard: `Tab` berurutan sesuai visual, `Enter` membuka baris, `Esc` menutup drawer/modal, `/` fokus ke pencarian, `j/k` pindah baris di tabel.
- Fokus terlihat di setiap elemen interaktif.

## 11. Kerangka aplikasi & header

Tidak ada sidebar. Semua navigasi ada di **header atas**.

```
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◆ Nexfiber │ Dashboard  Unconfigured 3  Configured  Settings ▾  Logs │ [⌕ Cari… ⌘K]  ● Sistem aktif  (EA)▾ │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
  ↑ logo       ↑ menu kiri, rata kiri setelah logo                        ↑ grup kanan, rata kanan
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ Judul halaman                                                   [aksi sekunder] [aksi primer] │  ← baris judul
│ (konten halaman)                                                                              │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Elemen | Spesifikasi |
|---|---|
| Header | Tinggi 56px, sticky, latar `--bg-surface`, garis bawah 1px `--border`, tanpa shadow, tanpa blur |
| Logo | Ikon 20px + "Nexfiber" 15px/600 `--ink`; klik = Dashboard |
| Menu | 13px/500, padding horizontal 12px, jarak antar menu 4px. Normal `--text-muted`; hover `--text` + latar `--bg-sunken` radius-sm; **aktif** `--text` tebal + garis bawah 2px `--fiber` menempel di tepi bawah header |
| Badge Unconfigured | Angka mono 11px di kotak radius-sm latar `--amber` teks `--on-amber`, hanya tampil bila > 0. Satu-satunya badge di header |
| Settings ▾ | Klik (bukan hover) membuka dropdown 240px, `shadow-overlay`, radius-md. Item: ikon Phosphor 16px + label 13px, tinggi 36px. Item Phase 2: teks `--text-faint` + label "Segera" 11px di kanan, tidak bisa diklik. Menu Settings ikut aktif saat berada di `/settings/*`; item dropdown yang sedang aktif memakai latar `--bg-sunken` + teks `--ink` tebal |
| Cari | Kolom cari tidak dirender sampai command palette siap; dilarang mengirim input disabled yang terlihat bisa dipakai. Bila palette sudah ada: input 240px tinggi 32px, placeholder "Cari SN, nama, PPPoE, IP OLT", hint `⌘K` mono di kanan dalam input. Hasil = command palette di tengah layar (lebar 560px), dikelompokkan: ONU · OLT |
| Sistem aktif | Titik 6px + teks 12px. Hijau = worker & poller sehat; amber = tertunda (worker hidup dan ada job antre); merah = mati. Tanpa pulse. Klik = popover status (worker, job antre, poll terakhir) |
| Avatar | Lingkaran 28px berisi inisial (satu-satunya bentuk bulat di app). Dropdown: nama + peran (teks, bukan badge), Ganti password, Tema (Sistem/Terang/Gelap), Logout |
| Baris judul | Judul `text-xl` di kiri, aksi halaman di kanan, satu baris, tinggi 48px, margin bawah 12px. Tanpa breadcrumb, kecuali halaman detail: tautan kecil "← Configured" / "← OLT Management" di atas judul |

Urutan menu dan isi dropdown **tetap**, hanya disembunyikan sesuai peran (PRD §3.7):

```
Settings ▾
  ⚙ OLT Management        (ikon HardDrives)
  ⚙ User Management       (ikon Users)
  ⚙ ONU Types             (ikon Cpu)
  ⚙ Splitters & Zone      (ikon TreeStructure)
  ⚙ Speed Profile         (ikon Gauge)
  ─────────────            ← satu-satunya pemisah: memisahkan fitur Phase 2
  ⚙ VPN Tunnels   Segera  (ikon ShieldCheck)
  ⚙ TR-069        Segera  (ikon Broadcast)
```

Desktop (≥ 1024px) memakai header di atas. Tablet & HP (< 1024px) memakai **navigasi bawah**, lihat §11.1.

Ikon: Phosphor `regular` 16px di menu/dropdown/tombol, 20px di header.

### 11.1 Navigasi bawah (Android / HP / tablet, < 1024px)

Gaya aplikasi Android modern (pola Material 3 navigation bar), tapi tetap memakai token Nexfiber.

```
┌─────────────────────────────────────┐
│ Configured                    ⌕ (EA)│  ← top bar 56px: judul halaman · cari · avatar
├─────────────────────────────────────┤
│                                     │
│  (konten, kartu §12.10)             │
│                                     │
├─────────────────────────────────────┤
│  ⌂        ⊕³        ☰       ≡      ⋯ │
│ Dashboard Unconfig Configured Logs Lainnya │  ← 64px + safe-area bawah
└─────────────────────────────────────┘
```

| Posisi | Tab | Ikon Phosphor | Isi |
|---|---|---|---|
| 1 | Dashboard | `House` | `/` |
| 2 | Unconfigured | `PlusCircle` + badge angka | `/unconfigured` |
| 3 | Configured | `ListBullets` | `/configured` |
| 4 | Logs | `ClockCounterClockwise` | `/logs` |
| 5 | Lainnya | `DotsThreeCircle` | Halaman daftar: grup **Settings** (semua sub-menu sesuai peran) · grup **Akun** (Ganti password, Tema, Logout) |

Spesifikasi:
- Bar: tinggi 64px + `env(safe-area-inset-bottom)`, latar `--bg-surface`, garis atas 1px `--border`, tanpa shadow, tanpa blur.
- Item: ikon 24px di atas label 12px/500, label **selalu tampil** (tidak hanya di tab aktif). Area sentuh penuh 1/5 lebar × 64px.
- **Aktif**: ikon berganti weight `fill`, warna `--fiber`; di belakang ikon ada indikator 56×32px latar `--fiber` 12% radius 16px (satu-satunya bentuk membulat penuh, dipakai sebagai penanda posisi, bukan tombol). Label aktif `--text` 600; tidak aktif `--text-muted`.
- Ganti tab: indikator membesar dari tengah 150ms ease-out; tanpa animasi lain. Hormati `prefers-reduced-motion` (tanpa animasi).
- Badge Unconfigured: angka mono 11px latar `--amber` teks putih, menempel di pojok kanan atas ikon; `99+` bila lebih. Tidak tampil bila 0.
- Ketuk tab yang sedang aktif = scroll ke atas + refresh data.
- Bar **tetap terlihat** saat scroll (posisi stabil lebih penting dari ruang ekstra). Disembunyikan saat keyboard terbuka.
- Bar hanya tampil di 5 halaman utama. Halaman turunan (Detail ONU, Detail OLT, form Otorisasi, sub-menu Settings) memakai top bar dengan tombol **←** dan tanpa navigasi bawah, sehingga tombol aksi bawah (mis. **Otorisasi**) punya tempat sendiri. Tombol back Android mengikuti riwayat yang sama.
- Top bar: judul `text-lg`, avatar (tombol cari dihapus sampai palette siap, seperti §11). Tanpa logo di HP agar judul halaman yang terbaca. Tombol ikon top bar memakai `hover:bg-sunken` seperti permukaan interaktif lain.
- Baris navigasi di Lainnya memakai chevron kanan `--text-faint`; baris Tema dan tombol Logout tidak.
- Pull-to-refresh di Dashboard, Unconfigured, Configured, Logs.
- Aksi primer halaman (mis. **Scan ulang**, **Tambah OLT**) di HP menjadi tombol bulat-sudut 56px di kanan bawah, 16px di atas navigasi bawah. Maksimal satu per halaman.
- Tema: `theme-color` meta mengikuti `--bg-surface` terang/gelap agar status bar Android menyatu.

**Bisa dipasang seperti aplikasi (PWA)**: `manifest.webmanifest` dengan `display: standalone`, ikon 192/512px (maskable), `start_url: "/"`, warna mengikuti token. Pengguna Android memilih "Tambahkan ke layar utama" lalu Nexfiber terbuka penuh layar tanpa bilah browser. Tanpa cache offline: data jaringan harus selalu live. Tidak ada ikon di depan menu header utama (Dashboard…Logs), karena teks sudah pendek dan jelas.

## 12. Tata letak per halaman

Lebar konten maks 1440px, padding 16px. Wireframe di bawah adalah desktop ≥ 1280px; perilaku mobile ditulis di bawah tiap wireframe.

### 12.1 Login `/login` & Setup `/setup`

```
                ◆ Nexfiber
        ┌─────────────────────────┐
        │ Username  [           ] │
        │ Password  [           ] │
        │ [        Masuk        ] │   ← tombol --fiber penuh lebar (bukan amber: tidak mengubah jaringan)
        └─────────────────────────┘
```
Kartu 360px di tengah layar, latar `--bg-app`. Tanpa ilustrasi, tanpa tagline, tanpa "lupa password". Error tampil satu baris merah di atas tombol. Setup memakai kartu yang sama: Username, Nama, Password, Ulangi password, tombol **Buat Superadmin**.

### 12.2 Dashboard `/`

```
Dashboard                                                         Diperbarui 14:02  [↻ Refresh]
┌──────────────┬──────────────┬──────────────┬──────────────────────┐
│ Total OLT    │ ONU Online   │ ONU Offline  │ Unconfigured         │  ← satu strip, 4 sel, dipisah garis 1px
│ 12           │ 4.812        │ 37           │ 3   [Scan baru]      │     angka text-metric mono
│ 11 terhubung │ dari 4.849   │ LOS 21 · DG 9│                      │
└──────────────┴──────────────┴──────────────┴──────────────────────┘
Kualitas sinyal   Critical 14 ▮  Weak 52 ▮  Fair 310 ▮  Good 4.436 ▮       ← satu baris, bukan kartu
┌ OLT ─────────────────────────────────────────────────────────────────────────────────┐
│ Nama OLT   IP          SNMP        ONU on/total   CPU   RAM   Suhu   Aksi            │
│ …          …           ● Up 14:01  412/420        12%   41%   44°C   Monitor         │
└──────────────────────────────────────────────────────────────────────────────────────┘
┌ Aktivitas terakhir ───────────────────────────────────────────── Lihat semua ┐
│ 14:01  [user]  Otorisasi  [SN]  [OLT] · 1/2/3:7   Sukses                     │
└──────────────────────────────────────────────────────────────────────────────┘
```
- Angka di strip & baris sinyal bisa diklik = buka Configured/Unconfigured terfilter.
- Sparkline ONU online 24 jam per OLT ditunda (PRD §3.4.2).
- Contoh angka di wireframe hanya ilustrasi ukuran; build memakai data nyata atau sel kosong.
- Mobile: strip jadi grid 2×2, baris sinyal jadi 2×2, tabel OLT jadi kartu (Nama, SNMP, ONU on/total), aktivitas 5 baris.
- **Motion (§2.1)**: keempat sel strip muncul dengan `motion-entrance` + `motion-stagger` (urutan kiri→kanan, total ≤250ms) hanya saat halaman pertama dimuat, bukan tiap auto-refresh. Setiap sel `shadow-hover-lift` saat `:hover`/`:focus-visible`. Saat auto-refresh (60s) mengubah angka, sel yang berubah dapat garis atas 2px `--teal-glow` sekali, hilang 2s — bukan animasi angka berganti (hindari layout thrash).
- **Triase**: sel urgent di strip/sinyal memakai garis atas 2px token status; sel netral tidak memakai aksen. Dot LOS memakai `--st-down` (bukan idle), dan tiap sel sinyal memakai subline "dari {total}".
- **Tabel OLT**: baris bisa diklik penuh ke Detail OLT; kolom ONU memakai bar 48×4 seperti UsageBar; urutan: OLT tidak online dulu, lalu rasio ONU online terendah. Kartu mobile OLT memakai pola `MobileCard` (press) dan jadi link penuh, tetap 3 baris.
- **Header**: Aktivitas memakai "Lihat semua" ke Logs; baris judul menampilkan waktu poll OLT terakhir (`last_poll_at`), bukan hanya waktu refresh halaman.

### 12.3 Unconfigured `/unconfigured`

```
Unconfigured                                    OLT [Semua ▾]   Scan terakhir 14:02   [↻ Scan ulang]
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ OLT     Shelf  Slot  Port  Nomor seri / MAC   Tipe deteksi   Rx      Terlihat   Aksi  │
│ …       1      2     3     [SN]               [model]        ▮ -21.4  2 mnt     [Otorisasi] │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
Tombol **Otorisasi** adalah aksi tunggal halaman ini, jadi memakai tombol isi fiber (amber tetap dipakai di form saat benar-benar mengirim ke OLT). Kosong = teks + tombol Scan ulang di dalam blok kosong. Mobile: kartu berisi SN (mono, baris pertama), OLT · port, Rx, tombol Otorisasi penuh lebar.

### 12.4 Form Otorisasi `/unconfigured/authorize/:oltId/:serial`

```
← Unconfigured
Otorisasi ONU   [SN] · [OLT] · 1/2/3                          Preset [Tidak ada ▾] [Simpan sebagai preset]
┌ Layanan ─────────────────────────────┐  ┌ Pelanggan ───────────────────────────┐
│ Tipe ONU        [            ▾]      │  │ Nama pelanggan *  [                ] │
│ Download        [            ▾]      │  │ Kontak            [                ] │
│ Upload          [            ▾]      │  │ Alamat            [                ] │
│ VLAN            [            ▾]      │  │ External ID       [                ] │
│ Mode ONU        (•) Routing ( ) Bridging│ │ Zone              [            ▾]  │
│ Mode WAN        [ PPPoE      ▾]      │  │ Splitter [      ▾]  Port [  ▾]       │
│ PPPoE user      [            ]       │  │ Lokasi  [lat] [long] [Gunakan GPS]   │
│ PPPoE password  [            ]       │  └──────────────────────────────────────┘
└──────────────────────────────────────┘
                                                                  [Batal]  [Otorisasi]   ← amber, kanan bawah
```
- Dua kolom sejajar atas (Layanan kiri, Pelanggan kanan); label di kiri input, lebar label 112px.
- Field PPPoE hanya muncul bila Mode WAN = PPPoE; field Mode WAN hanya bila Routing.
- Validasi inline di bawah field, satu baris. Wajib ditandai `*` saja, tanpa teks "wajib diisi" di awal form.
- Setelah klik Otorisasi: tombol jadi status job ("Mengirim ke OLT…"), lalu pindah ke Detail ONU.
- Mobile: satu kolom (Layanan dulu), label di atas input, tombol Otorisasi penuh lebar sticky di bawah layar (navigasi bawah tidak tampil di halaman ini).

### 12.5 Configured `/configured`

```
Configured                                                       [Sync pelanggan] [Export CSV]
[⌕ Nama, SN, alamat, PPPoE…      ]  [OLT ▾][Board ▾][Port ▾][Status ▾][Sinyal ▾][Tipe ▾][Profile ▾][VLAN ▾][Zone ▾][Splitter ▾]  Reset
Status: Offline ✕   Zone: [nama] ✕                                                     ← chip filter aktif
┌───────────────────────────────────────────────────────────────────────────────────────────────┐
│ ☐  Status       Nama pelanggan   SN        OLT · PON        VLAN  Splitter  Zone   Rx ONU    Rx OLT  │
│ ☐  ● Online     …                [SN]      [OLT] · 1/2/3:7   100   …         …      ▮ -22.1   -24.0  │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
3 dipilih   [Reboot] [Ubah speed] [Pindah zone]                     ← bar aksi massal muncul di bawah, sticky
1–50 dari 4.849                                   « ‹ 1 2 3 › »    Tampilkan [50 ▾]
```
- Filter multi-pilih berbentuk tombol dropdown kecil sebaris; dropdown berisi checkbox + kotak cari. Tombol berubah jadi `Status · 2` saat aktif. Filter langsung diterapkan (tanpa tombol Terapkan) dan tersimpan di URL.
- Select-all ada di header kolom pertama, bukan di bawah tabel; di desktop, filter di luar OLT/Status disembunyikan di balik satu disclosure "Filter lainnya"; chips + Reset tetap menjadi catatan filter aktif.
- Baris diklik = buka Detail ONU (tidak perlu tombol Detail per baris).
- Kartu mobile baris 3 = SignalBar + "Terlihat {waktu}" (Zone pindah ke halaman detail).
- Mobile: cari penuh lebar + tombol **Filter** (bottom sheet berisi semua filter); daftar kartu §12.9.

### 12.6 Detail ONU `/onu/:id`

```
← Configured
[Nama pelanggan]   ● Online   [SN] · [OLT] · 1/2/3:7                  [↻ Cek ulang]  [Aksi ▾]
┌ Sinyal ───────────────────────────────────────────┐ ┌ Pelanggan ─────────────── Edit ┐
│ Rx ONU ▮ -22.1   Rx OLT -24.0   Tx 2.3   Jarak 1.8 km│ │ Kontak, Alamat, Zone,          │
│ [ 24 jam | 7 hari | 30 hari ]                       │ │ Splitter · port, External ID,  │
│ ▁▂▂▃▃▂▂▁▁▂▃▃▂  (grafik Rx, ambang sebagai garis putus)│ │ Lokasi (link peta)             │
│ Uptime 12h 4m · Offline terakhir: LOS, 2 hari lalu  │ ├ Perangkat ─────────── Edit ┤
└─────────────────────────────────────────────────────┘ │ Tipe ONU, Preset, Diotorisasi  │
                                                        └────────────────────────────────┘
Status | Running config | Info software | Speed | Mode | Ethernet | WiFi · Segera | TR-069 · Segera
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ (isi tab)                                                                            │
└──────────────────────────────────────────────────────────────────────────────────────┘
```
- Kolom kiri 2/3, kanan 1/3. Panel kanan bertumpuk dalam satu kartu dengan pemisah jarak, bukan garis.
- **Aksi ▾** (kanan atas) berisi kelompok: Reboot, Resync config · Ubah speed, Ubah VLAN, Replace ONU, Nonaktifkan · Restore factory, Hapus (merah, konfirmasi ketik SN). Item yang tidak boleh untuk peran User disembunyikan.
- Tab = teks + garis bawah 2px `--fiber` di tab aktif; tab terpilih tersimpan di URL (`?tab=ethernet`).
- Running config: blok mono `--bg-sunken`, tombol **Salin** di pojok kanan atas.
- Strip identitas satu baris di atas blok Status: nama pelanggan, status, chip SN, link OLT · PON (ini yang dimaksud wireframe di atas; judul halaman yang disembunyikan sebelumnya diganti strip ini).
- Kartu Rx memakai `text-metric` (bukan ukuran di luar token) dan segmen signal bar di bawah angka; grafik Rx memberi label garis ambang di gutter/keterangan dan menampilkan nilai terakhir + waktunya; grafik LIVE memakai sumbu waktu nyata, frame seperti grafik histori, dan memutus garis bila gap > 2× interval poll; pita status memakai `radius-sm`, merah dipecah (LOS/dying-gasp = down, offline/lainnya = warn) dan menampilkan downtime terpanjang + waktunya; field yang belum terbaca ditulis sekali per section ("—" per baris), bukan per baris.
- Mobile: header jadi dua baris (nama + status; SN · port), kolom bertumpuk (Sinyal → Pelanggan → Perangkat), tab jadi scroll horizontal, Aksi jadi tombol penuh lebar sticky di bawah yang membuka bottom sheet. Bar sticky mobile hanya berisi aksi rutin Reboot dan Resync config + anchor "Semua aksi"; aksi destruktif tidak pernah di bar sticky.

### 12.7 Detail OLT `/olt/:id`

```
← OLT Management
[Nama OLT]   ● Terhubung   [IP] · [vendor model]                              [↻ Refresh status]
Monitoring | VLANs | Konfigurasi | Daftar ONU
```
- **Monitoring**: strip 5 sel (Uptime · CPU · RAM · Suhu · ONU on/total); di bawahnya dua tabel berdampingan: Kartu/board (kiri) dan PON port (kanan: port, status, ONU, Tx). Bar metric menganimasikan lebar seperti UsageBar; Suhu tidak punya bar persentase (hanya angka), Uptime tidak merender track kosong.
- **VLANs**: tabel VLAN + tombol **Tambah VLAN** di baris judul tab; panel Port uplink di bawahnya berupa matriks port × (Tagged/Untagged/None) dengan satu tombol amber **Simpan ke OLT**. Port uplink menampilkan kata penuh Tagged/Untagged di desktop; mobile hanya hitungan port, detail di drawer Ports.
- **Konfigurasi**: form dua kolom (Koneksi CLI kiri · SNMP kanan), Pemilik di atas form (hanya Superadmin), tombol amber **Simpan & verifikasi** kanan bawah. Password tampil kosong dengan placeholder "Tidak diubah". Nilai CLI menampilkan `ssh://user@host:port` dengan password dihilangkan seluruhnya, bukan `user@:`.
- **Daftar ONU**: tabel ringkas + tombol **Buka di Configured** (juga sebagai aksi di empty state). Tab aktif tersimpan di URL, tab bar sticky di bawah header, dan label Daftar ONU menampilkan hitungannya.
- Tab VLANs & Konfigurasi tidak dirender untuk User.

### 12.8 Settings (pola sama untuk semua sub-menu)

```
OLT Management                                                            [+ Tambah OLT]
[⌕ Cari…]  [filter relevan ▾]
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ tabel                                                                                │
└──────────────────────────────────────────────────────────────────────────────────────┘
```
- Satu pola untuk OLT Management, User Management, ONU Types, Splitters & Zone, Speed Profile, VPN, TR-069: **judul + satu tombol tambah di kanan, cari/filter, tabel**.
- Tambah/edit membuka **drawer kanan 480px** (bukan modal tengah, bukan halaman baru), tombol Simpan sticky di bawah drawer. Pengecualian: edit Splitter memakai halaman sendiri karena memuat tabel ONU terpasang.
- Kolom per tabel mengikuti PRD §3.4.8–§3.4.14. Kolom "Pemilik" di OLT Management hanya dirender untuk Superadmin.
- Splitters & Zone: dua tab di bawah judul (Splitter | Zone). Speed Profile: pemilih OLT di kiri baris filter + tab Download | Upload.
- Kolom "Penggunaan" splitter: teks mono `5/8` + bar 48×4px (pola sama dengan signal bar).
- Hapus = item di menu baris, konfirmasi dialog kecil; bila diblok (masih dipakai), tombol tetap ada dan dialog menjelaskan sebabnya dalam satu kalimat.
- Mobile: tabel jadi kartu, drawer jadi bottom sheet penuh layar.

### 12.9 Logs `/logs`

```
Logs
[⌕ Cari…]  [Kategori ▾] [OLT ▾] [User ▾] [Tanggal ▾]
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Waktu           User    OLT      ONU     Kategori     Keterangan             Hasil    │
│ 23 Okt 14:01    …       …        [SN]    Otorisasi    …                      Sukses  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```
Baris diklik = drawer kanan: command yang dikirim + respons perangkat (blok mono, password `[REDACTED]`). Tanpa tombol hapus log. Logs memakai `TableCard` seperti halaman daftar lain; kolom Waktu menampilkan waktu absolut WIB (relatif hanya baris sekunder di kartu mobile); blok kode detail memakai `bg-sunken` + mono seperti permukaan CLI lain.

### 12.10 Kartu mobile (pola semua tabel di < 768px)

```
┌─────────────────────────────────────┐
│ [Nama pelanggan]            ● Online │  ← baris 1: identitas + status
│ [SN] · [OLT] 1/2/3:7                 │  ← baris 2: mono, --text-muted
│ ▮ -22.1 dBm    VLAN 100    [Zone]    │  ← baris 3: angka penentu keputusan
└─────────────────────────────────────┘
```
Sejak bahasa tabel berbasis pembatas 2026-10-29 (§8): bukan lagi kartu berkotak — baris daftar tanpa bingkai/latar/shadow sendiri dan tanpa tinggi minimum, padding vertikal `py-3`, dipisah pembatas `divide-y`; seluruh baris bisa diketuk. Maksimal 3 baris; data lain ada di halaman detail. Nilai penentu yang wajib bertahan di kartu: Configured = Rx + Terlihat; Unconfigured = Terlihat (plus Pertama bila muat); Kartu OLT = Port · CPU · RAM (HW/SW sengaja dihilangkan, itu data halaman detail).

## 13. Pola interaksi

| Pola | Aturan |
|---|---|
| Aksi ke OLT | Tombol berubah jadi status job inline: `Menunggu…` → `Mengirim ke OLT…` → `Selesai` (hijau, 3 detik) / `Gagal: [pesan OLT]` + **Coba lagi**. Tidak ada optimistic update. Status job tampil di tempat aksi ditekan (baris yang diklik), bukan hanya di atas halaman |
| Toast | Hanya untuk hasil job yang selesai saat user sudah pindah halaman. Kanan bawah, maks 3, hilang 5 detik, kecuali gagal (tetap sampai ditutup) |
| Konfirmasi | Dialog kecil 400px: judul = aksi + target ("Reboot [SN]?"), satu kalimat dampak, tombol aksi di kanan. Aksi berbahaya: ketik SN/nama |
| Drawer | Dialog TENGAH seperti modal (dulu kanan 480px — diubah atas permintaan user 2026-10-28 supaya semua pop up seragam di tengah), `shadow-modal`, `Esc` menutup, perubahan belum disimpan = konfirmasi. Form konfigurasi perangkat selalu dibuka dengan nilai saat ini; bila nilai saat ini tidak tersedia, tampilkan ringkasan nilai saat ini di atas form, bukan form default kosong — dan jangan pernah mengarang nilai yang belum dibaca. Pengecualian jujur untuk port Eth/WiFi: perangkat tidak terbukti mengirimkan mode/VLAN port lewat running-config yang tersedia, jadi "nilai saat ini" di modal dan di seksi Port Detail ONU adalah **terakhir ditulis Nexfiber** (`onus.port_configs`, dihapus saat restore-factory) dan selalu dilabeli begitu; bila belum pernah ditulis, modal tetap membuka default dengan ringkasan "belum dibaca" |
| Bottom sheet | Di bottom sheet, aksi destruktif tidak pernah menjadi tombol pertama; urutan dari atas: aksi utama, batal, lalu aksi destruktif |
| Setelan instan | Setelan yang langsung berlaku menampilkan status Tersimpan; perubahan yang memperpendek retensi meminta konfirmasi |
| Loading | Skeleton baris di tabel; tombol yang ditekan menampilkan spinner 14px di dalam tombol, label tetap |
| Auto-refresh | Dashboard & Configured 60 detik, berhenti saat tab tidak aktif. Teks "Diperbarui 14:02" di baris judul, tanpa animasi |
| Shortcut | `⌘K/Ctrl+K` cari global · `/` cari halaman · `j/k` pindah baris · `Enter` buka · `Esc` tutup |

## 14. Checklist sebelum halaman dianggap selesai

- Sesuai wireframe §11–§12 (posisi, kesejajaran, isi).
- Desktop ≥ 1280px (header), tablet 768–1023px dan HP 390px (navigasi bawah) sudah dicek, termasuk Chrome Android, tanpa scroll horizontal di level halaman.
- Terang dan gelap sudah dicek.
- State kosong, loading, error, sebagian gagal ada.
- Menu & aksi yang tidak boleh untuk peran aktif tidak dirender.
- Tanpa teks penjelas panjang, popup bantuan, garis pemisah berlebih, penomoran berulang, emoji.
- Bisa dipakai penuh dengan keyboard, fokus terlihat.
- Motion sesuai token §2.1 (durasi/easing tepat, sekali per kemunculan, tidak ada loop), properti animasi hanya `opacity`/`transform`, `prefers-reduced-motion: reduce` sudah diuji (motion hilang, layout tetap sama).
