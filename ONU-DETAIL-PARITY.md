# ONU Detail — inventaris layout referensi vs Nexfiber

Sumber referensi: aplikasi PHP lokal milik user (read-only), file `frontend/onu-detail.php`
(4238 baris) + `frontend/public/style.css` (kelas `.detail-plain-*`, `.smartolt-row`,
`.chart-wrapper`, `.status-cli-output`, `.port-table`). Dibaca langsung dari source, bukan
dugaan. Branding/nama aplikasi referensi TIDAK dibawa ke kode/UI Nexfiber.

Permintaan user: "buat sub agen untuk analisa menu onu detail dan menerapkan semua menu yang
ada dan agar layoutnya mirip" + klarifikasi "ini biar sama dengan aplikasi smartolt untuk
tampilan nya" → target = kesetaraan tampilan (struktur, urutan, posisi, kepadatan), bukan
redesign sendiri.

## Struktur halaman referensi (urutan nyata di source)

| # | Blok | Markup/CSS referensi | Isi |
|---|------|----------------------|-----|
| 0 | H1 `Detail ONU — <nama>` | `#page-title` | nama bersih atau SN |
| 0b | Banner OLT offline + tombol "Cek Ulang" | `.alert.alert-danger` | muncul bila OLT tak merespon |
| 1 | Grid teks 2 kolom (tanpa kartu/garis) | `.detail-plain-grid` → 2 × `.detail-plain-col`, baris `.detail-plain-row` (label 190px kanan-align + value kiri) | kiri = identitas, kanan = status/koneksi |
| 2 | Baris "Status" | `.smartolt-row` (label 160px + konten) | tombol `Status`, `Show running-config`, `Info SW`, (`TR069 Status` kondisional), `LIVE!` + panel output CLI `#status-cli-output-container` di bawah tombol |
| 3 | Baris "Trafik/Sinyal" | `.flex-row-gap` → 2 × `.chart-wrapper` | chart trafik (UL/DL, current+max, total paket) & chart sinyal (Rx ONU/Rx OLT) |
| 4 | Baris "Profil Kecepatan" | `table.data-table` 45/45/10 | Download · Upload · Aksi (link "Konfigurasi") |
| 5 | Baris "Port Ethernet" | `.port-table` | jumlah port dari spesifikasi tipe ONU; kolom Port · Admin state · Mode · DHCP · Action("Configure") |
| 6 | Baris "WiFi" | `.port-table` | jumlah SSID dari tipe ONU; Port · Admin state · Mode · SSID · DHCP |
| 7 | Baris "Layanan VoIP" dan "CATV" | `.smartolt-row--tight` | jumlah port VoIP / dukungan CATV dari tipe ONU |
| 8 | Baris aksi | `.smartolt-row--actions` | Reboot · Restore Factory · Resync config · Nonaktifkan/Aktifkan ONU · Hapus |

Field grid blok 1 — kolom kiri: OLT, Shelf, Slot, Port, ONU (`gpon-onu_<pon>:<id>`), Kanal
GPON, SN*, Tipe ONU*, Preset Konfigurasi*, Zone*, Splitter*, Nama*, Alamat atau keterangan*,
Kontak*, Tanggal otorisasi, Port ODB*, ONU external ID*, Lokasi (link peta).
Kolom kanan: Status (dot + "auto-refresh Ns"), Last Down, Sinyal Rx (`Rx ONU / Rx OLT` +
jarak), IP Manajemen*, TR609 Profile*, VLAN Terpasang, Akses Remote WAN, Mode ONU*,
Mode setup WAN*, Nama pengguna PPPoE (mask + toggle mata), Kata sandi PPPoE (mask + toggle).
`*` = baris itu sendiri clickable → modal edit.

Modal referensi: `update-onu-mode`, `edit-onu-type`, `edit-config-preset`, `edit-identity`
(+ tombol GPS), `replace-onu`, `mgmt-ip`, `tr609-profile`, `port-configure`.

Responsif referensi: `.detail-plain-grid` 1 kolom di ≤900px; `.detail-plain-row` label pindah
ke atas (kiri-align, 0.75rem) di ≤600px; `.smartolt-row` jadi kolom di ≤768px; `.flex-row-gap`
jadi kolom di ≤992px.

## Peta ke Nexfiber (apa yang diterapkan)

