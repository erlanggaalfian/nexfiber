# Nexfiber — Manajemen OLT/ONU untuk ISP

**Author:** Erlangga Alfian

**Source code:** https://github.com/erlanggaalfian/nexfiber.git

Nexfiber adalah aplikasi web untuk administrator jaringan ISP yang perlu **mengelola OLT dan ONU secara terpusat**: inventaris OLT/ONU, otorisasi ONU baru, konfigurasi port Ethernet/WiFi/VLAN, monitoring sinyal optik, dan riwayat trafik — semua lewat satu antarmuka. Job yang menyentuh perangkat berjalan di server (worker + antrean Postgres) dan statusnya dialirkan ke browser lewat SSE — browser hanya menampilkan antarmuka dan hasil agregat.

---

## Daftar Isi

- Fitur Aplikasi
- Halaman Web
- Arsitektur
- Persyaratan Server
- Struktur Direktori
- Struktur Database
- Source Code Resmi
- Instalasi Baru
- Setup Admin Pertama
- Upgrade / Pembaruan
- Uninstall
- Backup Konfigurasi OLT & Retensi
- Keamanan
- Troubleshooting
- Lisensi & Kontribusi

---

## Fitur Aplikasi

### Manajemen pengguna

| Fitur | Keterangan |
| --- | --- |
| Login & session | Bearer token (JWT), logout mencabut token di server |
| Role | `superadmin`, `admin`, dan `user` |
| Cakupan OLT | Setiap endpoint memeriksa kepemilikan OLT di backend; di luar cakupan = 404 |
| Setup admin | Halaman `/setup` saat belum ada user sama sekali |
| Audit log | Semua aktivitas penting tercatat di `activity_logs` |

### Master data (Settings)

- **Zone** — wilayah/pengelompokan pelanggan
- **ONU Types** — katalog tipe ONU (jumlah port Ethernet, SSID WiFi, VoIP, CATV)
- **Splitter / ODP** — titik distribusi serat
- **Speed Profile** — profil kecepatan download/upload (baca VLAN existing, bukan CRUD VLAN)
- **VLAN** — master VLAN, termasuk penanda `type == "management"`
- **User Management** — kelola akun dan peran

### Manajemen OLT

- Tambah, edit, hapus OLT (ZTE C320, lewat CLI + SNMP)
- Kesehatan OLT: CPU, RAM, suhu, uptime, kartu per slot (digabung ke siklus optik 15 menit)
- Backup konfigurasi OLT, disimpan **terenkripsi** di database
- Detail OLT per tab: Monitoring (Port PON, Kartu), Konfigurasi, VLAN

### Manajemen ONU

- **Unconfigured** — ONU yang terdeteksi OLT tapi belum diotorisasi, lengkap dengan form otorisasi
- **Configured** — ONU terotorisasi dengan filter, pilih massal, dan status ikon-saja (deskripsi lengkap saat hover)
- **Detail ONU** — identitas, sinyal optik (4 bucket: Good/Fair/Weak/Critical/LOS), grafik Rx, Speed Profile, Port Ethernet, WiFi (WLAN), Management & VoIP IP, Setup WAN, layanan tambahan (VoIP/CATV/IPTV)
- **Aksi ONU** — reboot, resync config, ubah VLAN, otorisasi ulang, restore factory, dan aksi port — semua lewat job, tanpa optimistic update
- **Port Ethernet & WiFi** — konfigurasi per port; nilai yang tampil adalah **terakhir ditulis Nexfiber** (bukan hasil baca perangkat) dan selalu dilabeli begitu; password WiFi **tidak pernah** disimpan

### Monitoring (backend)

Semua pengecekan dijalankan **di server** — bukan N× fetch dari browser.

| Metode | Fungsi |
| --- | --- |
| SNMP polling 1 menit | Status ONU, tulis hanya saat berubah |
| Siklus optik 15 menit | Daya Rx per ONU + kesehatan OLT, satu koneksi per OLT |
| Job queue Postgres | `SELECT … FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`, bukan Celery/Redis |
| SSE job stream | Status job dialirkan ke browser dengan token sekali pakai |

**Dashboard:**

- Strip ringkasan, baris sinyal 4 bucket, tabel OLT, aktivitas terbaru
- Teks statis "Diperbarui HH:MM" + tombol Refresh

### Logs & data grafik

