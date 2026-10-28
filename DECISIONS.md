# DECISIONS.md — keputusan terkunci Nexfiber (jangan ditanya ulang)

Dokumen ini kumpulan jawaban final atas ambiguitas yang sudah diputuskan.
Kalau Copilot/sub-agent nemu konflik dengan `PRD-FINAL.md`/`DESIGN.md`,
**dokumen ini menang** untuk poin-poin di bawah (PRD/DESIGN belum sempat
di-sync ulang ke semua poin ini). Jangan tanya ulang ke user untuk hal yang
sudah tercatat di sini.

## Role & data model
- Role ENUM Postgres 3 nilai di `users.role`: `superadmin`, `admin`, `user`.
  Bukan "role sebagai data"/tabel terpisah — nambah role baru = migrasi Alembic.
- DB dev lama: TIDAK dimigrasikan. Reset total: drop DB dev → `alembic upgrade
  head` → buat Superadmin pertama via `/setup` → jalankan ulang seed dev
  (OLT dimiliki satu Admin dev + satu User dev di bawahnya). Seed dev TIDAK
  masuk git repo.
- `scripts/create_admin.py` dihapus — melanggar aturan "no default password",
  diganti alur `/setup` (404 setelah user pertama ada).
- **Pembuatan user (menang atas PRD §3.4.9):** Superadmin boleh membuat
  Superadmin / Admin / User; Admin boleh membuat Admin dan User (User otomatis
  di bawah dirinya), TIDAK boleh membuat Superadmin. PRD §3.4.9 lama menulis
  "Superadmin bisa membuat Admin/User; Admin hanya bisa membuat User" — itu
  bukan keputusan keamanan, hanya penyempitan awal. PRD §3.7 aturan 5 tetap
  berlaku: Superadmin **pertama** hanya lewat `/setup`.
- Visibilitas user tetap berbasis `admin_id` (§3.7): Admin yang membuat Admin
  lain tidak melihat Admin itu di daftarnya. Kalau nanti perlu, tambah kolom
  `created_by` — jangan melebarkan `_visible()`.
- **Hapus user = soft-delete** (`deleted_at` + `is_active=False`), pola sama
  seperti OLT/ONU. Tidak pernah hard-delete: `activity_logs.user_id` dan
  `olts.owner_id` harus tetap menunjuk baris nyata. Nonaktifkan/aktifkan lewat
  `PATCH /api/users/{id}` `{"is_active": ...}`.
- Seseorang **tidak bisa menonaktifkan atau menghapus akunnya sendiri**
  (dicek di backend, bukan cuma disembunyikan di UI), ditambah aturan lama:
  Admin yang masih punya OLT dan Superadmin aktif terakhir tidak bisa
  dinonaktifkan/dihapus; parent yang masih punya User di bawahnya juga tidak.

## Sinyal / RX
- 4 bucket dipakai di **SEMUA** tempat (tabel, kartu, filter, signal bar) —
  jangan ada tempat lain yang pakai pembagian 3 level:
  - **Good**: -8 s/d -25 dBm
  - **Fair**: -25 s/d -27 dBm
  - **Weak**: -27 s/d -28 dBm
  - **Critical**: ≤ -28 dBm, ATAU > -8 dBm (sinyal kelewat kuat)
  - **LOS**: tanpa nilai / putus

## Ditunda (jangan dibangun di MVP)
- Sparkline/grafik ONU online 24 jam per OLT di tabel Dashboard — ditunda.
  JANGAN buat tabel `onu_status_history`.
- Notifikasi Telegram/email (alert M6) — ditunda. Alert cukup tampil di
  dashboard (list/badge), tanpa pengiriman keluar.
- VPN Tunnels & TR-069 Management — tetap Phase 2 ("Segera"), tidak dibangun.

## Mode ONU / WAN setup mode di Detail ONU — sumber nilai
- Sumber utama: hasil baca **CLI/running-config** yang sudah disinkron backend
  (kolom `onus.onu_mode` / `onus.wan_mode`).
