# DESIGN.md: Fiberdesk NOC Console

Dokumen arah desain (sumber identitas). `antislop.md` dipakai di atas dokumen ini sebagai filter, bukan sebagai sumber gaya.

## 1. Identitas

- **Produk**: konsol operasional manajemen OLT/ONU untuk tim NOC ISP fiber (GPON).
- **Pengguna**: operator NOC shift 24/7, teknisi lapangan via laptop, supervisor. Internal, bukan publik.
- **Pekerjaan layar**: menemukan ONU/OLT yang bermasalah, membaca angka sinyal, dan mengambil satu tindakan (auth, reboot, assign profile, buka tiket).
- **Karakter**: panel instrumen, bukan brosur. Padat, tenang, terbaca saat mata lelah jam 3 pagi.
- **Motif identitas**: *signal bar*: balok horizontal 3 segmen setinggi 4px yang memetakan Rx power ke bucket (baik / waspada / buruk / LOS). Dipakai konsisten di tabel, kartu detail, dan ringkasan OLT. Alasan: satu bahasa visual untuk satu-satunya angka yang paling sering dibaca operator, dan ia membawa informasi (bukan dekorasi garis warna).

## 2. Dial

`Dial: ENERGY 1 / RHYTHM 1 / MOTION 1`

- **ENERGY 1**: alasan: aplikasi kerja harian; sapaan visual mengambil perhatian yang seharusnya milik data alarm.
- **RHYTHM 1**: alasan: operator memindai layar yang sama ratusan kali per shift; posisi elemen yang stabil mempercepat muscle memory. Variasi komposisi diizinkan hanya antar jenis layar (dashboard vs tabel vs detail), bukan antar section di dalam satu layar.
- **MOTION 1**: alasan: hover/focus/transisi state saja. Tidak ada scroll-reveal, tidak ada pulse abadi. Gerak abadi di layar monitoring menyerupai alarm palsu.

Karakter datang dari tipografi, densitas, dan motif signal bar, bukan dari energi atau animasi.

## 3. Palet

Dua warna inti + satu aksen + netral. Netral tidak dihitung sebagai warna inti (R-29).

### Netral (light, default)

| Token | Hex | Pakai |
|---|---|---|
| `--bg-app` | `#F7F6F3` | Latar aplikasi. Alasan: putih hangat mengurangi silau LCD dibanding `#FFFFFF` murni pada shift panjang. |
| `--bg-surface` | `#FFFFFF` | Tabel, panel, kartu. Alasan: kontras halus terhadap `--bg-app` memisahkan bidang tanpa perlu shadow. |
| `--bg-sunken` | `#EFEDE8` | Header tabel, baris zebra opsional, kode blok. |
| `--border` | `#D9D5CC` | Garis tabel dan panel. |
| `--border-strong` | `#B4AEA2` | Pemisah struktural, batas input. |
| `--text` | `#1C1B18` | Teks utama. Kontras 17.2:1 di `--bg-surface`, 15.9:1 di `--bg-app`. |
| `--text-muted` | `#5B574E` | Label, satuan, metadata. Kontras 7.2:1 / 6.7:1. |
| `--text-faint` | `#6B675B` | Placeholder saja, tidak pernah untuk data. Kontras 5.7:1 / 5.2:1 / 4.8:1 di `--bg-sunken`. |

### Inti

| Token | Hex | Pakai |
|---|---|---|
| `--ink` | `#1C1B18` | Warna inti 1: teks, ikon, garis. Alasan: grafit kehijauan, bukan hitam netral, agar menyatu dengan latar hangat. |
| `--fiber` | `#0F5C4A` | Warna inti 2: nav aktif, link, judul section, state terpilih. Alasan: hijau tua optik, merujuk serat/konektor APC; bukan biru korporat default dan lolos AA sebagai teks (7.9:1 di putih, 7.3:1 di `--bg-app`). |

### Aksen (satu, dipakai di momen kunci)