- **Logs** — filter kategori, waktu absolut (WIB), dan tautan balik ke ONU
- **GraphData** — pratinjau dan hapus data grafik per OLT dengan rincian per OLT, bukan sekadar total
- **Housekeeping otomatis** — purge grafik 03:00, purge umum 03:30 (lihat section Backup & Retensi)

### Performa UI

- Tabel terpusat satu gaya (`.tbl` di `index.css`): satu kartu lembut per tabel, header sunken kapital, sel lega
- Render bertahap (chunked) untuk tabel besar, ambang 100 baris
- Header tabel **tidak pernah sticky** (keputusan terkunci — lihat `DECISIONS.md`)
- Tema terang/gelap per browser, tanpa dependensi font eksternal (IBM Plex lokal)

---

## Halaman Web

| Halaman | Fungsi |
| --- | --- |
| `Dashboard.tsx` | Statistik, sinyal, tabel OLT, aktivitas terbaru |
| `Unconfigured.tsx` | ONU belum diotorisasi + form otorisasi |
| `Configured.tsx` | ONU terotorisasi, filter, aksi massal |
| `Logs.tsx` | Audit trail & log job |
| `OltDetail.tsx` | Detail OLT per tab (Monitoring, Konfigurasi, VLAN) |
| `OnuDetail.tsx` | Detail ONU lengkap (sinyal, grafik, port, layanan) |
| `AuthorizeOnu.tsx` | Form otorisasi ONU |
| `settings/OltManagement.tsx` | CRUD OLT |
| `settings/OnuTypes.tsx` | Katalog tipe ONU |
| `settings/Splitters.tsx` | Splitter / ODP |
| `settings/SpeedProfile.tsx` | Profil kecepatan |
| `settings/UserManagement.tsx` | Akun & peran |
| `settings/GraphData.tsx` | Kelola data grafik |
| `Lainnya.tsx` | Menu tambahan & akun |
| `Setup.tsx` | Buat Superadmin pertama |
| `Login.tsx` | Masuk sistem |

---

## Arsitektur

```
flowchart TD
    subgraph DEVICE["Jaringan"]
        A["OLT ZTE C320"]
        B["ONU"]
    end
    subgraph SERVER["Server Nexfiber"]
        C["FastAPI (API + frontend statis)"]
        D[("PostgreSQL")]
        E["Worker (job queue)"]
        F["Scheduler (polling & purge)"]
    end
    subgraph USER["Pengguna"]
        G["Browser"]
    end
    G --> C
    C --> D
    C -.->|"SSE job stream"| G
    E --> D
    F --> E
    E --> A
    A --> B
```

### Stack teknologi

| Komponen | Teknologi |
| --- | --- |
| Frontend | React 19, Vite 7, TypeScript, Tailwind CSS v4, IBM Plex lokal, Phosphor Icons |
| Backend web | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Driver OLT | netmiko (CLI ZTE C320), pysnmp (SNMP) |
| Database | PostgreSQL 15 (Debian) / 18 (pengembangan) |
| Web server | Tanpa reverse proxy — FastAPI menyajikan API + frontend statis |
| Scheduler | APScheduler di worker + antrean tabel Postgres |
| OS | Debian 12 |

### Alur kerja singkat

1. **Login** → dashboard
2. **Settings** → isi Zone, ONU Types, Splitter, Speed Profile, VLAN
3. **OLT** → tambah OLT beserta kredensialnya (terenkripsi)
4. **Unconfigured** → ONU yang terdeteksi muncul otomatis tiap 1 menit
5. **Otorisasi** → form otorisasi membuat job `authorize_onu`
6. **Job** → worker mengeksekusi perintah CLI ke OLT, status dialirkan via SSE
7. **Configured / Detail ONU** → pantau status, sinyal, dan konfigurasi port
8. **Logs** → semua aktivitas tercatat dan bisa difilter

---

## Persyaratan Server

- **OS:** Debian 12
- **Akses:** root/sudo untuk script instalasi
- **Paket:** PostgreSQL, Python 3 (venv), Node.js + npm (untuk build frontend), git, curl, openssl, snmp
- **Jaringan:** server harus bisa reach IP management OLT (SSH/CLI + SNMP)
- **Akses aplikasi:** LAN-only, HTTP port **8088**, tanpa TLS — jangan port-forward 8088 ke internet dan jangan arahkan domain publik ke port ini
- **RAM/disk:** sesuaikan dengan jumlah OLT/ONU yang dikelola (tidak ada angka minimum yang ditetapkan repo ini)

