# Prompt Nexfiber — tempel satu per satu ke chat agent di VS Code

Aturan tetap sudah ada di `AGENTS.md` (dibaca otomatis oleh sebagian besar agent; kalau tidak, prompt 0 memaksanya).
Kirim prompt berikutnya hanya setelah tahap sebelumnya terbukti jalan.

---

## Prompt 0 — Baca & pahami (tanpa coding)
```
Baca penuh AGENTS.md, PRD-FINAL.md, DESIGN.md, NEXFIBER-CLI-REFERENCE.md, NEXFIBER-SNMP-OID.md.
Jangan menulis kode dulu. Balas dengan:
1) ringkasan aplikasi maks 10 poin,
2) struktur folder repo yang akan kamu buat,
3) daftar tahap build sesuai urutan di PROMPTS.md,
4) semua hal yang menurutmu ambigu atau bertentangan antar dokumen (sebut pasal/section-nya).
```

## Prompt 1 — Scaffold
```
Tahap 1: scaffold repo sesuai AGENTS.md.
- backend/: FastAPI + SQLAlchemy 2 + Alembic, config dari config.ini/.env, endpoint GET /healthz.
- frontend/: Vite 7 + React 19 + TS + Tailwind v4 + react-router v7 (mode library) + TanStack Query v5 + Phosphor + @fontsource IBM Plex. Token warna & font dari DESIGN.md §3–§4 (terang + gelap).
- .gitignore (venv, node_modules, .env, config.ini, dist).
Jalankan backend & frontend lokal, tunjukkan output /healthz dan halaman kosong terbuka. Berhenti.
```

## Prompt 2 — Database
```
Tahap 2: model SQLAlchemy + migrasi Alembic pertama untuk semua tabel di PRD-FINAL.md §4.6 termasuk "Tabel tambahan v4",
users.role (superadmin/admin/user), users.admin_id, olts.owner_id, CHECK constraint role user ⇔ admin_id.
Kredensial OLT disimpan terenkripsi. Jalankan `alembic upgrade head` ke PostgreSQL lokal dan tampilkan daftar tabel. Berhenti.
```

## Prompt 3 — Auth, peran, cakupan OLT
```
Tahap 3: login/logout/sesi, halaman /setup (hanya saat users kosong → buat Superadmin pertama),
peran Superadmin/Admin/User dan dependency `scope_olt_ids(user)` sesuai PRD-FINAL.md §3.7.
Akses di luar cakupan = 404. Tulis test: User tidak bisa membaca OLT Admin lain, Admin tidak bisa membuat Admin, /setup 404 setelah ada user.
Jalankan test dan tempel hasilnya. Berhenti.
```

## Prompt 4 — Kerangka UI (header + navigasi bawah)
```
Tahap 4: app shell persis DESIGN.md §11 dan §11.1:
- ≥1024px: header atas (logo, Dashboard, Unconfigured+badge, Configured, Settings ▾, Logs, cari ⌘K, Sistem aktif, avatar). Tanpa sidebar.
- <1024px: top bar + navigasi bawah 5 tab (Dashboard, Unconfigured, Configured, Logs, Lainnya), gaya Android modern.
- Halaman Login & Setup (§12.1). Menu disembunyikan sesuai peran. Halaman lain isi placeholder kosong + route 404.
- PWA manifest (display standalone, tanpa cache offline).
Cek di lebar 1440px, 1024px, 390px, tema terang & gelap; laporkan hasil tiap lebar. Berhenti.
```

## Prompt 5 — Driver ZTE + job worker
```
Tahap 5: interface OltDriver + implementasi ZTE (netmiko untuk CLI, pysnmp untuk SNMP) memakai command/OID dari
NEXFIBER-CLI-REFERENCE.md dan NEXFIBER-SNMP-OID.md. Worker job tabel Postgres (SKIP LOCKED + LISTEN/NOTIFY),
job: test_connection, sync_unconfigured, sync_onu_status (1 menit), sync_optical (15 menit), provision_onu, reboot_onu.
Parser CLI wajib unit test dengan fixture teks. Jalankan test. Jangan sentuh OLT nyata sampai saya izinkan. Berhenti.
```

## Prompt 6 — Settings → OLT Management + Detail OLT
```
Tahap 6: halaman OLT Management (PRD-FINAL.md §3.4.8, DESIGN §12.8) dan Detail OLT (PRD §3.4.7, DESIGN §12.7)
beserta API-nya. Tambah OLT oleh Admin = owner otomatis; Superadmin pilih pemilik. Simpan menjalankan job test_connection.
Saya akan uji ke satu OLT nyata — beri tahu langkah ujinya. Berhenti.
```

## Prompt 7 — Dashboard
```
Tahap 7: Dashboard sesuai PRD §3.4.2 dan DESIGN §12.2. Query per blok (satu gagal tidak merusak halaman),
refetch 60 detik saat tab aktif. Data nyata dari DB, tanpa angka karangan. Berhenti.
```

## Prompt 8 — Unconfigured + Otorisasi
```
Tahap 8: Unconfigured (PRD §3.4.3, DESIGN §12.3) dan form Otorisasi (PRD §3.4.4, DESIGN §12.4), termasuk preset,
index ONU otomatis (ID kosong terkecil), Nama pelanggan wajib, status job di tombol. Berhenti dan beri langkah uji ke ONU test.
```

## Prompt 9 — Configured
```
Tahap 9: Configured (PRD §3.4.5, DESIGN §12.5): cari, 10 filter multi-pilih di URL, chip filter, pagination,
aksi massal, Export CSV, kartu mobile (DESIGN §12.10). Berhenti.
```

## Prompt 10 — Detail ONU
```
Tahap 10: Detail ONU (PRD §3.4.6, DESIGN §12.6): kartu sinyal + grafik 24j/7h/30h, panel pelanggan/perangkat,
tab (WiFi & TR-069 = "Segera"), menu Aksi ▾ dengan konfirmasi; Restore factory & Hapus disembunyikan untuk User. Berhenti.
```

## Prompt 11 — Settings lain + Logs
```
Tahap 11: User Management, ONU Types, Splitters & Zone, Speed Profile (PRD §3.4.9–§3.4.12, DESIGN §12.8) dan Logs
(PRD §3.4.15, DESIGN §12.9, tanpa tombol hapus). VPN & TR-069 tetap "Segera". Berhenti.
```

## Prompt 12 — Siap deploy
```
Tahap 12: cocokkan install.sh/update.sh/uninstall.sh dengan struktur repo nyata (path, nama service, build frontend,
Caddy SPA fallback non-/api ke index.html). Jalankan `bash -n` ke ketiganya, lalu jalankan checklist DESIGN §14 untuk
semua halaman. Laporkan yang belum lolos. Jangan jalankan install.sh di server saya.
```

---

### Kalau agent menyimpang
```
Berhenti. Itu menyimpang dari AGENTS.md / PRD-FINAL.md §[x] / DESIGN.md §[x]: [jelaskan]. Perbaiki sesuai dokumen, jangan tambah hal lain.
```