| Token | Hex | Pakai |
|---|---|---|
| `--amber` | `#B4540A` | Tombol aksi primer komit (Authorize, Reboot, Apply), penanda baris terpilih. Alasan: satu-satunya warna yang berarti "tindakan ini mengubah jaringan"; dilarang muncul di ikon, link, atau latar dekoratif. Teks putih di atasnya 4.98:1 (AA lolos); karena itu label tombol primer minimum 13px/600. |

### Status (bahasa data, bukan palet dekorasi)

Dipakai hanya untuk state perangkat, selalu berpasangan dengan teks/ikon (tidak pernah warna saja).

| Token | Hex | Arti | Kontras |
|---|---|---|---|
| `--st-up` | `#1F6B3A` | Online, Rx normal | 6.5:1 |
| `--st-warn` | `#8A5B00` | Rx mendekati ambang, high CRC | 5.9:1 |
| `--st-down` | `#A02020` | LOS, Dying Gasp, offline | 7.7:1 |
| `--st-idle` | `#5B574E` | Belum diotorisasi, disabled | 7.2:1 |

Kontras diukur terhadap `--bg-surface` `#FFFFFF`; semua tetap di atas 4.5:1 terhadap `--bg-app` `#F7F6F3`.

Ambang Rx ONU (GPON, dBm) yang memetakan status, sebagai nilai default yang dapat dikonfigurasi per OLT:

| Rentang | Status |
|---|---|
| -8 s/d -25 | normal (`--st-up`) |
| di bawah -25 s/d -27 | waspada (`--st-warn`) |
| di bawah -27, atau di atas -8 (terlalu kuat) | buruk (`--st-down`) |
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
| `--st-up` | `#56B870` |
| `--st-warn` | `#D9A33A` |
| `--st-down` | `#E4707A` |
| `--st-idle` | `#8E8B82` |

Toggle: `Sistem / Terang / Gelap`, tersimpan per pengguna. Keduanya diuji kontras sebelum rilis.

### Larangan palet

Tanpa gradien sebagai warna primer, tanpa glow, tanpa latar radial, tanpa background grid/blueprint. Alasan: tidak ada hierarki yang dilayani; di layar penuh angka, efek-efek itu hanya menambah noise.

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
| Padding sel tabel | `8px 12px` |
| Tinggi baris tabel (compact, default) | `32px` |
| Tinggi baris tabel (comfortable) | `40px` |
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
| `radius-md` | `8px` | Panel, kartu, modal, popover | Menandai lapisan di atas grid. |

Tidak ada pill. Alasan: bentuk kapsul menghapus perbedaan antara badge, tombol, dan input di layar yang penuh kontrol kecil.

## 7. Shadow

Dua level saja, dan hanya untuk elevasi nyata.

| Token | Nilai | Pakai |
|---|---|---|
| `shadow-overlay` | `0 4px 12px rgba(28,27,24,0.14)` | Dropdown, popover, context menu |
| `shadow-modal` | `0 12px 32px rgba(28,27,24,0.22)` | Dialog, drawer |

Panel, kartu, tabel, dan sidebar **tidak** memakai shadow; pemisahan memakai `--border` dan perbedaan latar. Alasan: shadow adalah penanda "elemen ini melayang di atas yang lain"; jika semuanya melayang, elevasi tidak lagi memberi tahu apa pun.

Fokus: `outline: 2px solid var(--fiber); outline-offset: 1px` di light, `--amber` di dark. Tidak pernah `outline: none` tanpa pengganti.

## 8. Komponen dasar

### Tombol

| Varian | Tampilan | Pakai |
|---|---|---|
| Primer | isi `--amber`, teks `#FFFFFF`, radius-sm | Satu per layar, untuk aksi yang mengubah jaringan |
| Sekunder | border `--border-strong`, teks `--ink` | Aksi aman (Export, Refresh, Filter) |
| Tenang | teks `--fiber`, tanpa border | Aksi dalam baris tabel |
| Destruktif | border `--st-down`, teks `--st-down`, konfirmasi wajib | Deauthorize, Factory reset |