---

## Struktur Direktori

Setelah instalasi, aplikasi berada di `/opt/nexfiber/`:

```
/opt/nexfiber/
├── install.sh                     # Script instalasi baru
├── update.sh                      # Script upgrade/pembaruan
├── uninstall.sh                   # Script hapus instalasi
├── README.md
├── AGENTS.md
├── DESIGN.md
├── DECISIONS.md                   # Keputusan terkunci (baca ini dulu sebelum mengubah)
├── PRD-FINAL.md
├── NEXFIBER-CLI-REFERENCE.md      # Command CLI OLT yang sudah diverifikasi
├── NEXFIBER-SNMP-OID.md
├── docs/
│   ├── deploy.md                  # Detail deploy LAN-only
│   └── db-maintenance.md
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI + penyajian frontend statis
│   │   ├── core/                  # Keamanan, config
│   │   ├── drivers/               # Driver ZTE C320
│   │   ├── models/                # Model SQLAlchemy
│   │   ├── routers/               # Endpoint API
│   │   ├── schemas/
│   │   ├── services/              # Logika bisnis & job
│   │   ├── repositories/
│   │   └── worker/                # Worker + scheduler
│   ├── alembic/                   # Migrasi database
│   ├── requirements.txt
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── pages/                 # Halaman (lihat tabel Halaman Web)
│   │   ├── components/            # TableCard, Panel, modal, dsb.
│   │   ├── lib/                   # SSE stream, auth, utilitas
│   │   └── styles/index.css       # Token + gaya tabel terpusat (.tbl)
│   └── dist/                      # Hasil build (disajikan FastAPI)
└── venv/                          # Python virtualenv
```

**File sensitif** (tidak ada di repository, dibuat di server):

- `/etc/nexfiber/config.ini` — URL database + secret key (izin 640, milik user `nexfiber`)
- `/var/backups/nexfiber/` — backup `config.ini` + dump database (izin 640)

---

## Struktur Database

Database default: `nexfiber_db`

| Tabel | Fungsi |
| --- | --- |
| `users` | Akun login (argon2) |
| `olts` | Inventaris OLT + kesehatan (CPU/RAM/suhu/uptime/kartu JSONB) |
| `olt_access` | Hak akses user ke OLT |
| `pon_ports` | Port PON per OLT |
| `olt_config_backups` | Backup konfigurasi OLT terenkripsi |
| `onus` | ONU terotorisasi + `port_configs` (terakhir ditulis Nexfiber) |
| `unconfigured_onus` | ONU terdeteksi tapi belum diotorisasi |
| `onu_types` | Katalog tipe ONU |
| `onu_presets` | Preset konfigurasi ONU |
| `speed_profiles` | Profil kecepatan |
| `vlans` | Master VLAN |
| `zones` | Zona |
| `splitters` | Splitter / ODP |
| `jobs` | Antrean job Postgres |
| `activity_logs` | Audit aktivitas |
| `onu_traffic_history` | Riwayat trafik ONU |
| `onu_signal_history` | Riwayat sinyal optik ONU |
| `settings` | Pengaturan key-value (termasuk token logout yang dicabut) |

---

## Source Code Resmi

Instalasi baru dan upgrade/pembaruan menggunakan **repository yang sama**:

|  |  |
| --- | --- |
| **Git** | `https://github.com/erlanggaalfian/nexfiber.git` |
| **Halaman** | https://github.com/erlanggaalfian/nexfiber |

Unduh source dengan salah satu cara berikut (berlaku untuk **install** dan **upgrade**):

**Opsi A — Git (source code):**

```
cd /opt
git clone https://github.com/erlanggaalfian/nexfiber.git
cd nexfiber
```

**Opsi B — ZIP manual (tanpa Git):**

1. Buka https://github.com/erlanggaalfian/nexfiber
2. Klik **Code** → **Download ZIP**
3. Ekstrak ke server, misalnya `/opt/nexfiber`
4. Masuk ke folder tersebut: `cd /opt/nexfiber`

> Untuk **upgrade**, Anda boleh clone/ekstrak ke folder lain (mis. `/opt/nexfiber-upgrade`). Script `update.sh` otomatis mendeteksi instalasi yang sudah ada di `/opt/nexfiber`.