- Tidak terbaca di CLI (kolom NULL/kosong) -> tampil **default**: ONU mode
  `Routing`, WAN setup mode `Setup via ONU webpage` (`wan_mode = "webpage"`).
  Default yang sama jadi nilai awal modal `Update ONU mode`.
- Default dihitung **di backend** (`app/schemas/onu.py`: `DEFAULT_ONU_MODE` /
  `DEFAULT_WAN_MODE`, dipakai `onu_service._apply_mode_defaults`) dan dikirim
  sebagai nilai efektif + penanda `onu_mode_source` / `wan_mode_source`
  (`"cli"` | `"default"`). Frontend TIDAK menambal default sendiri.
- Default **tidak pernah ditulis ke DB**: kolom tetap NULL supaya default tidak
  tersamar sebagai hasil baca perangkat.
- Kelak TR-069 server jadi sumber nilai; sebelum itu cukup CLI + default ini.
  Sumber baru masuk lewat jalur `*_source` yang sama, bukan cabang UI baru.

## Job & scheduling
- Nama job provisioning ONU: **`authorize_onu`** (bukan `provision_onu`).
- `sync_unconfigured`: interval **1 menit**.
- Kesehatan OLT (cpu/ram/suhu/uptime/cards): **gabung ke job optical yang
  sudah ada** (siklus 15 menit), satu koneksi per OLT untuk optical+health
  sekaligus. Jangan buat job terpisah `sync_olt_health`. Boleh rename job
  jadi `sync_olt_metrics` kalau scope-nya (optical+health) perlu nama yang
  lebih jelas — field DB tetap sama.
- Rx OLT per ONU (ZTE): via CLI `show pon power olt-rx gpon-olt_<pon>` di
  siklus 15 menit yang sama. **Parser untuk output ini BELUM ADA CONTOH
  OUTPUT ASLI** — `olt_rx_power_dbm` tetap `None` sampai ada sample nyata
  dari ONU test (`gpon-onu_1/4/1:11`, OLT id=8). Tandai di kode
  `# TODO: parser belum ada contoh output asli`.
- Reboot ONU (`pon-onu-mng` / `reboot` / `exit`): implementasikan, tapi
  tandai `# UNVERIFIED: uji di ONU test` di kode. JANGAN dieksekusi ke OLT
  produksi nyata oleh agent manapun — hanya user yang menjalankan uji nyata,
  dan hanya ke `gpon-onu_1/4/1:11`.

## Scope authorize_onu (MVP)
- **Minimal**: onu + type + sn + tcont + gemport + service-port, VLAN dari
  `onus.vlan_id` (dropdown pilih VLAN existing).
- **TIDAK** termasuk block `pon-onu-mng` (flow/switchport-bind, WiFi SSID,
  PPPoE) — itu device-specific per pelanggan, domainnya Detail ONU/preset,
  bukan job `authorize_onu`.

## VLAN write — scope fase Settings
- Fase Settings (Speed Profile) sekarang: backend saja —
  `POST/DELETE /api/vlans`, driver push ke OLT, job type baru untuk VLAN.
  Speed Profile di UI tetap **baca-saja** terhadap VLAN existing (dropdown
  pilih VLAN, bukan CRUD VLAN di halaman Speed Profile).
- UI CRUD VLAN penuh dibangun nanti di **Detail OLT tab VLANs** (PRD §3.4.7),
  bukan di halaman Speed Profile.

## Kesehatan OLT — skema DB
- Tambah kolom langsung ke tabel `olts` (BUKAN tabel `olt_cards` terpisah):
  `cpu_pct`, `ram_pct`, `temperature_c`, `uptime_seconds`, `software_version`,
  plus satu kolom `cards` tipe **JSONB** untuk data per-slot/card.
