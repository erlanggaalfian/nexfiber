# ROADMAP.md — Nexfiber, pengembangan paralel via sub-agent

Status repo saat tulisan ini dibuat: backend skeleton lengkap (model, router,
service, driver ZTE, worker) sampai level stub; frontend baru punya shell
(header+bottom nav), Login, Setup, Dashboard kosong. Instalasi lokal sudah
jalan di `http://<IP>:8088` (lihat install.sh/update.sh). Tinjau `PRD-FINAL.md`
dan `DESIGN.md` sebagai sumber kebenaran untuk fitur/tampilan — **tapi untuk
poin yang sudah diputuskan ulang (c1–c12 dan seterusnya), `DECISIONS.md`
menang**, karena PRD/DESIGN belum di-sync ke semua keputusan itu. Baca
`DECISIONS.md` SEBELUM mulai kerja apa pun di roadmap ini — isinya jawaban
final yang jangan ditanya ulang.

## Prinsip pembagian kerja paralel

Tiap sub-agent kerja di **file yang tidak tumpang tindih** dengan agent lain
yang jalan bersamaan, supaya tidak rebutan merge/conflict. Dependensi lintas
track ditandai di bawah — track yang depend harus nunggu track sumbernya
commit dulu (atau pakai interface/schema yang sudah disepakati di awal).

Semua track WAJIB: baca `AGENTS.md` dan skill di `.github/skills/` dulu,
test dulu sebelum lapor selesai (`tdd`), tidak nyentuh OLT produksi nyata
kecuali eksplisit diizinkan (satu-satunya target uji: `gpon-onu_1/4/1:11`,
OLT id=8), commit kecil & sering supaya gampang direview.

---

## Fase A — fondasi data (sebelum halaman apa pun, satu agent, tidak paralel)

**A1. Skema master data lengkap**
- Cek `backend/app/models/{zone,onu_type,speed_profile,splitter,vlan}.py` ada
  semua field sesuai PRD §4.6 (zones, onu_types, onu_presets kalau belum ada).
- Alembic migration final untuk semua tabel master sebelum halaman Settings
  dibangun — begitu Fase B mulai, schema master TIDAK boleh berubah lagi
  tanpa koordinasi (semua track B bergantung pada schema ini).
- Seed dev data (tidak masuk repo, hanya script lokal): 2–3 zone, 2–3 onu
  type, 1 speed profile per role.

Output: migration + model final, dilaporkan ke semua track B sebelum mereka mulai.

---

## Fase B — Settings pages (4 track paralel, backend+frontend per halaman)

Alasan urutan: Form Otorisasi ONU (Fase C) butuh dropdown dari sini. Tiap
track = 1 halaman Settings, backend (router+service+schema) + frontend
(page+komponen) digarap agent yang sama supaya kontrak API tidak perlu
disepakati lintas orang.

**B1. OLT Management** (`/settings/olts`)
- Backend: CRUD OLT (owner_id, credential encrypted, snmp_community_rw_enc),
  endpoint test-koneksi, scope Superadmin (assign owner) vs Admin (auto-owner).
- Frontend: list + form tambah/edit, badge status online/offline.
- File: `backend/app/routers/olts.py`, `services/olt_service.py`,
  `frontend/src/pages/settings/OltManagement.tsx` (baru).

**B2. User Management** (`/settings/users`)
- Backend: CRUD user scoped per role (Superadmin lihat semua, Admin lihat
  User miliknya saja), reset password, nonaktifkan (blokir kalau Admin masih
  punya OLT).
- Frontend: list + form, filter per role.
- File: router/service user baru, `frontend/src/pages/settings/UserManagement.tsx`.

**B3. ONU Types & Splitters/Zone** (`/settings/onu-types`, `/settings/splitters`)
- Backend: CRUD onu_types (vendor/model/capability), CRUD zones, CRUD
  splitters (ratio, zone_id, parent/child kalau bertingkat).
- Frontend: dua halaman list+form sederhana.
- File: router/service baru per entity, 2 halaman frontend baru.

**B4. Speed Profile + VLAN (backend-only untuk VLAN)**
- Backend Speed Profile: CRUD kecepatan upload/download, dropdown pilih
  VLAN existing (read-only terhadap VLAN di tahap ini).
- Backend VLAN: `POST/DELETE /api/vlans`, driver push ke OLT, job type baru
  (scope sudah diputuskan: backend only, UI VLAN penuh nanti di Detail OLT).
- Frontend: halaman Speed Profile (list+form+tombol Simpan ke OLT/Baca dari OLT).
- File: `backend/app/models/vlan.py`, router/service vlan+speed_profile baru,
  `frontend/src/pages/settings/SpeedProfile.tsx`.