---

## Instalasi Baru

### 1. Unduh source

Ikuti langkah unduh di section **Source Code Resmi** (`https://github.com/erlanggaalfian/nexfiber.git`).

### 2. Jalankan installer

```
chmod +x install.sh
sudo bash install.sh
```

Installer interaktif **8 langkah** — konfigurasi database, bind address, paket sistem, migrasi, build frontend, dan systemd unit.

**Log instalasi:** `/var/log/nexfiber_install.log`

### Input yang diminta installer

| Input | Contoh / default |
| --- | --- |
| Database Name | `nexfiber_db` |
| Database User | `nexfiber_user` |
| Password user DB | auto-generate jika dikosongkan (tersimpan di `config.ini`, tidak dicetak) |
| Bind address API | IP LAN pertama server (default) — `127.0.0.1` = hanya dari server itu sendiri, `0.0.0.0` = semua interface bila sadar dipilih |
| Lanjutkan instalasi? | `[y/N]` |

### Yang dilakukan installer otomatis

1. **[1/8] Konfigurasi Database** — nama/user/password database + bind address API
2. **[2/8] Install paket sistem** — PostgreSQL, Python venv, git, curl, openssl, snmp (Node.js/npm wajib sudah terpasang, dicek di awal)
3. **[3/8] Setup user sistem & direktori** — user `nexfiber`, folder `/opt/nexfiber`, `/etc/nexfiber`, `/var/backups/nexfiber`
4. **[4/8] Setup database PostgreSQL** — database + user
5. **[5/8] Tulis config, siapkan venv, migrasi** — `config.ini` (izin 640), venv + `requirements.txt`, `alembic upgrade head`
6. **[6/8] Build frontend** — `npm ci` + `npm run build`
7. **[7/8] Tulis systemd unit** — `nexfiber-api` (uvicorn `--host <bind> --port 8088`) dan `nexfiber-worker`
8. **[8/8] Verifikasi instalasi** — health check `GET /healthz`; instalasi **tidak** diklaim berhasil bila verifikasi gagal

Instalasi lama yang sudah ada: `config.ini` lama dibackup ke `/var/backups/nexfiber/` dan secret dipertahankan (tidak ditulis ulang).

### Setelah instalasi

Buka `http://<IP-LAN-server>:8088/` di browser, lalu selesaikan **Setup Admin Pertama** di bawah. Perintah cek service:

```
systemctl status nexfiber-api
systemctl status nexfiber-worker
```

> Peringatan installer: akses masih HTTP tanpa TLS, hanya untuk LAN tepercaya. Jangan ekspos port 8088 ke internet. Akses publik butuh reverse proxy TLS di depan + bind `127.0.0.1` — lihat `docs/deploy.md`.

---

## Setup Admin Pertama

1. Buka URL aplikasi di browser (mis. `http://192.168.1.10:8088/`)
2. Jika belum ada user, diarahkan ke halaman **Setup**
3. Buat username dan password Superadmin pertama
4. Login → Dashboard

Halaman `/setup` mengembalikan 404 setelah user pertama ada — tidak ada password default, dan tidak ada script pembuat admin manual.

---

## Upgrade / Pembaruan

Gunakan `update.sh` saat ada versi baru. Script ini:

- Memvalidasi instalasi yang sudah ada (`/opt/nexfiber` + `/etc/nexfiber/config.ini`)
- **Backup database wajib sebelum perubahan** (`pg_dump` ke `/var/backups/nexfiber/`) — tanpa `pg_dump`, update dibatalkan sebelum perubahan apa pun
- Backup `config.ini` (secret dipertahankan, tidak ditulis ulang)
- Menyalin kode terbaru, update dependency Python, migrasi database, dan build ulang frontend
- **Backend dan frontend selalu diperbarui bersamaan** — wajib, karena token SSE frontend hanya kompatibel dengan backend yang sama
- Health check `GET /healthz` setelah start; bila API tidak sehat, kode lama di-restore otomatis — **tetapi database TIDAK di-rollback otomatis** (restore manual dari dump bila migrasi sudah jalan)

**Log upgrade:** tidak ada file log khusus; output script tampil di terminal.

### 1. Unduh source versi terbaru

Unduh dari **repository yang sama** dengan instalasi: `https://github.com/erlanggaalfian/nexfiber.git`