Diterapkan di `frontend/src/pages/OnuDetail.tsx` (satu halaman existing, tanpa halaman kedua),
pakai token/komponen Nexfiber sendiri (`Panel`, `StatusBadge`, `SignalBar`, `Drawer`,
`Confirm`, `TableCard`, `Button`) — tanpa menyalin CSS/branding referensi:

- Blok 1 grid 2 kolom label/value: `grid lg:grid-cols-2`, label `w-[190px] text-right`
  (≤600px label naik ke atas & kiri-align). Baris yang bisa diedit memakai `onClick` ke
  dialog existing (`info`, `speed`, `vlan`, `replace`) — hanya yang punya endpoint nyata.
- Blok 2 baris Status: tombol `Status`, `Show running-config`, `Info SW` memilih tampilan
  output dari job `POST /api/onus/{sn}/refresh` (read-only ke OLT, job nyata) yang dirender
  inline di panel output mono. `LIVE!` = toggle auto-refresh query detail dari database
  (15 s), tidak membanjiri perangkat.
- Blok 3: kartu Sinyal memakai histori `GET /api/onus/{sn}/signal?range=` (24h/7d/30d) +
  ringkasan min/avg/maks. Kartu Trafik per ONU = Phase 2 (tidak ada counter per ONU di
  backend) → kartu tetap ada di posisi yang sama dengan status "Segera", bukan angka palsu.
- Blok 4 Profil Kecepatan: tabel Download · Upload · Aksi, aksi membuka dialog ubah speed
  (`POST /api/onus/{sn}/speed-profile`, job).
- Blok 5–7: jumlah port Ethernet/SSID WiFi/VoIP/CATV dibaca dari katalog
  `GET /api/onu-types` yang dicocokkan dengan `onu_type_id`/`onu_type` ONU — angka nyata dari
  master data, bukan hardcode.
- Blok 8 baris aksi bawah: Reboot · Restore Factory · Resync config · Nonaktifkan/Aktifkan ·
  Hapus, semuanya endpoint job existing + konfirmasi (ketik SN untuk restore/hapus) + RBAC
  (`isManager` untuk replace/restore/hapus, sama seperti sebelumnya).

## Gap / blocker (tidak dipaksakan)

| Menu referensi | Status di Nexfiber | Alasan |
|---|---|---|
| Edit "Tipe ONU" & "Preset Konfigurasi" dari detail | read-only | tidak ada endpoint ubah tipe/preset pasca-otorisasi; menambahnya = fitur baru di luar halaman ini |
| Modal "IP Manajemen" (set DHCP/Static) | read-only | tidak ada endpoint/driver `set_mgmt_ip` di Nexfiber |
| "TR609/TR-069 Profile" + tombol TR069 Status | label "Segera" | TR-069 = Phase 2 terkunci (DECISIONS.md) |
| "Akses Remote WAN" | label "Segera" | sama, Phase 2 |
| PPPoE username/password + toggle mata | username read-only, password TIDAK ditampilkan | password ONU disimpan terenkripsi dan tidak pernah dikirim ke frontend (AGENTS.md); menampilkannya = regresi keamanan |
| Modal "Mode ONU / Mode setup WAN" | read-only | tidak ada endpoint ubah mode ONU/WAN (bukan scope `authorize_onu`, DECISIONS.md) |
| "Configure" per port Ethernet + modal port | tabel tampil, aksi nonaktif | belum ada driver/endpoint konfigurasi port per ONU dan belum ada transkrip CLI nyata |
| WiFi SSID edit | hanya jumlah SSID | Phase 2 (butuh TR-069) |
| Chart trafik per ONU | kartu "Segera" | tidak ada sumber counter per ONU di backend |
| Shelf/Kanal GPON | Shelf = 1 (C300/C320 single-shelf), Kanal = `pon_type` tipe ONU | perangkat tidak melaporkan shelf per ONU; nilai lain akan jadi tebakan |
| Banner OLT offline | dipakai status OLT dari detail ONU bila tersedia | tidak ada field `last_snmp_status` per ONU di API Nexfiber |

Penyimpangan yang disetujui user (klarifikasi "tampilan harus sama"): menu aksi pindah dari
dropdown "Aksi ▾" kanan atas (DESIGN §12.6) menjadi baris tombol di bagian bawah + baris
tombol Status di atas, sesuai referensi. Tab horizontal DESIGN §12.6 dihapus karena referensi
menampilkan semua blok bertumpuk dalam satu halaman.