**Sinkronisasi di akhir Fase B:** semua 4 track lapor daftar endpoint API
final (path, method, request/response shape) sebelum Fase C mulai — supaya
Form Otorisasi tahu dropdown mana manggil endpoint apa.

---

## Fase C — halaman inti ONU/OLT (3 track paralel)

**C1. Unconfigured + Form Otorisasi** (`/unconfigured`, `/unconfigured/authorize`)
- Backend: `sync_unconfigured` job (1 menit) sudah ada di worker — pastikan
  endpoint list unconfigured + endpoint `authorize_onu` (scope MVP: onu+type
  +sn+tcont+gemport+service-port, VLAN dari dropdown Fase B4) dites end-to-end.
- Frontend: list ONU belum terdaftar per OLT + form otorisasi (dropdown
  Zone/ONU Types/Splitter dari Fase B3, VLAN dari Fase B4).
- Depend: Fase B3 (dropdown), B4 (VLAN dropdown).

**C2. Configured + Detail ONU** (`/configured`, `/onu/:id`)
- Backend: list ONU terkonfigurasi (filter per bucket sinyal Good/Fair/Weak/
  Critical, §3.4.2), endpoint detail ONU (optical, config, reboot — reboot
  ditandai `# UNVERIFIED` dan tidak dieksekusi ke device nyata oleh agent).
- Frontend: tabel Configured (bulk actions, filter signal, CSV export),
  halaman Detail ONU (tab General/Optical/Config sesuai wireframe DESIGN §12).
- Depend: tidak depend ke B, bisa mulai bareng C1.

**C3. Detail OLT** (`/olt/:id`)
- Backend: endpoint detail OLT (health: cpu/ram/suhu/uptime/cards — kolom
  sudah ditambah ke tabel `olts`), tab VLANs (UI penuh CRUD pakai backend
  dari B4), job metrics gabung (`sync_olt_metrics` hasil Fase B4 kebutuhan
  job sudah disepakati: gabung ke job optical, bukan job baru).
- Frontend: halaman Detail OLT dengan tab Info/VLANs/PON.
- Depend: Fase B4 (backend VLAN), B1 (data OLT dasar).

---

## Fase D — Dashboard & Logs (2 track paralel, terakhir karena depend ke semua data di atas)

**D1. Dashboard penuh** (`/`)
- Isi final sesuai PRD §3.4.2/DESIGN §12.2: strip 4 sel, baris sinyal
  (4 bucket), tabel OLT (tanpa sparkline — ditunda), aktivitas terbaru,
  "Diperbarui HH:MM" + tombol Refresh. HAPUS blok v3 (Perlu tindakan,
  histogram Rx, 6 PON terpadat, countdown) — sudah diputuskan dihapus semua.
- Depend: data OLT (B1/C3) dan data ONU (C1/C2) harus sudah ada untuk diuji
  dengan data nyata, bukan mock.

**D2. Logs + Akun** (`/logs`, halaman Lainnya sisanya)
- Backend: endpoint activity log (filter, paginasi, retensi 365 hari, non-
  deletable dari UI).
- Frontend: halaman Logs (tabel+filter), lengkapi halaman Lainnya (ganti
  password, tema, logout — kerangka sudah ada di `Lainnya.tsx`).
- Depend: activity_log sudah dipakai di berbagai service lain (B/C) sebagai
  penulis log — pastikan semua service itu benar-benar menulis ke sana
  sebelum lapor halaman Logs selesai.

---

## Command palette ⌘K (opsional, track sendiri, kapan saja setelah Fase B)
- Frontend-only: search cepat ke OLT/ONU/halaman Settings. Tidak depend ke
  backend baru (pakai endpoint list yang sudah ada). Bisa disisipkan sebagai
  track ke-5 di Fase B atau track solo di Fase C.

---

## Ringkasan paralelisme

| Fase | Track paralel | Blocking sebelumnya |
|---|---|---|
| A | 1 (solo) | — |
| B | B1, B2, B3, B4 (4 agent) | A selesai |
| C | C1, C2, C3 (3 agent) | B selesai (C1/C3 depend B3/B4; C2 bisa mulai bareng) |
| D | D1, D2 (2 agent) | C selesai |
| ⌘K | solo, kapan saja | B selesai |

Maksimal paralel sehat: **4 agent** di Fase B (sesuai batas delegate_task
umum). Fase C turun ke 3, Fase D ke 2 — makin ke ujung makin saling depend,
makin kecil manfaat paralelnya.

## Definition of done per track
- Test lulus (`pytest` backend relevan, minimal smoke test frontend kalau ada).
- Dicoba nyata di `http://<IP>:8088` (bukan cuma `npm run build` tanpa run).
- Tidak ada perubahan skema DB yang belum dikoordinasikan ke track lain.
- Tidak menyentuh kode di luar file yang jadi scope track-nya.