Ikuti **Opsi A (Git)** atau **Opsi B (ZIP)** di section **Source Code Resmi**. Pastikan source yang diunduh adalah versi terbaru.

### 2. Jalankan script upgrade

```
chmod +x update.sh
sudo bash update.sh
```

### Langkah update

| Langkah | Isi |
| --- | --- |
| `[0/5]` | Hentikan service + backup (config + dump database) |
| `[1/5]` | Sinkronkan kode ke `/opt/nexfiber` |
| `[2/5]` | Update dependency Python |
| `[3/5]` | Migrasi database (`alembic upgrade head`) |
| `[4/5]` | Build ulang frontend (`npm ci` + `npm run build`) |
| `[5/5]` | Start service + health check |

Setelah upgrade: bila tab browser lama masih menampilkan tampilan lama, tutup tab dan buka ulang (`index.html` disajikan dengan `Cache-Control: no-cache` + validasi ETag, jadi tab baru selalu mengambil bundle terbaru).

### File yang tidak ditimpa saat upgrade

| File / data | Alasan |
| --- | --- |
| `/etc/nexfiber/config.ini` | Kredensial database + secret produksi |
| Pilihan bind dari instalasi | Unit systemd tidak ditulis ulang oleh `update.sh` |
| Data tabel operasional | Data ONU, job, log, backup tidak diubah |

---

## Uninstall

Gunakan `uninstall.sh` untuk menghapus Nexfiber dari server. Script ini **tidak** menghapus paket sistem (PostgreSQL, Python, Node.js).

**Yang dilakukan script, berurutan:**

1. Konfirmasi interaktif: `Hapus instalasi Nexfiber (service + /opt/nexfiber + /etc/nexfiber)? [y/N]`
2. Backup `config.ini` ke `/var/backups/nexfiber/` (wajib — berisi secret untuk mendekripsi kredensial OLT di database yang dipertahankan)
3. Backup database wajib (`pg_dump`) — bila `pg_dump` tidak tersedia atau dump gagal, uninstall **dibatalkan** tanpa menghapus apa pun
4. Menonaktifkan dan menghapus unit `nexfiber-api` + `nexfiber-worker`
5. Menghapus folder `/opt/nexfiber` dan `/etc/nexfiber`

### Yang dihapus vs dipertahankan

| Item | Uninstall |
| --- | --- |
| Unit systemd `nexfiber-api` + `nexfiber-worker` | ✅ Dihapus |
| Folder `/opt/nexfiber` dan `/etc/nexfiber` | ✅ Dihapus |
| Backup `/var/backups/nexfiber/` | ❌ Tetap ada |
| Database & user PostgreSQL | ❌ Dipertahankan (tidak ada opsi hapus otomatis) |
| Paket sistem | ❌ Tetap terpasang |

### Hapus database manual (bila perlu)

Script mencetak perintahnya setelah selesai — contoh untuk default:

```
sudo -u postgres psql -c 'DROP DATABASE nexfiber_db;'
sudo -u postgres psql -c 'DROP ROLE nexfiber_user;'
```

> Jangan hapus file backup `/var/backups/nexfiber/config.ini.*` selama database dipertahankan — secret di file itu dibutuhkan untuk mendekripsi kredensial OLT.

---

## Backup Konfigurasi OLT & Retensi

### Backup konfigurasi OLT

- Backup konfigurasi OLT disimpan di tabel `olt_config_backups` dengan isi **terenkripsi** (prefix `enc:`, format lama plaintext masih bisa dibaca).
- Belum ada endpoint restore yang membaca backup — backup saat ini bersifat arsip, bukan jalur restore.

### Housekeeping otomatis (worker)

| Jadwal | Isi |
| --- | --- |
| 03:00 | Purge data grafik, dicatat sebagai `housekeeping.purge_graph` |
| 03:30 | Purge umum, dicatat sebagai `housekeeping.purge`: log aktivitas 365 hari (sesuai PRD), job terminal 180 hari, backup 90 hari — **angka job dan backup masih PROVISIONAL**, ubah konstantanya sebelum purge pertama setelah deploy bila perlu |
| Selalu | Backup terbaru per OLT **tidak pernah** dihapus purge |

---

## Keamanan