- Alasan: data card cuma ditampilkan di satu tab, tidak pernah di-query
  granular per-card. JSONB cukup; jangan bikin tabel relasional untuk ini.

## Infra / config
- Health endpoint: **`/healthz`** (bukan `/api/health`) — konsisten di semua
  dokumen, script, dan test.
- `config.py` baca `config.ini` dari env `NEXFIBER_CONFIG` (format: section
  `[database] url`, `[app] secret_key`) bila env itu ada; fallback ke `.env`
  untuk dev kalau env `NEXFIBER_CONFIG` tidak di-set.
- Struktur folder: pertahankan `app/worker` (dijalankan `python -m app.worker`)
  seperti sekarang, JANGAN pindah ke `repositories/`+`worker/` di root.
- Indikator "● Sistem aktif": `GET /api/system/status`, aktif bila heartbeat
  worker < 2 menit.

## Urutan pembangunan halaman
- **Settings dulu** (Zone, ONU Types, Splitter, Speed Profile+VLAN read,
  User Management) → baru Unconfigured → Configured → Form Otorisasi →
  Detail ONU → Detail OLT → Dashboard penuh → Logs → Akun.
- Alasan: Form Otorisasi butuh dropdown Zone/ONU Types/Splitter — kalau
  dibangun sebelum Settings ada, akan pakai data mock lalu harus dirombak
  ulang.

## Dashboard — blok v3 yang DIHAPUS
Hapus semua, ganti dengan isi v4 (strip 4 sel, baris sinyal 4 bucket, tabel
OLT tanpa sparkline, aktivitas terbaru, "Diperbarui HH:MM" + tombol Refresh):
- Blok "Perlu tindakan" (daftar ONU bermasalah)
- Histogram Rx
- "6 PON terpadat" (daftar PON tersibuk)
- Kalimat ringkasan agregat
- Countdown refresh (ganti jadi teks statis "Diperbarui HH:MM")

## Infra server (hasil setup nyata, bukan rencana)
- Server ini (Debian 12 bookworm) sudah jalan Apache untuk domain lain —
  Nexfiber TIDAK pakai Caddy/domain/HTTPS, cukup satu port HTTP langsung.
- Port aplikasi: **8088** (dicek kosong, dikonfirmasi user).
- Deploy: **tanpa Docker** — install lokal langsung di server
  (`/opt/nexfiber`, venv Python 3.11, PostgreSQL bawaan Debian/repo resmi
  versi 15, systemd unit `nexfiber-api` + `nexfiber-worker`, frontend
  di-build jadi static lalu disajikan langsung oleh FastAPI lewat
  `StaticFiles`/`FileResponse` — tidak ada nginx/caddy terpisah).
- `install.sh` dan `update.sh` dijalankan di **host** (bukan di dalam
  container — tidak ada container sama sekali untuk deployment ini).
- Config tersimpan di `/etc/nexfiber/config.ini`, dimiliki user sistem
  `nexfiber` (folder WAJIB di-chown juga, bukan cuma isinya — pernah jadi
  bug: folder tetap `root:root` padahal file sudah `chown nexfiber`, bikin
  API gagal baca config dan crash loop).
- User dev untuk login: dibuat via `POST /api/auth/setup` (bukan script
  manual) — username `admin`, password lihat catatan terpisah (jangan
  simpan password asli di file markdown).

## Audit fitur SmartOLT — pola diadopsi (Fase C, belum dikerjakan sekarang)
Hasil audit kode SmartOLT (seluruh action handler + backend) vs PRD Nexfiber:
mayoritas fitur besar (Replace ONU, Restore factory, CSV export, ONU preset,
backup config OLT, VLAN management, mode IP manajemen ONU, port config fisik)
**sudah tercakup** di PRD-FINAL.md §3.4.6–3.4.12, cuma belum dibangun. VPN
Tunnels & TR-069 tetap ditunda (lihat di atas) — jangan diusulkan lagi.
Dua pola teknis layak diadopsi saat halaman terkait dibangun:
- **`test_connection` job**: hasil CLI dan SNMP harus dua boolean terpisah
  dari tes sungguhan, BUKAN string-matching pesan driver. SmartOLT pernah
  bug: status SNMP ditentukan dari mencocokkan teks pesan, hasilnya selalu
  salah setelah refactor driver. Terapkan saat job `test_connection`/OLT
  Management dibangun.
