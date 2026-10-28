# AGENTS.md — aturan tetap untuk AI coding agent (Nexfiber)

Nexfiber = aplikasi web manajemen OLT/ONU untuk ISP. Greenfield, dirawat satu orang.

## Sumber kebenaran (baca sebelum menulis kode)
- `PRD-FINAL.md` — fitur, isi tiap halaman (§3.3–§3.4), peran & hak akses (§3.7), arsitektur, skema DB, deploy.
- `DESIGN.md` — tampilan: token warna/font, header desktop (§11), navigasi bawah Android (§11.1), wireframe per halaman (§12), pola interaksi (§13), checklist (§14).
- `NEXFIBER-CLI-REFERENCE.md` — command CLI OLT per vendor (sudah diverifikasi ke perangkat nyata).
- `NEXFIBER-SNMP-OID.md` — OID SNMP + enum status (sudah diverifikasi).
- Konflik: soal tampilan ikut DESIGN.md, soal fitur/hak akses ikut PRD. Bila keduanya diam: **tanya**, jangan menebak.
- Semua trade-off di PRD berstatus "Disetujui". Jangan diperdebatkan ulang.

## Stack terkunci (jangan diganti, jangan tambah dependency tanpa izin)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL 18, argon2, netmiko (CLI), pysnmp (SNMP).
- Job queue: tabel Postgres `SELECT … FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`. **Bukan** Celery/Redis.
- Frontend: React 19, Vite 7, TypeScript, Tailwind CSS v4, shadcn/ui (copy-in, token di-override), Phosphor Icons (npm), react-router v7 mode library (`BrowserRouter` + `Routes`), TanStack Query v5, TanStack Table, React Hook Form + Zod, font `@fontsource` IBM Plex Sans/Mono.
- **Dilarang**: Next.js, Lucide, Redux/Zustand untuk data server, CDN apa pun (Google Fonts dll — server bisa tanpa internet), Docker/K8s.
- Deploy: systemd, LAN-only tanpa Caddy (keputusan terkunci di DECISIONS.md: satu port HTTP langsung, port 8088, frontend disajikan FastAPI; rencana Caddy di PRD sudah kedaluwarsa untuk server ini). `install.sh` / `update.sh` / `uninstall.sh` di root repo sudah final; ubah hanya path/variabel bila struktur folder nyata berbeda. Lihat `docs/deploy.md`.

## Aturan produk yang sering terlewat
- Navigasi: **desktop ≥ 1024px menu di header atas** (tanpa sidebar). **< 1024px navigasi bawah 5 tab** (Dashboard · Unconfigured · Configured · Logs · Lainnya). Lihat DESIGN §11–§11.1.
- Peran: Superadmin / Admin / User + `olts.owner_id`, `users.admin_id`. Pembatasan cakupan OLT dicek **di backend pada setiap endpoint** (termasuk SSE, export, job). Di luar cakupan = 404.
- Semua aksi yang menyentuh OLT = **job**. UI menampilkan status job, tanpa optimistic update.
- MVP = ZTE saja lewat interface `OltDriver`. CDATA, TR-069, VPN = Phase 2 (menu tampil "Segera", tanpa kode).
- Status ONU dipoll SNMP tiap 1 menit (tulis hanya saat berubah); sinyal optik tiap 15 menit.
- Superadmin pertama dibuat lewat halaman `/setup` saat tabel users kosong. Tidak ada password default.
- Kredensial OLT terenkripsi di DB, tidak pernah dikirim balik ke frontend, tidak pernah masuk log (`[REDACTED]`).

## Selera UI pemilik (wajib)
Simpel, padat, modern. Tanpa teks penjelas panjang, tanpa popup/tooltip bantuan, tanpa garis pemisah berlebih, tanpa penomoran berulang, tanpa emoji, tanpa gradien/glow/glass. Ikuti wireframe persis (posisi & kesejajaran).

## Cara kerja
- Kerjakan **satu tahap per giliran**, lalu berhenti dan laporkan: file yang diubah, perintah yang dijalankan, hasilnya. Tunggu "lanjut".
- "Selesai" = sudah dijalankan & dicek (test lulus / halaman terbuka / endpoint menjawab), bukan sekadar ditulis. Tempel output nyatanya.
- Kode boring: fungsi pendek, tanpa abstraksi yang tidak diminta, tanpa scaffolding "untuk nanti".
- **Tanpa duplikasi logika (DRY, wajib di semua lapisan — backend, frontend, driver, migrasi).** Kalau logika yang sama (perhitungan, validasi, mapping, query, parsing) sudah ada dan dibutuhkan di tempat lain, PANGGIL/PAKAI yang sudah ada — jangan tulis ulang versi baru dengan nama/lokasi berbeda walau "kelihatannya beda konteks". Sebelum menulis fungsi/logika baru: cek dulu apakah sudah ada yang setara (grep nama/kata kunci terkait). Kalau 2+ tempat butuh logika yang sama, itu tandanya harus ditarik jadi satu fungsi/modul bersama — jangan biarkan dua salinan berjalan paralel, walau saat ini isinya identik, karena akan diam-diam menyimpang saat salah satu diubah dan yang lain lupa diupdate. Contoh yang DILARANG: bucket sinyal 4 level dihitung ulang terpisah di komponen tabel ONU dan di komponen signal bar — harus satu fungsi `getSignalBucket()` dipakai oleh keduanya.
- Parser output CLI wajib punya unit test dengan fixture teks (PRD Bagian 5, modul kritis).
- Jangan pernah menulis IP, community, password, atau serial asli ke repo. Pakai `.env` / `config.ini` yang di-gitignore.
- Commit kecil per tahap, pesan jelas.