| Lapisan | Implementasi |
| --- | --- |
| Password user | argon2 |
| Kredensial OLT | Fernet v2 (PBKDF2-HMAC-SHA256, salt acak, 600.000 iterasi, fallback baca format lama, upgrade oportunistik saat disimpan ulang) |
| Session | Bearer token (JWT); logout mencabut token via `jti` di tabel `settings` |
| SSE stream | Token sekali pakai 120 detik (`POST /api/stream/jobs/token`); token akses di query string ditolak (401) |
| Kredensial OLT di API | Tidak pernah dikirim balik ke frontend, tidak pernah masuk log |
| Backup konfigurasi OLT | Terenkripsi di database |
| Password WiFi | Tidak pernah disimpan (hanya status/mode/SSID terakhir ditulis) |
| Akses aplikasi | LAN-only, HTTP port 8088, tanpa TLS — jangan ekspos ke internet |
| Server | Jalankan install / upgrade / uninstall hanya sebagai root/sudo |

**File rahasia — jangan dibagikan atau unggah ke publik:**

- `/etc/nexfiber/config.ini`
- `/var/backups/nexfiber/config.ini.*` dan `/var/backups/nexfiber/db-*.sql`
- Isi tabel `olt_config_backups` dan kredensial OLT apa pun

---

## Troubleshooting

### API tidak sehat setelah update

```
sudo journalctl -u nexfiber-api -n 50
sudo journalctl -u nexfiber-worker -n 50
sudo systemctl status nexfiber-api nexfiber-worker
```

Bila update gagal di tengah jalan, `update.sh` me-restore kode lama otomatis — tetapi database tidak di-rollback otomatis; restore manual dari dump di `/var/backups/nexfiber/` bila migrasi sudah jalan.

### Tab browser lama menampilkan tampilan lama

Tutup tab dan buka ulang. `index.html` disajikan dengan `Cache-Control: no-cache` + validasi ETag sejak commit `8b47a1a`, jadi tab baru selalu mengambil bundle terbaru — tab lama yang sudah terbuka tetap menjalankan bundle lamanya.

### SSE stream / status job tidak update

Pastikan backend dan frontend diperbarui **bersamaan** via `update.sh`. Frontend lama mendapat 401 pada stream bila backend sudah memakai token SSE sekali pakai, dan sebaliknya.

### Database tidak terjangkau

```
sudo systemctl status postgresql
sudo cat /etc/nexfiber/config.ini   # periksa baris url (izin file 640, butuh sudo)
```

Tes backend yang butuh database akan skip bila Postgres tidak terjangkau — itu perilaku tes, bukan bukti database rusak.

### OLT tidak terjangkau

- Pastikan server bisa reach IP management OLT (SSH/CLI + SNMP) dan tidak terhalang firewall/ACL.
- Perintah CLI yang belum terverifikasi ke perangkat nyata ditandai `UNVERIFIED` di kode — jangan jalankan aksi destruktif (reboot, restore factory) ke OLT produksi; uji hanya ke ONU test bila ada.

### Port 8088 tidak bisa diakses dari LAN

Periksa bind address di unit terinstal (bukan di script — `update.sh` tidak menulis ulang unit):

```
sudo systemctl cat nexfiber-api   # lihat --host di ExecStart
```

Ubah bind pada instalasi yang sudah berjalan:

```
sudo systemctl edit nexfiber-api   # ubah --host
sudo systemctl daemon-reload
sudo systemctl restart nexfiber-api
```

### Instalasi gagal

```
sudo tail -50 /var/log/nexfiber_install.log
```

### Dokumen pendukung

- `PRD-FINAL.md` — fitur dan skema (catatan: rencana Caddy di PRD sudah kedaluwarsa untuk server ini)
- `DESIGN.md` — tampilan dan wireframe
- `DECISIONS.md` — keputusan terkunci (baca dulu sebelum mengubah apa pun)
- `docs/deploy.md` — detail deploy LAN-only dan langkah akses publik bila suatu hari diputuskan
- `docs/db-maintenance.md` — perawatan database

---

## Lisensi & Kontribusi

Lisensi belum dinyatakan di repository ini (tidak ada file `LICENSE`).

### Author

**Erlangga Alfian**

📧 <erlanggaalfian82@gmail.com>

🌐 https://github.com/erlanggaalfian/nexfiber.git

Jika project ini membantu:

- Berikan ⭐ pada repository
- Fork & improve
- Submit issue atau pull request