- **ETag ringan via CRC32-XOR per baris** untuk polling status ONU (tabel
  Configured/Dashboard): hitung `BIT_XOR(CRC32(kolom-kolom relevan))` per
  OLT, kirim data penuh hanya kalau checksum berubah — hemat bandwidth/
  re-render saat polling tabel besar. Terapkan saat polling status ONU di
  Configured/Dashboard dibangun (SSE job-stream yang sudah ada untuk job
  lain tetap dipakai apa adanya, ini khusus untuk endpoint polling tabel).
- Pola background job via `exec(...)` non-blocking dari form SmartOLT TIDAK
  diadopsi — arsitektur tabel job Postgres + worker Nexfiber sudah lebih
  benar untuk ini.

## TODO — Speed Profile pisah Download/Upload (belum dikerjakan)
Permintaan user: satu profil `speed_profiles` sekarang gabung download+upload
dalam satu baris (`download_kbps`+`upload_kbps`). User minta dipisah jadi dua
entitas profil independen (profil Download sendiri, profil Upload sendiri)
supaya bebas mencampur kombinasi down/up tanpa harus buat baris baru untuk
tiap kombinasi. Ini sejalan dengan PRD-FINAL.md §4.6 baris `speed_profiles`
yang sudah menyebut field `direction` ENUM(`download`,`upload`) — field itu
belum pernah diimplementasikan di model `backend/app/models/speed_profile.py`
maupun di `frontend/src/pages/settings/SpeedProfile.tsx` (kedua tempat masih
pakai 1 baris = 1 pasang down+up).
- Scope saat dikerjakan: migrasi skema (tambah `direction` ENUM, atau pecah
  jadi dua baris per arah — putuskan saat eksekusi, cek dulu apakah `onu_presets`
  `download_profile`/`upload_profile` (sudah berupa 2 field nama terpisah,
  §4.6 baris 504) butuh ikut berubah referensinya.
- Dampak ke dropdown: halaman Form Otorisasi/ONU Preset yang pilih profil
  speed by name HARUS bisa pilih Download dan Upload dari dua dropdown
  terpisah, bukan satu dropdown "paket".
- Belum ditentukan track Fase mana — ajukan sebagai task tersendiri setelah
  Fase C selesai, JANGAN digabung diam-diam ke track C yang sedang berjalan
  (hindari migrasi skema bentrok dengan C1-C3 yang sedang paralel).

## Management & VoIP IP di Detail ONU — sumber nilai
- Nilai modal "Update Management and VoIP IP" disinkronkan dari blok
  `pon-onu-mng` running-config perangkat (perangkat = sumber kebenaran, seperti
  `wan_vlan`).
- Aturan pasangan: `ip-host N` ↔ `gemport N flow F` ↔ `flow F ... vlan V`.
  Contoh nyata: `ip-host 2 dhcp-enable enable` + `gemport 2 flow 2` +
  `flow 2 pri 2 vlan 100` → mode DHCP, VLAN 100. Mode dari baris `ip-host`:
  `dhcp-enable enable` = DHCP; `dhcp-enable disable ip-address <ip>` = static;
  tanpa baris `ip-host N` = inactive; bentuk lain/tak bisa dipasangkan = None
  (nilai lama bertahan, tidak menebak).
- Hanya kandidat dengan VLAN bertanda `type == "management"` di master VLAN yang
  dipakai. `onus.vlan_id` (VLAN utama, kolom "Update VLAN") TIDAK disentuh oleh
  sinkron management — nomor VLAN management tampil dari `service_vlans`
  (is_management).

## IP terbaca perangkat (tautan di baris Setup WAN / Mgmt IP)

- Sumber IP = `show gpon remote-onu ip-host <ifname>`, baris `Current IP address`
  per blok `Host ID` (perangkat = sumber kebenaran). Laporan TIDAK memuat VLAN —
  verifikasi lewat pasangan running-config (`Host ID` = `ip-host N`, aturan §
  "Management & VoIP IP"). Aturan keras (keputusan user): hanya IP yang terpasang
  ke VLAN bertanda `type == "management"` yang boleh disimpan/ditampilkan;
  tidak bisa dipasangkan = None (tidak menebak/menyimpan, nilai lama bertahan).
- Diambil on-demand (POST `/api/ons/{onu_id}/refresh-ip`, read-only, dua perintah
  satu sesi CLI, tanpa `confirm`) saat halaman Detail ONU dibuka bila
  `onus.ip_address` masih kosong, dan saat "Muat ulang"; hanya IP terverifikasi
  VLAN management yang disimpan, nilai lama tidak pernah dikosongkan.
- Baris Setup WAN dan Mgmt IP menampilkannya sebagai tautan `http://<ip>` yang
  membuka tab baru (komponen `IpLink`). Frontend memakai satu sumber `ipLive`
  (fallback `d.ip_address`).

## Kolom `onus.wan_ip_address` terpisah dari `onus.ip_address` (wt7, 2026-10-28)

**Aturan keras tetap**: `onus.ip_address` HANYA IP dari master VLAN `type == "management"`, `onus.wan_ip_address` HANYA IP host di VLAN NON-management — dua kolom tidak pernah saling mewakili, tidak pernah saling mengisi, tidak pernah di-NULL-kan oleh satu sama lain.

**Bug**: chip "Setup WAN" di Detail ONU memakai `ipLive` (IP management) sehingga IP management (contoh produksi `192.168.100.20`) tampil sebagai IP WAN.

**Sumber IP WAN**: `Current IP address` blok `Host ID` dari `show gpon remote-onu ip-host` yang terpasang ke VLAN non-management (urutan Host ID, pertama ≠ `0.0.0.0`); pasangan host→VLAN utama `vlan-filter iphost N ... vlan V` (host bisa punya IP walau TANPA baris `ip-host N`, lihat laporan produksi job 13256), fallback `ip-host N` ↔ `gemport N flow F` ↔ `flow F ... vlan V`. Tanpa pasangan / laporan kosong / `management_vlans` kosong = `None` — tidak pernah menebak.

**Kolom**: `onus.wan_ip_address` `String(45)` NULL (rev `d7e8f9a0b1c2`), bukan INET: sumber `Current IP address` termasuk nilai belum assign `0.0.0.0`/`255.255.255.255` yang memang tidak disimpan (hanya ≠ `0.0.0.0` yang masuk), netmask pg `INET` terlalu berisiko untuk nilai kasar.

**Isi dua titik, dua aturan sama**:
- `refresh_ip` (POST `refresh-ip`): respons kini `{ip_address, wan_ip_address}`; parser `parse_wan_ip` = kebalikan `parse_current_ip`.
- sync inventaris (`_adopt_inventory`): `wan_ip_address` = kandidat pertama `management_ips` di luar set management yang membawa IP (pola pemilihan kandidat sama dengan sync management). Master tanpa VLAN management = tidak ada dasar memastikan "non-management" → tidak disentuh.
- Keduanya: hasil `None`/kosong → nilai lama dibiarkan, tidak pernah di-NULL-kan.

**Frontend**: `wanIpLive = liveWanIp ?? d.wan_ip_address` khusus baris `Setup WAN`; chip null = mode tampil tanpa chip. `Mgmt IP` tetap `ipLive`. Guard refresh kini `!ip_address || !wan_ip_address` (satu POST mengisi dua kolom).