Tinggi: 28px (dalam tabel), 32px (default), 40px (form submit). Tap target mobile minimum 44px.
Tanpa panah dekoratif di tombol. Alasan: tidak ada tombol di aplikasi ini yang arah visualnya membantu.

### Badge status

Teks + titik 6px berwarna status, radius-sm, tanpa glow, tanpa uppercase lebar, tanpa animasi pulse. Titik menandai state perangkat nyata (R-31). Satu-satunya elemen yang boleh "berkedip" adalah banner alarm kritis baru, sekali selama 2 detik lalu berhenti. Alasan: perhatian ditarik saat kejadian, bukan terus-menerus.

### Signal bar (motif)

Balok lebar 48px tinggi 4px, radius 0, terbagi jadi segmen terisi sesuai bucket Rx, warna mengikuti token status, dengan nilai dBm mono di sebelahnya. Selalu berdampingan dengan angka, tidak pernah menggantikan angka. Alasan: operator butuh nilai eksak untuk tiket; bar hanya mempercepat pemindaian.

### Tabel

- Header lengket (sticky), kolom pertama lengket pada viewport < 1280px.
- Virtualisasi wajib di atas 200 baris.
- Zebra mati secara default; pemisah baris memakai garis 1px `--border`. Alasan: pada baris 32px, zebra menambah getaran visual saat scroll cepat.
- Hover baris: latar `--bg-sunken`. Baris terpilih: latar `--bg-sunken` + garis kiri 2px `--amber` (penanda state nyata, bukan dekorasi).
- Pengurutan: indikator panah kecil pada kolom aktif saja.

### State data (wajib di setiap tampilan data)

| State | Isi |
|---|---|
| Kosong (belum ada data) | Sebab + satu aksi: "Belum ada OLT terdaftar. Tambahkan OLT untuk mulai menarik data ONU." |
| Kosong (filter) | "Tidak ada ONU yang cocok dengan filter ini." + tombol Hapus filter |
| Loading | Skeleton baris setinggi baris asli, maksimal 8 baris, plus teks "Menarik data dari OLT ..." |
| Error | Penyebab + tindakan: "Gagal terhubung ke OLT-SBY-01 (timeout 10s). Coba lagi atau periksa jalur manajemen." + tombol Coba lagi |
| Sebagian gagal | Banner di atas tabel: "3 dari 12 OLT gagal dipolling. Data di bawah mungkin kedaluwarsa." + daftar OLT |

### Data placeholder

Selama belum terhubung ke perangkat nyata, sel kosong dibiarkan kosong atau diberi `[DATA NYATA]`. Dilarang mengisi tabel dengan serial/pelanggan/angka Rx karangan yang terlihat realistis.

## 9. Breakpoint

| Lebar | Perilaku |
|---|---|
| >= 1440px | Sidebar penuh + tabel + panel detail samping |
| 1024 s/d 1439px | Sidebar penuh, panel detail jadi drawer |
| 768 s/d 1023px | Sidebar jadi ikon, kolom tabel sekunder disembunyikan |
| < 768px | Tabel jadi daftar kartu (serial, status, Rx, OLT/PON), aksi lewat drawer, target sentuh 44px |

Tanpa overflow horizontal di level halaman; scroll horizontal hanya di dalam container tabel.

## 10. Aksesibilitas

- Kontras teks minimum 4.5:1, teks besar 3:1, sudah diverifikasi pada tabel token di atas untuk kedua tema.
- Status tidak pernah disampaikan oleh warna saja: selalu ada teks dan/atau bentuk.
- Seluruh alur dapat dioperasikan dengan keyboard: `Tab` berurutan sesuai visual, `Enter` membuka baris, `Esc` menutup drawer/modal, `/` fokus ke pencarian, `j/k` pindah baris di tabel.
- Fokus terlihat di setiap elemen interaktif.
