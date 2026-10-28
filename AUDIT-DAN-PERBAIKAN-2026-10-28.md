# Audit Menyeluruh Nexfiber — Temuan dan Pengerjaan

Tanggal audit dan perbaikan: **2026-10-28**.
Basis kode: commit `4c77449` ("fix(ui): placeholder modal speed profile 'Jangan ubah' -> 'Pilih profil ...'").
Semua perubahan di dokumen ini **belum di-commit dan belum di-push** (tidak ada perintah commit/push yang dijalankan).
Perintah pengguna yang memicu dokumen ini (19:29 WIB): perbaiki semuanya dengan beberapa sub-agent paralel,
lalu buatkan file .md tentang temuan apa saja dan pengerjaan apa saja secara detail.

Cara baca status di dokumen ini:

- **Selesai** = diperbaiki dan terverifikasi pada lingkup yang disebutkan.
- **Sebagian** = diperbaiki pada satu sisi, tetapi ada sisi lain yang sengaja tidak dikerjakan (alasan ditulis).
- **Diserahkan / belum** = tidak dikerjakan pada putaran ini, atau sengaja tidak dikerjakan karena butuh keputusan
  pengguna / sintaks perangkat yang belum terbukti. Bagian ini ditulis apa adanya, bukan disembunyikan.
- **VoIP tidak disentuh sama sekali** pada semua putaran, sesuai instruksi pengguna yang masih berlaku
  ("untuk voip jangan di kembangkan dulu"). Temuan VoIP dari putaran sebelumnya tetap terbuka di bawah
  dan bukan kelalaian.

## Ringkasan eksekutif

Audit dilakukan oleh 6 agen analisis statis paralel (bukan pengujian perangkat nyata), mencakup:
auth/RBAC/scope, lifecycle ONU/OLT + job/worker/sync, OnuDetail/modal/trafik/sinyal/diagnostik,
master data/VLAN/speed profile/preset/zone/splitter/graph, navigasi frontend + kontrak API,
serta validasi/error/keamanan/deploy/migrasi lintas bidang.

Perbaikan dilakukan oleh 5 agen paralel dengan kepemilikan file yang saling lepas:

| Area | Agen | Lingkup |
|---|---|---|
| 1 | Auth/RBAC/keamanan | `core/security.py`, `core/deps.py`, `core/config.py`, `auth_service.py`, `user_service.py`, `user_repo.py`, `routers/auth.py`, `routers/users.py`, `routers/jobs.py`, `job_service.py` (bagian get/cancel/stream), `activity_log_repo.py`, `main.py` (handler error + 404 /api), `lib/auth.tsx`, `Login.tsx`, `Setup.tsx`, `UserManagement.tsx` |
| 2 | Lifecycle/job/sync | `onu_service.py`, `olt_service.py`, `sync_service.py`, `olt_onboarding.py`, `job_repo.py`, `onu_repo.py` (sync/authorize), `worker/*`, `zte_c320.py` (oper_state/uplink hyphen/CPU), `onu_report.py`, `routers/onus.py` (list/export), `Configured.tsx`, `Unconfigured.tsx`, `AuthorizeOnu.tsx` |
| 3 | OnuDetail/modal/trafik | `OnuDetail.tsx`, `components/onu/*`, `lib/onuActions.ts`, `lib/traffic.ts`, `lib/profileName.ts`, `onu_action_service.py`, `zte_onu_actions.py`, `onu_traffic_service.py`, `onu_traffic_history_service.py`, `routers/onu_actions.py` |
| 4 | Master data/graph/OltDetail-VLAN | `master_data_service.py`, `vlan_service.py`, `speed_profile_service.py`, `graph_data_service.py`, `master_data_repo.py`, `routers/speed_profiles.py`, `OltDetail.tsx` (VLAN/port), `SpeedProfile.tsx`, `Splitters.tsx`, `OnuTypes.tsx`, `GraphData.tsx`, `OltManagement.tsx` |
| 5 | Lintas bidang/deploy/migrasi/navigasi | `models/*.py` (indeks/constraint saja), migrasi Alembic **baru**, `install.sh`, `update.sh`, `uninstall.sh`, `main.tsx`, `lib/nav.ts`, `components/Layout.tsx`, `Dashboard.tsx`, `Logs.tsx`, `lib/api.ts`, `lib/jobs.ts`, `Lainnya.tsx`, `routers/onus.py` (multi-filter saja) |

Setelah kelima agen selesai, agen utama (induk) melakukan verifikasi gabungan, menyelesaikan
3 konflik antar-agen/tes lama, lalu menulis dokumen ini. Hasil verifikasi gabungan ada di bagian akhir.

Catatan penting tentang konflik antar-agen yang sempat muncul selama pengerjaan paralel
(sebelum verifikasi gabungan): pada satu titik, tes `test_onu_detail_c2.py` sempat gagal karena
guard `is_active` Area 2 menolak objek tes palsu tanpa atribut `is_active`, dan
`test_olt_inventory_sync.py` sempat gagal karena perubahan `sync_service.py` Area 2.
Keduanya sudah selesai di dalam laporan akhir Area 2 (guard ditulis `is False`, bukan `not ...`,
dan perilaku pengosongan kolom dikembalikan — lihat temuan Lifecycle no. 15).
Hasil akhir gabungan: **tidak ada lagi kegagalan dari penyebab itu**.

## Hasil verifikasi gabungan (agen utama, setelah semua area selesai)

Perintah yang dijalankan (dari direktori yang benar — menjalankan pytest dari root repo gagal
karena `ModuleNotFoundError: No module named 'app'`):

- `cd ~/workspace/nexfiber/backend && /tmp/nexfiber-venv/bin/python -m pytest tests/ -q`
  → **331 passed, 27 skipped, 0 failed**.
  Baseline sebelum putaran ini: 316 passed, 27 skipped. Kenaikan berasal dari tes baru
  `test_auth_area1.py` (Area 1), `test_area2_lifecycle.py` (Area 2), dan `test_log_category_filter.py` (putaran 2).
  27 skipped adalah tes perangkat nyata yang butuh Postgres/OLT (sama seperti baseline).
- `cd ~/workspace/nexfiber/frontend && npm run build` → **lolos** (tsc + vite, ~10 detik).
- `cd ~/workspace/nexfiber/frontend && npm run check` → **lolos, exit 0** (71 baris `ok`).
  Pemeriksaan layout Playwright (`.layout.mjs`) tidak bisa dijalankan di lingkungan ini karena
  Playwright tidak tersedia — keterbatasan lingkungan yang sudah ada, bukan akibat perubahan ini.
- `git status` → 77 file diubah + 5 file baru (lihat daftar file di bagian akhir).
  Tidak ada file VoIP yang diubah. Tidak ada migrasi Alembic lama yang diubah.
- `alembic heads` (dilaporkan Area 5) → satu head: `a5f100000001`.
  **Peringatan yang masih berlaku:** bila ada migrasi lain yang dibuat dengan `down_revision`
  yang sama di cabang lain, head harus dilinearisasi sebelum merge. Pada verifikasi gabungan
  ini tidak ada migrasi kedua, jadi tidak ada tindakan yang diambil.

Yang **tidak** diverifikasi pada putaran ini (jujur, bukan klaim):

- Tidak ada pengujian ke OLT ZTE nyata dan tidak ada Postgres nyata (tes integrasi skip seperti biasa).
- Migrasi baru hanya dicek lewat `alembic upgrade --sql` dan `alembic check` terhadap DB tidak mungkin
  (koneksi Postgres ditolak di lingkungan ini). Migrasi **belum** dijalankan ke DB nyata.
- `install.sh`/`update.sh`/`uninstall.sh` hanya dicek sintaks (`bash -n`), tidak dijalankan end-to-end
  (butuh root/Postgres/instalasi nyata).
- Multi-filter Configured end-to-end belum diverifikasi terhadap DB nyata (tidak ada Postgres).

## Perbaikan yang dilakukan agen utama (di luar 5 area)

1. **Wiring visibilitas log non-OLT diaktifkan.** Area 1 sudah memperbaiki repo
   (`activity_log_repo.search` menerima `viewer_id`), tetapi service pemanggilnya belum meneruskannya,
   sehingga perbaikan itu belum aktif end-to-end. Agen utama menambahkan
   `viewer_id=user.id` di `backend/app/services/activity_log_service.py`.
   Sekarang: baris log tanpa OLT hanya terlihat oleh Superadmin atau oleh aktornya sendiri.
2. **Konflik "Move ONU" diputuskan.** Area 3 menambahkan modal Move ONU (tombol "Pindah PON",
   manager-only) karena backend sudah mendukung move lengkap dengan pre-check. Dua pemeriksaan lama
   secara eksplisit melarang `kind: "move"` di UI (keputusan pemilik lama: "Move ONU dibuang pemilik").
   Karena tugas audit secara eksplisit membalik keputusan itu, agen utama memperbarui kedua pemeriksaan
   tersebut (`backend/tests/test_onu_detail_layout.py` dan `frontend/tests/onu-detail.check.mjs`)
   menjadi menegaskan move **harus ada**, dengan komentar yang menjelaskan pembalikan keputusan ini.
   Bila pemilik ingin move tetap dibuang, yang harus diubah hanyalah keputusan ini — bukan kodenya.
3. **Konflik route Graph Data diputuskan.** Area 5 membungkus route `/settings/graph-data` dengan
   `RequireSettingsRole` (manager-only). Pemeriksaan lama `graph-data.check.mjs` mengharapkan route
   tanpa wrapper, sehingga `npm run check` gagal. Agen utama memperbarui pemeriksaan itu agar
   mengharapkan wrapper tersebut. Ini perubahan tes yang mengikuti perubahan produk, bukan perbaikan palsu.

---

# Bagian A — Kritis

## A1. Running-config bocor ke role `user` lewat `job.result` — Selesai (Area 1)

- Temuan: endpoint refresh tidak di-gate manager; `get_job`/SSE hanya memeriksa scope OLT,
  sehingga role `user` bisa membaca `running_config` dari hasil job.
- Pengerjaan: fungsi baru `redact_job(job, viewer)` di `job_service.py` menghapus
  `running_config` (job refresh) dan `output` diagnostik untuk non-manager. Diterapkan di router jobs
  (list/get/cancel) dan di stream SSE.
- File: `backend/app/services/job_service.py`, `backend/app/routers/jobs.py`.

## A2. Superadmin terakhir bisa demote diri sendiri — Selesai (Area 1)

- Temuan: PATCH `role` tidak punya proteksi Superadmin terakhir (berbeda dengan proteksi deaktivasi).
- Pengerjaan: `update_user` kini memblokir demote Superadmin terakhir, sama seperti proteksi deaktivasi.
  Tambahan: Admin yang masih memiliki OLT tidak bisa di-demote ke `user`.
- File: `backend/app/services/user_service.py`.

## A3. Job `replace_onu` gagal mengunci serial baru — Selesai (Area 2)

- Temuan: bila authorize gagal, serial baru sudah ter-commit dan baris terkunci: authorize ulang
  diblokir `exists_serial` miliknya sendiri, hapus diblokir `config_state`.
- Pengerjaan: `replace_onu` hanya memakai serial baru sementara selama authorize; bila gagal,
  serial lama dikembalikan **dan di-commit** (penting, karena `_record` authorize yang gagal sudah
  commit serial baru + `failed`). Hasil akhir gagal = baris berserial lama + `config_state=failed`,
  sehingga bisa di-resync, di-replace ulang, atau dihapus tanpa DB manual.
  `onu_repo.exists_serial(..., exclude_id=...)` ditambahkan dan `_serial_taken` mendelegasikannya;
  dipakai juga oleh `authorize_onu` dan validasi replace.
- File: `backend/app/services/onu_service.py`, `backend/app/repositories/onu_repo.py`.

## A4. Guard hapus VLAN membandingkan kolom yang salah — Selesai (Area 4)

- Temuan: guard membandingkan `Onu.vlan_id == vlan.vlan_id` (FK baris vs nomor VLAN 1–4094) —
  selalu lolos. Untuk VLAN global dampaknya ke semua OLT.
- Pengerjaan: `_ensure_unused` kini memeriksa `Onu.vlan_id == vlan.id` (id baris). Untuk VLAN global
  guard berlaku tanpa scope OLT; untuk VLAN OLT, scope dibatasi ke OLT itu. Hapus VLAN global
  membungkus `IntegrityError` → rollback → `ConflictError` (409), bukan 500.
- Batasan jujur: pemeriksaan ulang di sisi worker (`push_delete`) sengaja **tidak** ditambahkan
  karena `FakeDb` di `test_vlan_speed_profile.py` tidak punya method `scalar()`; menutup race
  enqueue→eksekusi butuh penambahan `scalar()` ke `FakeDb` itu dulu.
- File: `backend/app/services/vlan_service.py`.

## A5. OLT soft-delete bisa dibangkitkan job tertunda / adopsi inventory — Selesai, dua sisi (Area 2 + Area 5)

- Temuan: job tertunda untuk OLT yang sudah dihapus tetap jalan; `_adopt_inventory` bisa me-INSERT ulang.
- Pengerjaan Area 2: `run_job` menolak job OLT deleted/nonaktif dengan membatalkannya (bukan gagal);
  `job_repo.cancel_pending_for_olt` (baru) membatalkan semua job `pending` OLT itu, dipanggil dari
  `delete_olt` dan dari `update_olt` saat transisi aktif→nonaktif; `olt_onboarding.cancel_chain` (baru)
  menutup rantai aktif sebagai `failed` (bukan `cancelled`, karena kontrak frontend `oltSyncStages.ts`
  hanya mengenal pending/running/success/failed).
- Pengerjaan Area 5: unique OLT diubah menjadi partial unique `uq_olt_host_cliport WHERE deleted_at IS NULL`
  (lihat Bagian E no. 2), sehingga OLT pengganti dengan host/port yang sama bisa dibuat setelah soft-delete.
- File: `backend/app/services/olt_service.py`, `backend/app/services/olt_onboarding.py`,
  `backend/app/repositories/job_repo.py`, `backend/app/worker/main.py`, `backend/app/models/olt.py`,
  migrasi `a5f100000001_area5_indexes_partial_unique.py`.

## A6. ONU hilang dari perangkat tetap `online`; posisi PON dipakai ulang tidak bisa diadopsi — Selesai (Area 2)

- Temuan: ONU yang sudah tidak ada di perangkat tetap `online` selamanya; adopsi serial baru di posisi
  PON yang sama gagal diam-diam karena `ON CONFLICT DO NOTHING`.
- Pengerjaan: `sync_onu_status` menandai ONU DB yang tadinya `online` tetapi tidak ada di sampel
  perangkat menjadi `offline` (alasan `absent_from_device_sample`, optik dikosongkan, riwayat ditulis
  dulu, baris **tidak** dihapus). Hanya yang tadinya online yang ditandai; yang sudah `offline`/`los`
  mempertahankan status spesifiknya. Walk kosong tidak menandai apa pun.
  Di `_adopt_inventory`, bentrok posisi PON ditangani: bila posisi diklaim baris DB lain yang serialnya
  sudah tidak ada di inventory perangkat, baris lama ditandai `offline` + `onu_index=None` (melepas
  partial unique) sehingga INSERT serial baru bisa jalan; bila baris lama masih ada di perangkat,
  adopsi dilewati (bukan diam-diam `DO NOTHING`). Tidak ada query `db.scalar()` baru di sana
  (tes fake-DB lama hanya punya `execute()`/`add()`).
- File: `backend/app/services/sync_service.py`, `backend/app/repositories/onu_repo.py`.

## A7. Tidak ada ganti password; `must_change_password` tidak ditegakkan; token tanpa revokasi — Selesai sebagian (Area 1)

- Temuan: tidak ada flow ganti password, flag `must_change_password` tidak pernah ditegakkan,
  token 8 jam hanya berisi sub/role/exp tanpa revokasi.
- Pengerjaan:
  - Endpoint baru `POST /api/auth/change-password` (password lama wajib, password baru min 12 / maks 128,
    membersihkan `must_change_password`). Login tetap berhasil bila flag set, sehingga bukan jebakan;
    `RequireAuth` menampilkan `ChangePasswordForm` bila flag set, lalu redirect ke `/login`.
  - Revokasi token **tanpa kolom DB baru**: `create_access_token` menambahkan klaim `"ph"` = SHA-256
    dari `password_hash` saat ini; `_user_from_token` menolak token yang klaimnya tidak cocok,
    sehingga reset/ganti password mencabut token lama.
- Batasan jujur (jangan diklaim lebih dari ini):
  - Token yang dibuat **sebelum** perubahan ini (tanpa klaim `"ph"`) masih diterima sampai kedaluwarsa (8 jam),
    demi kompatibilitas. Revokasi retroaktif penuh butuh kolom versi token di model (wilayah agen model).
  - Tidak ada daftar revokasi server-side / logout server-side.
  - Ganti password **mandiri** (voluntary) belum ada halaman: menu "Ganti password" di Layout/Lainnya
    masih berlabel "Segera". Yang jalan adalah ganti password **wajib** saat flag `must_change_password` set.
- File: `backend/app/routers/auth.py`, `backend/app/core/security.py`, `backend/app/core/deps.py`,
  `backend/app/services/auth_service.py`, `frontend/src/lib/auth.tsx`.

## A8. Aksi ONU langsung tidak di-gate manager — Selesai (Area 3, backend + frontend)

- Temuan: aksi langsung `attached-vlans`, `eth-port`, `wifi-port`, `wifi-clear`, `onu-type`, `mgmt-ip`
  tidak di-gate manager (hanya delete/restore-factory/replace-sn/move yang di-gate).
- Pengerjaan: catatan Area 3 — gate manager diterapkan pada jalur aksi langsung (router/service aksi),
  dan tombol-tombol terkait di OnuDetail ditandai manager-only (mis. tombol "Pindah PON" manager-only,
  modal Primary VLAN dari putaran 2 sudah manager-only).
- Catatan verifikasi: laporan Area 3 tidak merinci nama fungsi gate satu per satu; verifikasi gabungan
  tidak menemukan regresi tes terkait, tetapi audit ulang gate per-kind disarankan sebelum rilis
  (lihat "Yang masih perlu dicek sebelum rilis" di akhir).
- File: `backend/app/services/onu_action_service.py`, `backend/app/routers/onu_actions.py`,
  `frontend/src/pages/OnuDetail.tsx`.

## A9. Mengurangi Attached VLANs tidak menghapus service-port sisa — Selesai (Area 3)

- Temuan: daftar menyusut di DB, tetapi service-port lama di perangkat tetap ada.
- Pengerjaan: `build_attached_vlans` kini menerima `previous_count` (jumlah service-port lama dari DB)
  dan mengirim `no service-port i` untuk indeks di atas jumlah VLAN baru sampai
  `max(len baru, previous_count)`, dengan urutan hapus-lalu-tulis per indeks. `run_action` meneruskan
  `previous_vlan_count = len(service_vlan_ids lama)` dan menyimpan `service_vlan_ids` hasil
  `validate_vlans` (dedup + urut), bukan `wanted` mentah. Perilaku tanpa `previous_count` tidak berubah
  (tes `[15, 100]` tetap lolos). Verifikasi manual: mengurangi 3 → 1 menghasilkan
  `no service-port 2` dan `no service-port 3`.
- Batasan jujur: indeks perangkat yang sama sekali tidak tercatat di DB tetap tidak bisa dibuktikan
  terhapus — tidak ada perintah baca service-port yang terbukti di repo, dan sintaksnya tidak dikarang.
- File: `backend/app/drivers/zte_onu_actions.py`, `backend/app/services/onu_action_service.py`.

## A10. `install.sh` memutar `secret_key`; `uninstall.sh` menghapus kunci dekripsi tapi menyimpan DB — Selesai (Area 5)

- Temuan: reinstall memutar secret sehingga kredensial OLT terenkripsi lama tidak bisa dibuka;
  uninstall menghapus kunci tapi menyimpan DB; tidak ada `pg_dump` di install/update/uninstall.
- Pengerjaan:
  - `install.sh` tidak lagi memutar secret bila `config.ini` sudah ada (di-backup dengan timestamp,
    secret lama dipertahankan).
  - `pg_dump` ditambahkan pra-migrasi di `update.sh` (gagal → batal sebelum perubahan apa pun;
    bila `pg_dump` tidak ada/tidak bisa dibaca, diperingatkan dan dilanjutkan) dan pra-hapus di
    `uninstall.sh` (diperingatkan dan dilanjutkan bila tidak tersedia).
  - `uninstall.sh` mem-backup `config.ini` ke `/var/backups/nexfiber` dengan peringatan eksplisit
    agar tidak dihapus bila DB dipertahankan; pesan DROP manual kini memakai nama DB/user yang diparse.
  - `update.sh` ditulis ulang: stop service → backup direktori app + config (timestamp) → pg_dump →
    rsync `--delete` → pip → alembic upgrade → build frontend → start → health check; bila health check
    gagal, kode dikembalikan dari backup dan exit 1. **DB tidak di-rollback otomatis**; path dump
    disebutkan di pesan.
  - `install.sh` kini exit 1 (bukan mencetak sukses) bila health check gagal.
  - Nama DB/user divalidasi (`^[a-zA-Z_][a-zA-Z0-9_]*$`), password DB di-escape SQL (kutip digandakan)
    dan di-URL-encode untuk config; password DB tidak lagi dicetak di ringkasan install;
    Node/npm divalidasi di awal install dan update.
- Batasan: skrip hanya dicek sintaks (`bash -n`), belum dijalankan end-to-end.
- File: `install.sh`, `update.sh`, `uninstall.sh`.

## A11. Satu handler exception (`AppError`) — banyak error input jadi 500 — Selesai (Area 1)

- Temuan: hanya `AppError` yang ditangani, sehingga error validasi/tipe/integritas lain menjadi 500.
- Pengerjaan di `main.py`: handler terpusat baru — `PydanticValidationError`/`ValueError`/`KeyError`/
  `TypeError` → 422, `IntegrityError` → 409; handler `AppError` yang sudah ada tidak diubah.
  Tambahan: route `/api/{full_path:path}` mengembalikan 404-JSON, didaftarkan setelah router API
  dan sebelum SPA catch-all (sehingga GET `/api/` yang tidak dikenal tidak lagi mengembalikan 200+HTML).
- File: `backend/app/main.py`.

---

# Bagian B — Tinggi

## B1. `config_options` membocorkan Zone/Splitter tanpa scope — Selesai (Area 3)

- Temuan: endpoint opsi konfigurasi mengembalikan semua Zone/Splitter tanpa `owner_of`.
- Pengerjaan: `config_options` kini memfilter berdasarkan scope pemilik; Area 3 juga memfilter
  `OnuType.is_active.is_(True)` di sana, selaras dengan daftar VLAN/speed profile.
  (Area 4 sempat menyerahkan temuan ini ke Area 3 karena filenya `onu_action_service.py`;
  perbaikan akhir dilakukan di Area 3.)
- File: `backend/app/services/onu_action_service.py`.

## B2. Authorize tidak memvalidasi `zone_id`/`splitter_id`/`preset_id` — Selesai (Area 2)

- Temuan: authorize menerima referensi master data tanpa validasi keberadaan/scope/kapasitas.
- Pengerjaan: `_check_authorize` kini memvalidasi `zone_id` (ada + scope pemilik), `splitter_id`
  (ada + pemilik lewat zone-nya — model `Splitter` tidak punya `owner_id`, jadi scope diturunkan dari zone;
  zone harus cocok bila keduanya diberikan; kapasitas splitter), duplikat `splitter_port` untuk baris baru,
  `preset_id` (ada + scope), `onu_type_id` (ada). `update_info` juga mendapat cek duplikat
  `splitter_port` efektif (mengecualikan ONU sendiri).
- Batasan: unique DB `(splitter_id, splitter_port)` tetap butuh migrasi model (Area 5 tidak membuatnya
  pada putaran ini) — cek aplikasi menutup kasus normal, bukan balapan persis.
- File: `backend/app/services/onu_service.py`.

## B3. Speed profile menunjuk VLAN OLT lain; update profile tanpa push — Selesai dengan keputusan produk (Area 4)

- Temuan: `_check_refs` mengizinkan `vlan_db_id` lintas OLT; `update_profile` mengubah DB tanpa
  job/push sehingga DB dan perangkat menyimpang.
- Pengerjaan:
  - `_check_refs` kini memvalidasi `vlan_db_id`: VLAN harus ada, `olt_id`-nya null (global) atau sama
    dengan `olt_id` profile, dan OLT non-global harus aktif dan dalam scope user. Berlaku di create
    dan update, termasuk saat hanya `vlan_db_id` yang di-patch (digabung dengan nilai lama).
  - Update profile yang dipakai ONU non-deleted: perubahan `name`, `speed_kbps`, `olt_id`, atau
    `vlan_db_id` **ditolak** `ConflictError` dengan pesan "buat profile baru dan terapkan, atau lepas
    dulu dari ONU". Alasan (keputusan produk, dicatat eksplisit): push ulang membuat device profile baru,
    meng-orphan profile lama, dan ONU yang sudah diterapkan tetap memakai profile lama sampai diterapkan
    satu per satu — push diam-diam justru membuat DB dan perangkat makin menyimpang.
    Perubahan `description` dan `is_active` (termasuk reaktivasi) tetap diizinkan saat dipakai.
- File: `backend/app/services/speed_profile_service.py`.

## B4. VLAN/speed profile global bisa diedit Admin mana pun; retensi graph global; purge 03:00 memengaruhi semua tenant — Sebagian (Area 4 + Area 5)

- Temuan: baris global tidak punya pemilik sehingga bisa diedit Admin mana pun; retensi graph satu
  setting global; purge 03:00 memengaruhi semua tenant.
- Pengerjaan: guard hapus VLAN global kini berlaku tanpa scope (Bagian A4) dan hapus VLAN global
  lewat API langsung (tanpa job) dengan konfirmasi yang membedakan dampak global vs OLT (Area 4,
  OltDetail). Retensi per-tenant **tidak** diubah — ini keputusan desain (setting global), bukan bug
  yang diperbaiki diam-diam; purge 03:00 tetap global.
- Status: **sebagian, dengan sengaja**. Bila retensi per-tenant diinginkan, itu perubahan produk,
  bukan perbaikan bug.

## B5. Menonaktifkan Admin tidak memeriksa anak (subtree tetap login) — Selesai (Area 1)

- Temuan: Admin dinonaktifkan, tetapi user anaknya (yang dibuat Admin itu) tetap bisa login.
- Pengerjaan: `_check_deactivable` kini juga menolak bila `count_children > 0`; `_parent_id`
  menolak parent nonaktif; reaktivasi memeriksa parent aktif.
- File: `backend/app/services/user_service.py`, `backend/app/repositories/user_repo.py`.

## B6. Admin dengan `olt_access` bisa merebut kepemilikan OLT via PATCH `owner_id` — Selesai (Area 2)

- Temuan: backend menulis ulang nilai `owner_id` apa pun menjadi id pemanggil (atau sebaliknya,
  nilai pemanggil diterima tanpa cek), sehingga Admin bisa merebut OLT.
- Pengerjaan: Area 1 mengidentifikasi temuan ini di `olt_service.py` dan menyerahkannya ke Area 2
  (pemilik file). Area 2 memperbaiki validasi kepemilikan pada update OLT: `owner_id` tidak lagi
  bisa diubah sembarangan oleh Admin non-Superadmin; perubahan kepemilikan dibatasi ke Superadmin
  (dan nilai yang tidak sah ditolak, bukan ditulis ulang diam-diam).
- Catatan kejujuran: laporan Area 2 tidak merinci temuan ini satu per satu dengan nama fungsi;
  verifikasi gabungan tidak menemukan regresi, tetapi audit ulang endpoint PATCH OLT disarankan
  sebelum rilis (lihat akhir dokumen).
- File: `backend/app/services/olt_service.py`.

## B7. Filter multi-nilai Configured dikirim berulang, backend hanya skalar — Selesai (Area 2)

- Temuan: frontend mengirim filter berulang, tetapi backend mendeklarasikan skalar (hanya `status`/
  `signal` yang list) — CSV export mewarisi masalah ini.
- Pengerjaan: backend kini menerima list untuk `olt_id`, `vlan_id`, `zone_id`, `splitter_id`,
  kedua profile, dan `onu_type` (di router + service + repo; list satu nilai lama tetap jalan karena
  FastAPI list menerima satu nilai). Export CSV memakai parameter yang sama sehingga konsisten
  dengan tabel. `Configured.tsx` **tidak** diubah — UI sudah mengirim multi-nilai (`MULTI_KEYS`);
  yang rusak adalah backend. Upaya sementara Area 5 di level router dihapus karena Area 2
  mengimplementasikannya secara native; diff akhir `onus.py` adalah pekerjaan Area 2.
- Batasan: belum diverifikasi end-to-end terhadap DB nyata (tidak ada Postgres).
- File: `backend/app/routers/onus.py`, `backend/app/services/onu_service.py`,
  `backend/app/repositories/onu_repo.py`.

## B8. Aksi langsung melewati antrean job, lock CLI per-OLT, dan gate `config_state` — Selesai sebagian (Area 3)

- Temuan: jalur perintah langsung tidak melewati antrean, lock, maupun gate.
- Pengerjaan Area 3: `run_action` kini menolak ONU `config_state == "configuring"` (authorize sedang
  berjalan, aksi bisa tertimpa/hilang). ONU `success` dan `failed` diizinkan — aksi langsung adalah
  jalur perbaikan untuk config gagal, dan memblokir `failed` akan mengunci ONU itu. `external-id`
  (hanya DB) tidak di-gate karena tidak menyentuh perangkat; gate ditempatkan setelah cabang
  JOB_KINDS/external-id dan sebelum perintah dikirim. Gate `onu_index is None` yang sudah ada tetap berlaku.
- Sisa yang **tidak** diubah: aksi langsung tetap tidak masuk antrean job dan tidak memakai lock CLI
  per-OLT — itu arsitektur jalur langsung, bukan sesuatu yang bisa diubah tanpa mengubah kontrak
  jalur tersebut. Yang diperbaiki adalah gate keamanannya, bukan mengubah jalur menjadi job.
- File: `backend/app/services/onu_action_service.py`.

## B9. Job level OLT menumpuk; payload basi menang; `set_ports` menulis DB saat enqueue — Selesai (Area 2 + Area 4)

- Temuan: job OLT bisa menumpuk; payload basi bisa menang; `set_ports` menulis `uplink_ports` ke DB
  saat enqueue, sebelum perangkat dikonfirmasi.
- Pengerjaan Area 2: `job_service.enqueue` kini menolak job kedua yang masih aktif untuk
  `set_vlan_ports`, `set_port_config`, `push_speed_profile`, `sync_speed_profiles`,
  `test_connection`, `backup_olt_config` (via `job_repo.exists_active_for_olt`, baru). Cek ini di pusat
  enqueue sehingga jalur VLAN/speed-profile tertutup tanpa mengubah file-file itu.
  (`test_connection`/`sync_speed_profiles`/`backup_olt_config` sudah tercakup index partial Area 5 —
  cek ini duplikasi yang aman, `ConflictError` yang sama, ditangani scheduler sebagai skip.)
- Pengerjaan Area 4 (pemilik `vlan_service`): `set_ports` kini hanya mengantre job (payload berisi
  `ports` + `removed_ports`); `push_ports` menulis `vlan.uplink_ports` (gabungan nilai lama + baru)
  hanya setelah driver sukses, dan commit dilakukan worker `mark_success`.
- Catatan: Area 5 sengaja **tidak** memperluas anti-pileup partial unique ke
  `create_vlan`/`delete_vlan`/`set_vlan_ports`/`set_port_config`/`push_speed_profile` (payload berbeda
  per operasi; lock CLI menserialisasikannya) — jangan diklaim cakupannya penuh.
- File: `backend/app/services/job_service.py`, `backend/app/repositories/job_repo.py`,
  `backend/app/services/vlan_service.py`, `backend/app/worker/main.py`, migrasi Area 5.

## B10. Authorize via API bisa membuat ONU "telanjang"; tipe ONU diabaikan — Selesai (Area 2)

- Temuan: VLAN/profile opsional + fallback string `line/srv_profile_id` kiriman klien melewati
  penolakan null `device_profile_id`; authorize mengabaikan `onu_type_id` yang dipilih
  (memakai `onu.onu_type or "ALL-ONT"`).
- Pengerjaan:
  - `authorize_onu` tidak lagi memakai string `line_profile_id`/`srv_profile_id` kiriman klien sebagai
    fallback — bila `device_profile_id` null, yang dikirim `None` (blok terkait di-omit driver),
    bukan nama karangan.
  - Validasi di `_check_authorize` dan `_validate_job_payload`: VLAN/profile yang diberikan harus ada,
    dalam scope OLT (global diizinkan), dan tidak `is_active=False` (cek ditulis `is False` supaya
    objek tes tanpa `is_active` — yang di DB nyata selalu True/False karena `nullable=False` —
    tidak salah ditolak).
  - `create_and_enqueue_authorize` me-resolve `onu_type_id` ke nama katalog saat ada, fallback ke
    `body.onu_type`/`pending.onu_type`; `authorize_onu` memakai `onu.onu_type or "ALL-ONT"`.
- Batasan: skema masih mengizinkan VLAN/profile kosong, dan frontend AuthorizeOnu sudah mewajibkannya
  (`min(1)`); bila produk memutuskan wajib di backend juga, itu perubahan skema, bukan yang diubah diam-diam.
- File: `backend/app/services/onu_service.py`.

## B11. Semua port PON selalu tampil "offline" — Selesai (Area 2)

- Temuan: `PonPort.oper_state` tidak pernah ditulis di mana pun.
- Pengerjaan: `zte_c320.fetch_pon_oper_states` (baru, dalam irisan yang diizinkan) membaca
  `OID_IF_OPER_STATUS` yang selama ini tidak pernah dipakai, dipetakan via ifDescr `gpon-olt_*` →
  (slot, port), 1=`up`, selain itu=`down`, best-effort (SNMP gagal → `{}` sehingga nilai lama tidak
  ditimpa `None`). `sync_service._refresh_pon_oper_states` menulisnya ke `PonPort.oper_state`
  di `sync_onu_status` dan `sync_olt_metrics`.
- Catatan desain: metode ini sengaja dipanggil lewat `getattr` karena `types.py`/`base.py`
  (interface `OltDriver`) di luar kepemilikan Area 2 — penambahan resmi ke interface butuh pemilik
  file itu; driver/fake tanpa metode ini dilewati diam-diam.
- File: `backend/app/drivers/zte_c320.py`, `backend/app/services/sync_service.py`.

## B12. Unique OLT host/port dan username tanpa predikat soft-delete — Selesai (Area 5)

- Temuan: `UniqueConstraint("host","cli_port")` dan username unik tanpa `deleted_at IS NULL`
  memblokir pemakaian ulang setelah soft-delete.
- Pengerjaan: partial unique `uq_olt_host_cliport WHERE deleted_at IS NULL` dan
  `uq_users_username_active WHERE deleted_at IS NULL` (model + migrasi; migrasi menjatuhkan constraint
  lama; upgrade gagal secara transaksional bila sudah ada duplikat aktif — didokumentasikan).
- Koreksi terhadap laporan Area 1: Area 1 sempat menulis "penggunaan ulang username belum diaktifkan —
  wilayah agen model". **Keadaan akhir: sudah diaktifkan oleh Area 5** (model + migrasi di atas).
  Laporan Area 1 itu benar pada saat ditulis, tetapi sudah disusul Area 5.
- File: `backend/app/models/olt.py`, `backend/app/models/user.py`,
  `backend/alembic/versions/a5f100000001_area5_indexes_partial_unique.py`.

## B13. Kategori log `login` menyebabkan 500; kategori `delete` tidak lengkap; log non-OLT tak terlihat — Selesai (Area 1 + agen utama)

- Temuan: repo `_category_condition` tidak punya `login` (500); kategori `delete` tidak lengkap;
  query ber-scope membuang baris `olt_id IS NULL` sehingga log non-OLT tak terlihat non-Superadmin.
- Pengerjaan Area 1: `_category_condition` menangani `login` (`action == "user.login"`, tidak lagi 500);
  kategori `delete` = `action LIKE "%.delete" OR action = "onu.restore_factory"` dengan `category_of`
  yang diselaraskan dan kondisi olt/user/service diperbarui untuk mengecualikan delete/login;
  daftar legacy `_KNOWN_ACTIONS` diperluas. Repo `search` menerima `viewer_id` opsional
  (baris non-OLT terlihat hanya bila viewer adalah aktornya).
- Pengerjaan agen utama: wiring `viewer_id=user.id` di `activity_log_service.py` sehingga perbaikan
  ini aktif end-to-end (sebelumnya belum aktif — lihat "Perbaikan agen utama" no. 1).
- File: `backend/app/repositories/activity_log_repo.py`, `backend/app/schemas/activity_log.py`,
  `backend/app/services/activity_log_service.py`.

## B14. Secret default bersama untuk JWT + Fernet; tanpa fail-fast — Selesai sebagian (Area 1)

- Temuan: default `"change-me-in-production"` dipakai bersama untuk JWT dan Fernet (SHA-256 tanpa
  salt/KDF), tanpa fail-fast.
- Pengerjaan: `app_secret_key`/`jwt_secret_key` kini dibaca terpisah dari `config.ini` dengan fallback
  ke `secret_key` lama; fail-fast `RuntimeError` bila masih default saat `NEXFIBER_CONFIG` diset
  (mode install), `UserWarning` saja di dev.
- **Tidak** diubah: derivasi Fernet tetap SHA-256 polos tanpa salt/KDF — mengubahnya akan merusak
  semua kredensial OLT yang sudah tersimpan (itu migrasi kunci, bukan perbaikan sekali jalan).
- File: `backend/app/core/config.py`.

## B15. HTTP plaintext `0.0.0.0:8088`; dokumen kontradiktif soal Caddy — Belum diputuskan (butuh keputusan pengguna)

- Temuan: aplikasi berjalan HTTP plaintext; AGENTS.md/PRD menyebut Caddy+HTTPS, DECISIONS.md menyebut
  tanpa Caddy — kontradiktif.
- Pengerjaan Area 5: installer kini memperingatkan dengan jelas (HTTP saja, tanpa TLS/Caddy/firewall,
  hanya LAN, jangan ekspos port 8088) dan tidak lagi mengklaim HTTPS. Arsitektur **tidak** diubah.
- Status: **terbuka, menunggu keputusan pengguna: pasang Caddy+TLS, atau tetap LAN-only secara sadar.**
  Dokumen ini tidak memutuskan sendiri.

---

# Bagian C — Sedang

## C1. Cancel job tanpa cek pembuat/role; job running tidak bisa dihentikan — Selesai sebagian (Area 1 + Area 2)

- Temuan: cancel tidak memeriksa pembuat/role; job yang sedang berjalan tidak bisa dihentikan.
- Pengerjaan Area 1: `cancel_job` kini menerima `viewer`: non-manager hanya boleh membatalkan job
  buatannya sendiri (`created_by`); job sistem (`created_by IS NULL`) tidak diblokir.
- Pengerjaan Area 2: `run_job` kini recheck status saat eksekusi dimulai — job `cancelled` tidak
  dieksekusi; job OLT deleted/nonaktif dibatalkan.
- Batasan jujur: **job yang sudah berjalan di tengah perintah CLI tidak bisa dihentikan** —
  tidak ada cancellation token, dan laporan ini tidak mengklaim sebaliknya. Yang bisa dihentikan
  hanyalah job yang belum mulai dieksekusi.
- File: `backend/app/services/job_service.py`, `backend/app/worker/main.py`.

## C2. Stale-release bisa me-requeue job hidup; job SNMP-only bisa double-run — Selesai (Area 2)

- Temuan: tidak ada heartbeat `locked_at`; job SNMP-only bisa berjalan ganda.
- Pengerjaan: heartbeat `_execute_with_heartbeat` menjalankan `_heartbeat_loop` yang me-refresh
  `locked_at` tiap 5 menit lewat sesi DB terpisah yang di-commit sendiri (refresh di sesi eksekusi
  tidak terlihat proses lain karena transaksinya belum commit — poin krusialnya). `STALE_AFTER`
  sengaja **tidak** diperpanjang (tetap 15 menit) supaya worker yang benar-benar mati tetap pulih cepat.
  `job_repo.refresh_lock` (baru). SNMP-only: kunci per-OLT di memori worker (`_snmp_locks`); bila
  sinkron SNMP OLT itu sedang berjalan, job dikembalikan ke antrean tanpa dihitung gagal
  (pola sama seperti CLI busy). Duplikat antar-proses untuk `sync_*`/`sample_onu_traffic` sudah dicegah
  index partial unique `uq_jobs_sync_pending_per_olt` — kunci memori ini hanya pelengkap, bukan
  satu-satunya pertahanan.
- File: `backend/app/worker/main.py`, `backend/app/repositories/job_repo.py`.

## C3. Rantai onboarding tanpa timeout/force-restart — Selesai sebagian (Area 2)

- Temuan: rantai onboarding bisa menggantung tanpa jalan keluar.
- Pengerjaan: `olt_onboarding.cancel_chain` (baru) menutup rantai aktif sebagai `failed` dengan pesan
  alasan, dipanggil dari `delete_olt` dan transisi aktif→nonaktif (lihat A5). Timeout otomatis
  per-tahap **belum** ditambahkan — yang ada adalah jalan keluar manual lewat pembatalan rantai ini.
- File: `backend/app/services/olt_onboarding.py`.

## C4. Authorize gagal/stuck tidak bisa dihapus/di-authorize ulang; kasus PON penuh — Selesai (Area 2)

- Temuan: baris authorize gagal/stuck (termasuk PON penuh dengan `onu_index` None) tidak bisa
  dihapus atau di-authorize ulang; worker memilih `onu_index` tanpa cek DB.
- Pengerjaan: gate `enqueue_onu_job` dan `enqueue_bulk` diubah — `resync_onu` boleh untuk
  `success`/`failed`, termasuk `onu_index=None` (kasus PON penuh — worker `authorize_onu` akan memilih
  index baru); `delete_onu` boleh untuk `success`/`failed`/`configuring`, kecuali `configuring`
  saat job authorize masih aktif (dicek `exists_active_for_onu`, supaya tidak balapan).
  `delete_onu` worker dengan `onu_index=None` (baris buntu PON penuh) hanya soft-delete baris DB
  tanpa perintah perangkat. `_load` kini melempar `NotFoundError` jelas bila `PonPort` baris ONU hilang,
  bukan `AttributeError` yang di-retry.
  `authorize_onu` menggabungkan index perangkat (`list_onu_ids`) dengan index yang sudah diklaim DB
  untuk PON itu, lalu `pick_free_onu_index`; sebelum perintah dikirim ada cek bentrok
  `exists_index(..., exclude_id=onu.id)`.
- File: `backend/app/services/onu_service.py`, `backend/app/repositories/onu_repo.py`,
  `backend/app/worker/main.py`.

## C5. Bulk resync menolak ONU `failed`, padahal resync satuan mengizinkan — Selesai (Area 2)

- Pengerjaan: gate `enqueue_bulk` disamakan dengan satuan (lihat C4).
- File: `backend/app/services/onu_service.py`.

## C6. `set_onu_vlan` vs `attached-vlans` tidak saling memperbarui — Selesai sebagian (Area 2 + Area 3)

- Pengerjaan Area 2 (satu arah): worker `set_onu_vlan` — bila `service_vlan_ids` sudah tersinkron
  (bukan `None`), VLAN primer lama diganti yang baru di daftar itu, supaya kolom VLAN dan daftar
  attached tidak menampilkan VLAN berbeda sampai sync berikutnya. Bila daftar belum pernah tersinkron
  (`None`), tidak dikarang.
- Arah sebaliknya (attached-vlans menghapus VLAN primer → `vlan_id`) ada di `onu_action_service.py`
  (Area 3) — laporan Area 3 tidak mengklaim perbaikan arah ini secara eksplisit, sehingga status
  arah sebaliknya adalah **belum terkonfirmasi selesai**; jangan diklaim selesai.
- File: `backend/app/services/onu_service.py`, `backend/app/worker/main.py`.

## C7. Splitter dengan `zone_id=NULL` tak terlihat (inner join ke Zone) — Selesai sebagian (Area 4)

- Temuan: splitter tanpa zone hilang dari daftar karena inner join.
- Pengerjaan: repo kini outer join ke Zone, sehingga Superadmin bisa melihat dan memperbaiki splitter
  tanpa zone. Untuk Admin, kepemilikan diwariskan lewat zone sehingga splitter tanpa zone tidak punya
  pemilik — mengubah itu berarti mengubah semantik kepemilikan, jadi tidak diubah diam-diam.
  PATCH splitter yang mengosongkan `zone_id` kini ditolak (zone menentukan pemilik; mengosongkannya
  akan meng-yatimkan splitter).
- File: `backend/app/repositories/master_data_repo.py`, `backend/app/services/master_data_service.py`.

## C8. Guard hapus preset/onu-type/splitter tidak lengkap → FK 500 — Selesai (Area 4)

- Pengerjaan: `delete_preset` memeriksa `Onu.preset_id`; `delete_onu_type` memeriksa
  `OnuPreset.onu_type_id`; `delete_splitter` memeriksa `OnuPreset.splitter_id` (di samping guard ONU
  dan splitter turunan yang sudah ada). Semua jalur hapus zone/tipe/splitter/preset kini juga
  membungkus `IntegrityError` → 409 dengan rollback.
- File: `backend/app/services/master_data_service.py`.

## C9. Update splitter parsial merusak konsistensi OLT–PON dan scope — Selesai (Area 4)

- Pengerjaan: `_check_refs` ditulis ulang untuk memvalidasi keadaan **akhir** (nilai lama + patch):
  PATCH `pon_port_id` milik OLT B pada splitter OLT A, atau PATCH `olt_id` pada splitter dengan PON
  OLT A, kini ditolak. Pengecualian yang disengaja: pada update, invariant induk/OLT–PON hanya
  ditegakkan bila field terkait ikut di-patch, supaya baris legacy yang belum memenuhi invariant
  tetap bisa diedit field lainnya.
- Tambahan: OLT kini dicek lewat `olt_repo.get_active` (memfilter `deleted_at`) dengan
  `scope_olt_ids(user)`; OLT pemilik PON port juga dicek scope + aktif. OLT/PON milik tenant lain
  atau sudah dihapus kini 404, bukan lolos.
- File: `backend/app/services/master_data_service.py`.

## C10. VLAN management / VLAN eth+wifi tidak dicek terhadap master di backend — Selesai (Area 3)

- Pengerjaan: `run_action` untuk `eth-port`/`wifi-port` kini memuat `list_vlans` ter-scope untuk OLT itu
  dan menolak `vlan_id` maupun tiap `allowed_vlans` yang tidak ada di master atau bertipe `management`
  (422, bukan diam-diam lolos). Frontend mengirim `vlan_id` sebagai nomor VLAN, jadi validasi memakai
  nomor, bukan id baris.
- Pengecualian yang disengaja: nomor management yang **sudah ada** di `service_vlan_ids` boleh
  dipertahankan di attached-vlans — menolaknya akan membuat modal tidak bisa disimpan sama sekali
  untuk ONU yang punya VLAN management, dan akan menghapus service-port management itu diam-diam
  saat submit (modal memang sengaja mempertahankannya). Nomor management yang **belum terpasang**
  kini ditolak.
- File: `backend/app/services/onu_action_service.py`.

## C11. Sukses mgmt-ip tidak ditulis balik ke DB — Selesai (Area 3)

- Pengerjaan: saat `result.success` dan kind `mgmt-ip`, service kini menulis `onu.mgmt_ip_mode`
  dan `onu.ip_address`: `manual` → `static` + IP yang dikirim; `release` → `inactive` + IP dikosongkan;
  `pool` → `dhcp` dengan IP lama dipertahankan sampai sync berikutnya (IP hasil auto-assign belum
  diketahui saat perintah sukses; pemetaan `pool → dhcp` adalah asumsi yang masih perlu verifikasi
  perangkat, karena mode perangkat yang dikenal adalah `static`/`dhcp`/`inactive`).
- File: `backend/app/services/onu_action_service.py`.

## C12. Default EthPortModal tidak netral — Selesai (Area 3)

- Pengerjaan: Save kini mati sampai ada perubahan dari nilai awal (dibandingkan dengan default
  `on`/`lan`/kosong/`none`), di Eth maupun WiFi. Ini mencegah klik tanpa sengaja membuka port dan
  mengubahnya ke tag/LAN.
- Keterbatasan jujur: konfigurasi perangkat saat ini tetap tidak dibaca (by design, tidak ada endpoint
  baca config port), jadi "tidak ada perubahan" di sini berarti tidak ada perubahan dari default modal,
  bukan dari config perangkat yang sebenarnya.
- File: `frontend/src/components/onu/modals/EthPortModal.tsx`,
  `frontend/src/components/onu/modals/WifiPortModal.tsx`.

## C13. WiFi Clear tanpa konfirmasi dan tidak mati saat busy — Selesai (Area 3)

- Pengerjaan: tombol Clear kini konfirmasi dua klik ("Klik lagi untuk menghapus") dan `disabled`
  saat `busy` (aksi lain berjalan) maupun saat `clearSupported === false`. Tidak ada modal baru.
- File: `frontend/src/components/onu/modals/WifiPortModal.tsx` (dan pemanggilnya di OnuDetail).

## C14. State OnuDetail tidak di-reset saat param route berubah tanpa unmount — Selesai (Area 3)

- Pengerjaan: effect baru pada `[routeKey]` di `OnuDetail` me-reset `liveIp`, `liveWanIp`, `note`,
  seluruh state diagnostik, `live`, `modal`, dan `vlanPrimerOpen`. `useLiveTraffic` juga mengosongkan
  titik/`last`/`error` saat serial berubah, dan `PppoePassword` diberi `key={serial_number}` agar
  state "shown" tidak terbawa ke ONU lain.
- File: `frontend/src/pages/OnuDetail.tsx`.

## C15. Live traffic: baseline basi dan tick tumpang tindih — Selesai (Area 3)

- Pengerjaan: `tick` kini membuang baseline (`prev = null`) saat tab tersembunyi dan saat fetch gagal,
  sehingga titik pertama setelah kembali menjadi baseline baru, bukan dibandingkan dengan sampel lama.
  `deltaMbps` di `traffic.ts` kini menolak delta > 60 detik (`MAX_LIVE_DELTA_S = 60`, konsisten
  dengan interval live 5 detik dan batas wrap Counter32). `useLiveTraffic` kini punya penjaga in-flight
  (`inFlight` ref): tick berikutnya dilewati bila tick sebelumnya belum selesai, sehingga bulkwalk
  9–12 detik tidak menumpuk pada interval 5 detik dan tidak memicu 429 dari tab yang sama.
- File: `frontend/src/pages/OnuDetail.tsx`, `frontend/src/lib/traffic.ts`.

## C16. Grafik Rx menjembatani null (LOS); titik tunggal di tengah; label sumbu/ambang tidak akurat — Selesai (Area 3)

- Pengerjaan: `RxChart` kini membangun segmen per rentetan titik non-null untuk tiap seri; null memutus
  garis seperti grafik trafik, dan titik terisolasi digambar sebagai lingkaran. Titik tunggal seri kini
  memakai `cx` dari posisi waktu/indeks sampelnya, bukan `cx="50"` hardcode. `aria-label` kini memakai
  `dataMin` (bukan `min` sumbu yang sudah diberi padding). Garis ambang kini `[-25, -27, -28]`
  (critical −28 dari `core/signal.py` ditambahkan; domain tetap memuat −27,25/−24,75 sesuai pemeriksaan).
  `axisTick` untuk nilai < 1 Mbps kini 2 desimal yang dipangkas nol akhirnya (0,05 Mbps tidak lagi
  tampil "0.0").
- File: `frontend/src/pages/OnuDetail.tsx` (komponen RxChart di dalamnya).

## C17. Histori sinyal mencampur dua sumber — Selesai sebagian (Area 3, frontend)

- Pengerjaan: `RxChart` kini memakai sumbu waktu nyata dari `sampled_at` (bukan indeks seragam),
  sehingga jarak antar titik proporsional waktu meskipun baris perubahan status (Rx lama) bercampur
  baris optik 15 menit (Rx segar).
- Batasan: statistik tetap dihitung dari semua baris karena backend tidak menandai sumber tiap baris.
  Perbaikan penuh backend (`signal_history`/`sync_service`) berada di luar kepemilikan Area 3 dan
  tidak dilakukan.
- File: `frontend/src/pages/OnuDetail.tsx`.

## C18. Grafik histori trafik membuang titik terisolasi + menyambung melintasi celah waktu — Selesai (Area 3)

- Pengerjaan: `TrafficHistoryChart` kini memakai sumbu waktu nyata, memutus segmen bila selisih
  `sampled_at` antar titik > 15 menit (3× interval sampler 5 menit), dan menggambar titik terisolasi
  sebagai lingkaran (bukan dibuang). Titik null tetap tidak digambar sebagai nol.
- File: `frontend/src/pages/OnuDetail.tsx`.

## C19. Hapus port di PortsDrawer tidak menghapus VLAN di perangkat — Sebagian (Area 4, sisi service/payload)

- Pengerjaan: `set_vlan_ports` kini menghitung `removed_ports` (port tersimpan yang dihilangkan)
  dan mengirimnya dalam payload job sebagai kontrak untuk implementasi driver. `push_ports` sengaja
  **tidak** menghapus port dari DB: driver `zte_c320.set_vlan_ports` hanya mengiterasi port yang
  dikirim dan tidak punya perintah hapus, jadi menghapus dari DB akan memalsukan keadaan perangkat.
  Port yang dihapus dilaporkan di hasil job sebagai `removed_not_applied` dan diperingatkan di UI
  PortsDrawer.
- Status: **jangan diklaim perangkat sudah benar** — perintah hapus di driver adalah pekerjaan
  pemilik driver (di luar Area 4).
- File: `backend/app/services/vlan_service.py`, `frontend/src/pages/OltDetail.tsx`.

## C20. Tab VLAN satu OLT tanpa penanda scope; dialog hapus tidak menutup; baris hilang sebelum job selesai — Selesai (Area 4)

- Pengerjaan: tabel VLAN di `OltDetail.tsx` kini punya kolom "Cakupan" (Global/OLT), tombol Port
  dinonaktifkan untuk VLAN global (dengan keterangan), dan teks konfirmasi hapus dibedakan:
  VLAN global dihapus langsung tanpa job dan berdampak ke semua OLT; VLAN OLT lewat job.
  Hapus global: dialog langsung ditutup dan tabel di-refresh (tidak ada job). Hapus VLAN OLT:
  tabel **tidak** di-invalidate saat antrean dibuat; `useJob` memantau job dan tabel di-refresh +
  dialog ditutup hanya saat job mencapai status terminal (sukses). `JobTrace` tetap tampil selama
  job berjalan.
- File: `frontend/src/pages/OltDetail.tsx`.

## C21. Port uplink yang hilang dari daftar sinkron tidak bisa dilihat/diubah — Selesai (Area 4)

- Pengerjaan: PortsDrawer kini merender gabungan port sinkron + kunci `vlan.uplink_ports` yang
  tersimpan; port yang hanya tersimpan dilabeli "(tersimpan)".
- File: `frontend/src/pages/OltDetail.tsx`.

## C22. Nilai port live null dipaksa disable/1000/full — Selesai (Area 4)

- Pengerjaan: di PortConfigDrawer, `auto_nego`/`speed`/`duplex` null kini menjadi opsi
  "Tidak diketahui" (disabled), dan Simpan diblokir (dengan pesan error) sampai operator memilih
  nilai sebenarnya — tidak ada payload `disable` yang terkirim tanpa dipilih operator.
- File: `frontend/src/pages/OltDetail.tsx`.

## C23. Dropdown induk splitter tanpa filter tipe/zona — Selesai, sebagai invariant produk (Area 4)

- Pengerjaan: frontend memfilter induk ke `type == "odc"` dan zone yang sedang dipilih
  (watched `zone_id`), plus opsi fallback untuk induk lama supaya baris legacy tetap bisa disimpan.
  Backend menegakkan invariant yang sama (induk harus ODC dan satu zone). Ini dinyatakan sebagai
  invariant produk yang ditegakkan, bukan sekadar filter UI.
- File: `frontend/src/pages/settings/Splitters.tsx`, `backend/app/services/master_data_service.py`.

## C24. Celah log aktivitas (hapus VLAN, push/sync speed profile tidak dicatat) — Selesai (Area 4)

- Pengerjaan: hapus VLAN OLT kini mencatat `vlan.delete_requested` dengan `job_id` di sisi API
  (sebelumnya hanya log worker `vlan.push_delete`). `enqueue_push` mencatat
  `speed_profile.push_requested`, `enqueue_sync` mencatat `speed_profile.sync_requested`, dan
  `sync_from_olt` mencatat `speed_profile.sync` dengan `found`/`added` (sebelumnya sync tidak
  mencatat apa pun meski menambah baris).
- File: `backend/app/services/vlan_service.py`, `backend/app/services/speed_profile_service.py`.

## C25. Validasi hilang di UI (VLAN, OLT create, user password, host, port) — Selesai (Area 4 + Area 5)

- Pengerjaan Area 4: `vlanSchema` di OltDetail — `vlan_id` 1–4094, `gemport` kosong atau ≥ 1,
  `user_vlan` kosong atau 1–4094. OltManagement: host ditolak bila ada oktet > 255 (regex saja
  meloloskan "999.1.1.1"), port CLI/SNMP 1–65535, PON 1–128, dan secret wajib (min 1) saat create saja —
  saat edit kosong berarti kredensial lama dipertahankan (dicek di handler submit karena Zod tidak
  tahu mode edit).
- Pengerjaan Area 5: tipe `Job` di `lib/api.ts` diperluas (priority, payload, created_by, attempts,
  max_attempts, duration_ms), tipe `User` ditambahkan sesuai `UserOut`.
- File: `frontend/src/pages/OltDetail.tsx`, `frontend/src/pages/settings/OltManagement.tsx`,
  `frontend/src/lib/api.ts`.

## C26. Duplikasi master data + IntegrityError jadi 500 — Selesai sebagian (Area 4 + Area 5)

- Pengerjaan Area 4: `_save` dan semua jalur hapus master data kini memetakan `IntegrityError` → 409
  dengan rollback. Cek duplikasi aplikasi tetap ada sebagai pertahanan pertama.
- Pengerjaan Area 5: unique constraint DB untuk master data — speed_profile
  `(olt_id, direction, device_profile_id)`, preset `(owner_id, name)`, onu_type `(name)`,
  splitter `(olt_id, code)`, zone case-insensitive `(owner_id, lower(name))` — ditambahkan di model
  + migrasi baru.
- File: `backend/app/services/master_data_service.py`, `backend/app/models/speed_profile.py`,
  `backend/app/models/onu_preset.py`, `backend/app/models/onu_type.py`,
  `backend/app/models/splitter.py`, `backend/app/models/zone.py`, migrasi Area 5.

## C27. Duplikasi zone lewat whitespace — Selesai (Area 4)

- Pengerjaan: nama zone dinormalisasi (`_clean_zone_name`: `_` dianggap spasi, spasi dirapatkan)
  saat cek dan simpan, dan `zone_name_taken` di repo kini membandingkan dengan normalisasi yang sama
  (`regexp_replace`, konsisten dengan `get_or_create_zone`). Nama tipe ONU, splitter, dan preset
  minimal di-strip.
- File: `backend/app/services/master_data_service.py`, `backend/app/repositories/master_data_repo.py`.

## C28. Update VLAN description/gemport/tag_action/user_vlan tidak sampai ke perangkat — Dokumentasi jujur, driver belum (Area 4)

- Temuan: `push_ports` hanya mengirim perintah switchport; tidak ada jalur driver yang mengirim ulang
  field-field itu untuk VLAN yang sudah ada (hanya `description` dikirim sekali saat `push_create`).
- Pengerjaan: docstring `update_vlan` dikoreksi dan VlanDrawer menampilkan catatan saat edit bahwa
  perubahan field tersebut hanya tersimpan di DB sampai VLAN dihapus dan dibuat ulang.
  **Tidak diklaim terkirim.** Bila driver nanti mendukung kirim ulang field itu, itu pekerjaan
  pemilik driver.
- File: `backend/app/services/vlan_service.py`, `frontend/src/pages/OltDetail.tsx`.

## C29. Menurunkan ratio splitter di bawah jumlah ONU — Selesai, sebagai batas keras (Area 4)

- Pengerjaan: update ratio kini ditolak 409 bila kapasitas baru < jumlah ONU non-deleted yang menempel,
  dengan pesan yang menyebut angka keduanya. Kapasitas diperlakukan sebagai batas keras.
- File: `backend/app/services/master_data_service.py`.

## C30. Histori graph OLT terhapus tidak bisa dibersihkan manual — Selesai (Area 4)

- Pengerjaan: `_onu_ids` di `graph_data_service` kini mengizinkan Superadmin (scope `None`) menyentuh
  OLT yang sudah dihapus bila `olt_id` diberikan eksplisit; non-Superadmin tetap dibatasi scope + OLT
  aktif. Di UI GraphData, Superadmin mendapat input "ID OLT terhapus" yang mengalahkan dropdown
  (dropdown tidak pernah menampilkan OLT terhapus). Dikonfirmasi lewat jalur hapus manual yang sama,
  bukan jalur baru.
- File: `backend/app/services/graph_data_service.py`, `frontend/src/pages/settings/GraphData.tsx`.

## C31. `size_bytes` adalah ukuran seluruh tabel — Label diperjujur, perilaku tidak diubah (Area 4)

- Pengerjaan: perilaku backend tidak diubah (sudah didokumentasikan di kode). Label UI diubah dari
  "Ukuran tabel" menjadi "Ukuran tabel (semua OLT)".
- File: `frontend/src/pages/settings/GraphData.tsx`.

## C32. Drawer/state basi + konfirmasi hapus tidak lengkap — Selesai (Area 4)

- Pengerjaan: PortsDrawer dan PortConfigDrawer kini me-refresh query saat job DONE, bukan saat enqueue
  (lihat C20). Teks konfirmasi dilengkapi: splitter menyebut preset dan splitter turunan; zone menyebut
  preset; tipe ONU menyebut preset.
- File: `frontend/src/pages/OltDetail.tsx`, `frontend/src/pages/settings/Splitters.tsx`,
  `frontend/src/pages/settings/OnuTypes.tsx`.

## C33. Tombol "Simpan ke OLT" Speed Profile tanpa JobTrace — Selesai (Area 4)

- Pengerjaan: push kini menyimpan `job_id` dan menampilkan `JobTrace` (pola yang sama dengan
  VLAN/Interfaces), di samping catatan "Job #… dibuat".
- File: `frontend/src/pages/settings/SpeedProfile.tsx`.

## C34. GraphData setelah hapus — Selesai (Area 4)

- Pengerjaan: setelah hapus sukses, pratinjau dikosongkan (tombol Hapus hilang) dan tampil angka hasil
  sebenarnya ("N baris dihapus."), bukan pratinjau lama. Pratinjau vs hasil hapus untuk `date_to` hari
  berjalan sudah diperiksa dan **tidak ada bug lain** — pratinjau dan hapus memakai payload yang sama.
- File: `frontend/src/pages/settings/GraphData.tsx`.

## C35. Info OLT tidak bisa diubah dari Settings (`max_onu_per_port`) — Selesai (Area 4)

- Pengerjaan: backend sudah mendukung di `OltCreate` dan `OltUpdate` (1–256, default 128), jadi field
  ditambahkan ke skema, default, body request, dan form OltManagement. Tidak ada field tak didukung
  yang dikirim.
- File: `frontend/src/pages/settings/OltManagement.tsx`.

## C36. Speed profile duplikat + nama tidak dibersihkan — Selesai (Area 4)

- Pengerjaan: create dan update kini membersihkan nama dengan `clean_profile_name` saat simpan dan
  menolak duplikat (nama bersih, case-insensitive, per arah dan `olt_id`, dengan `olt_id` null
  diperlakukan sebagai global) dengan 409, plus pemetaan `IntegrityError` → 409 sebagai jaring
  pengaman race.
- File: `backend/app/services/speed_profile_service.py`.

## C37. Preset menyimpan nama profile/nomor VLAN mentah — Selesai (Area 4)

- Pengerjaan: create preset kini memvalidasi `download_profile`/`upload_profile` terhadap
  `speed_profiles` (nama dibersihkan, per arah, dalam scope: global atau OLT dalam scope) dan `vlan`
  terhadap `vlans` (nomor ada di katalog master dalam scope). Catatan: preset tidak terikat satu OLT,
  jadi validasi ini adalah keberadaan di katalog master; pencocokan per-OLT tetap terjadi saat preset
  dipakai, sesuai komentar skema.
- File: `backend/app/services/master_data_service.py`.

## C38. Update speed profile ke `is_active=False` tersimpan tapi respons 404 — Selesai (Area 4)

- Pengerjaan: `list_one` tidak lagi lewat `list_profiles` (yang memfilter `is_active=True`); kini
  memakai `_get` (cek scope yang sama) + helper `_row_for` yang memuat `olt_name`, VLAN, dan jumlah
  ONU secara langsung.
- File: `backend/app/services/speed_profile_service.py`.

## C39. Edit speed profile bisa men-null-kan `olt_id`/`vlan_db_id` — Selesai (Area 4)

- Pengerjaan: drawer menampilkan opsi fallback ("OLT/VLAN tidak tersedia (id …)") bila nilai lama
  tidak ada di daftar opsi, sehingga simpan tidak diam-diam men-null-kan. Selain itu drawer kini
  memuat daftar VLAN-nya sendiri berdasarkan OLT yang dipilih di drawer (watched `olt_id`),
  bukan filter halaman.
- File: `frontend/src/pages/settings/SpeedProfile.tsx`.

## C40. Speed profile nonaktif hilang dan tidak bisa diaktifkan lagi — Selesai (Area 4)

- Pengerjaan: `list_profiles` mendapat parameter `include_inactive`; endpoint list meneruskannya;
  halaman Settings memanggil dengan `include_inactive=true` sehingga profile nonaktif tampil dengan
  badge Nonaktif dan bisa diaktifkan lewat field Status di drawer (default perilaku list lain tetap
  aktif-saja, mis. dropdown otorisasi). `toPayload` mengirim `is_active` saat edit (tidak saat create,
  karena `SpeedProfileCreate` tidak punya field itu).
- File: `backend/app/services/speed_profile_service.py`, `backend/app/routers/speed_profiles.py`,
  `frontend/src/pages/settings/SpeedProfile.tsx`.

## C41. Dashboard "ONU Offline" ≠ link-nya; "Total OLT" menyesatkan — Selesai (Area 5)

- Pengerjaan: kartu diganti nama menjadi "ONU Tidak Online" dengan link yang mencakup **semua**
  status non-online (`offline, los, dying_gasp, power_off, unknown`); "Total OLT" diganti label
  "OLT Aktif" (backend memang menghitung yang aktif saja).
- File: `frontend/src/pages/Dashboard.tsx`.

## C42. `/settings/olts` dan route settings lain tidak di-gate role di UI — Selesai (Area 5)

- Pengerjaan: `RequireSettingsRole` baru di `main.tsx` meng-gate `/settings/olts`, `/settings/users`,
  `/settings/onu-types`, `/settings/graph-data` ke role manager dengan halaman penjelasan
  (bukan redirect diam-diam); route splitters/speed-profiles tetap tidak di-gate sesuai menu.
- File: `frontend/src/main.tsx`.

## C43. `/settings/*` wildcard menelan typo menjadi Placeholder, bukan 404 — Selesai (Area 5)

- Pengerjaan: `/settings/*` dihapus dari placeholder `LATER` (hanya `/settings/vpn` dan `/settings/tr069`
  yang tersisa sebagai placeholder "segera" yang jujur); path settings lain yang tidak dikenal →
  `NotFound`.
- File: `frontend/src/main.tsx`.

## C44. Job polling tidak berhenti saat query error — Selesai (Area 5)

- Pengerjaan: `useJob` kini `retry: false`, polling berhenti saat error dan saat DONE.
  `useJobStream` di `jobs.ts` mengembalikan `{ disconnected }`, menutup koneksi saat token hilang,
  dan tidak reconnect dengan token basi.
- File: `frontend/src/lib/jobs.ts`.

## C45. Refresh-metrics OLT membuang `job_id` dan menelan error; daftar ONU OltDetail terpotong 200 — Diserahkan, belum selesai

- Temuan: refresh-metrics tidak melacak job-nya; daftar ONU OltDetail diam-diam terpotong 200 baris.
- Status: **belum dikerjakan pada putaran ini.** Area 2 menyerahkan keduanya ke Area 4 (pemilik
  `OltDetail.tsx`); laporan akhir Area 4 tidak mengklaim perbaikan untuk kedua temuan ini.
  Jangan diklaim selesai.
- File yang perlu disentuh: `frontend/src/pages/OltDetail.tsx`.

## C46. Validasi frontend lebih longgar dari backend (OLT create, password, host, port) — Selesai (Area 4, lihat C25)

## C47. Preset tanpa endpoint update; speed profile nonaktif (lihat C40); status OLT tiga penulis — Sebagian (Area 2)

- Preset **tidak** mendapat endpoint update pada putaran ini (tidak ada di laporan area mana pun) —
  status: **belum**.
- Status OLT tiga penulis: `worker._fail` kini hanya menandai `unreachable` untuk error konektivitas
  sungguhan (`TimeoutError`/`ConnectionError`/`OSError`/`DriverError` non-permanen) dari job
  NON-diagnostik; satu diagnostik gagal/timeout, perintah ditolak, atau validasi gagal tidak lagi
  membuat OLT sehat jadi `unreachable`. `sync_onu_status` dengan walk kosong dan `sync_onu_optical`
  dengan walk optik kosong tidak lagi menandai OLT `online`.
  Batasan yang tersisa dan didokumentasikan di kode: sukses SNMP saja tetap menandai `online` —
  artinya "terjangkau lewat SNMP", bukan "CLI sehat"; kesehatan CLI hanya dibuktikan job
  `test_connection`/aksi CLI. Penulis keempat, `onu_traffic_history_service.py` (menulis `olt.status`
  langsung), ada di luar daftar file Area 2 — perlu dilihat pemiliknya, tidak diubah.
- File: `backend/app/worker/main.py`, `backend/app/services/sync_service.py`.

## C48. `sync_olt_metrics` menimpa data baik dengan `None`; all-or-nothing; balapan sync 1 menit vs 15 menit — Selesai sebagian (Area 2)

- Pengerjaan: semua field health kini hanya ditulis bila ada nilainya (`cpu_pct`, `ram_pct`,
  `temperature_c`, `uptime_seconds`, `software_version`, `sys_name`, `sys_location`, `cards` bila
  non-kosong, `uplink_ports` bila non-kosong). Sisi driver sudah best-effort (SNMP gagal → `None`);
  sisi sync kini tidak mem-forward `None` itu ke DB.
- CPU kartu kontrol: **tidak diubah** — tidak ada transkrip `show card` terverifikasi di repo yang
  membedakan kartu kontrol dari kartu layanan, jadi menebak tipe (SCXN/dll) bisa menampilkan CPU
  kartu yang salah; "kartu pertama ber-CPU" dipertahankan dan dicatat di komentar kode.
- Balapan 1 menit vs 15 menit: kunci SNMP per-OLT (lihat C2) mengurangi risiko double-run; balapan
  tulis antar kedua sync tidak sepenuhnya dihilangkan.
- File: `backend/app/services/sync_service.py`.

## C49. `sync_unconfigured` menghapus semua pending bila scan kosong — Selesai (Area 2)

- Pengerjaan: bila scan kosong **dan** daftar PON perangkat juga kosong (tidak ada bukti perangkat
  benar-benar terbaca), penghapusan dilewati dan OLT tidak ditandai online
  (`wipe_skipped_empty_untrusted`). Scan kosong yang valid (PON terbaca, memang tidak ada ONU
  unconfigured) tetap menghapus seperti dulu. Tambahan: anti-join — pending yang serialnya sudah
  terdaftar dihapus walau masih terlihat di scan. Pemanggilan `list_pon_ports` kedua dihilangkan
  (hasilnya dipakai ulang).
- File: `backend/app/services/sync_service.py`.

## C50. Perubahan perangkat tidak tercermin untuk kolom yang hanya ditulis bila ada nilai — Sengaja tidak ditutup penuh (Area 2)

- Temuan: IP mgmt/IP WAN/VLAN WAN tidak dikosongkan saat perangkat tidak lagi menampilkannya.
- Pengerjaan: Area 2 sempat mengimplementasikan pengosongan, lalu **mengembalikannya total** karena
  tes yang ada membuktikan itu salah: tes mengunci keputusan "tanpa kandidat: kolom tidak disentuh,
  tidak dikosongkan" (mis. `test_adopt_inventory_no_management_ip_never_clears_ip`), dan alasannya
  kuat — snapshot perangkat tidak cukup setia untuk membuktikan penghapusan
  (`parse_management_ip` mengembalikan `None` untuk seluruh stanza bila satu baris ambigu; kolom-kolom
  ini juga menampung isian operator). Pengosongan yang benar-benar aman butuh penanda per-field di
  level snapshot/driver (mis. "stanza perangkat terbaca penuh + field ini memang tidak ada") dan,
  untuk PPPoE, kolom sumber — karena `pppoe_username` bisa diisi operator lewat API tanpa penanda
  sumber, "stanza tidak ada" tidak bisa dibedakan dari "rencana operator yang belum di-push".
- Status: **temuan yang sengaja tidak ditutup penuh, bukan terlewat.** Komentar penjelas ditambahkan
  di `_adopt_inventory`.
- File: `backend/app/services/sync_service.py`.

## C51. Logs page: `page` tidak disanitasi; halaman di luar total — Selesai (Area 5, sisi frontend)

- Pengerjaan: halaman Logs menyaring `page` (NaN/<1/non-integer → 1) dan meng-clamp halaman
  di luar total kembali ke halaman terakhir.
- File: `frontend/src/pages/Logs.tsx`.

## C52. Navigasi: judul "Detail ONU" hilang; tombol back mobile tanpa fallback; pencarian header palsu — Selesai sebagian (Area 5)

- Pengerjaan: `nav.ts` mengembalikan "Detail ONU" untuk `/onu/…`; tombol back mobile di Layout
  fallback ke `/` bila history kosong. Header search jujur dinonaktifkan ("Cari (segera hadir)"),
  tombol search mobile dinonaktifkan; item menu "Ganti password" di Layout/Lainnya diberi label
  non-aktif "Segera" — **catatan:** label ini kini perlu dibaca bersama Bagian A7: ganti password
  wajib (saat flag set) sudah jalan, yang belum ada adalah halaman ganti password mandiri.
- Belum: validasi `next` di Login (`Login.tsx` masih `next?.startsWith("/")`, yang masih meloloskan
  `//evil.com` sebagai redirect protokol-relatif). Status: **masih terbuka** (kecil, tapi nyata).
- File: `frontend/src/lib/nav.ts`, `frontend/src/components/Layout.tsx`,
  `frontend/src/pages/Lainnya.tsx`, `frontend/src/pages/Login.tsx` (belum).

## C53. OLT refresh-metrics, OltDetail, dan job tracking — lihat C45 (belum)

## C54. Hapus/nonaktifkan OLT tidak menghentikan job/rantai — Selesai (Area 2, lihat A5)

## C55. Retry perintah destruktif tanpa idempotensi — Selesai sebagian (Area 2)

- Pengerjaan: authorize — penolakan `already exist` diperlakukan sukses **hanya** bila index itu
  memang ada di perangkat (`list_onu_ids`) dan tidak ada baris DB lain di posisi itu (cek bentrok
  sudah dilakukan). Delete — jawaban perangkat "sudah tidak ada"
  (`there is no`/`no related information`/`does not exist`/`not exist`/`not found`) diperlakukan
  sukses karena tujuan akhirnya tercapai.
- **Restore-factory tidak dibuat idempoten**: tidak ada penanda perangkat yang membedakan
  "restore job ini sudah jalan" dari "restore manual di antaranya", sehingga retry buta bisa
  menghapus hasil resync manual — batasan ini didokumentasikan di kode, bukan diperbaiki diam-diam.
- File: `backend/app/worker/main.py`, `backend/app/services/onu_service.py`.

## C56. Unconfigured menampilkan ONU yang sudah terdaftar — Selesai (Area 2)

- Pengerjaan: anti-join ke `onus` di `onu_repo.list_pending` dan penghapusan pending terdaftar di
  `sync_unconfigured` (lihat C49).
- File: `backend/app/repositories/onu_repo.py`, `backend/app/services/sync_service.py`.

## C57. `customer_id` tanpa unique/normalisasi — Selesai sebagian (Area 2)

- Pengerjaan: `normalize_customer_id` = strip saja, dipakai di cek dan simpan authorize +
  `update_info`. Sengaja **tidak** di-lowercase supaya ID pelanggan yang ditampilkan tidak berubah bentuk.
- Unique DB diserahkan ke Area 5 dan **tidak** dibuat pada putaran ini — normalisasi menutup varian
  spasi, bukan balapan persis.
- File: `backend/app/services/onu_service.py`.

## C58. Bulk `set_state` tanpa `enabled` gagal di worker; `set_port_config` tanpa validasi pra-antre — Selesai (Area 2)

- Pengerjaan: cabang `set_state` ditambahkan di `_validate_job_payload` (harus bool asli), plus tes
  unit. `ValidationAppError` ditambahkan ke `PERMANENT_ERRORS` worker supaya validasi worker yang
  deterministik tidak di-retry.
  Validasi di enqueue `olt_service.set_port_config`: format + kombinasi speed/duplex dicek dengan
  builder perintah driver yang sama (satu sumber aturan, DRY), port harus ada di daftar uplink terakhir
  yang diketahui bila daftar itu sudah tersinkron (bila belum pernah tersinkron, keberadaan tidak
  bisa dibuktikan sehingga tidak ditolak). Gagal validasi = `ValidationAppError` sebelum antrean,
  bukan job gagal. Worker `push_port_config` memvalidasi ulang untuk job lama yang antre sebelum
  aturan ini ada.
- File: `backend/app/services/olt_service.py`, `backend/app/services/onu_service.py`,
  `backend/app/worker/main.py`.

## C59. Cek koneksi pra-simpan hanya SNMP; walk kosong dianggap sukses — Selesai sebagian (Area 2)

- Pengerjaan: walk kosong kini gagal ("SNMP tidak mengembalikan sysDescr (walk kosong)"),
  bukan sukses "SNMP menjawab".
- **Uji CLI penuh tidak diimplementasikan di endpoint ini** karena form pra-simpan tidak membawa
  kredensial CLI sama sekali (hanya host + SNMP) — menambahnya butuh field form + halaman di luar
  kepemilikan frontend Area 2; batasan ini didokumentasikan di docstring, bukan disembunyikan.
- File: `backend/app/services/olt_service.py`.

## C60. Replace-sn langsung vs job replace tidak disamakan — Selesai sebagian (Area 2)

- Pengerjaan sisi job: `replace_onu` menghapus baris `UnconfiguredOnu` serial baru setelah authorize
  sukses, dan pada gagal tidak mengklaim layanan lama tanpa penanda (baris kembali ke serial lama +
  `failed`, lihat A3). Penyamaan penuh (re-authorize penuh setelah replace-sn langsung) tidak dilakukan
  karena berisiko. Jalur replace-sn langsung ada di `onu_action_service.py` (Area 3) — tidak diedit
  Area 2; penghapusan pending row + penanda di jalur itu butuh Area 3 dan **belum terkonfirmasi**.
- File: `backend/app/services/onu_service.py`.

## C61. Move ONU: backend mendukung, UI tidak ada — Selesai, dengan pembalikan keputusan pemilik (Area 3 + agen utama)

- Pengerjaan: modal baru `MoveModal.tsx` (daftar PON tujuan dari `GET /api/olts/{olt_id}/pon-ports`,
  PON asal tidak ditawarkan, menampilkan `onu_count/capacity`, Save mati sampai PON tujuan dipilih),
  didaftarkan di `OnuActionModals` (`kind: "move"`), dan tombol "Pindah PON" (manager-only)
  ditambahkan di panel Aksi Operasional halaman Detail ONU. Backend sudah mendukung penuh termasuk pre-check.
- Konflik keputusan: dua pemeriksaan lama secara eksplisit menegaskan `kind: "move"` tidak boleh ada
  (keputusan lama "Move ONU dibuang pemilik"). Tugas Area 3 secara eksplisit membalik keputusan itu,
  sehingga pemeriksaan tersebut diperbarui oleh agen utama (lihat "Perbaikan agen utama" no. 2).
- File baru: `frontend/src/components/onu/modals/MoveModal.tsx`;
  diubah: `frontend/src/components/onu/modals/OnuActionModals.tsx`, `frontend/src/pages/OnuDetail.tsx`,
  `backend/tests/test_onu_detail_layout.py`, `frontend/tests/onu-detail.check.mjs`.

---

# Bagian D — OnuDetail / modal / trafik / sinyal / diagnostik (Area 3, per temuan 1–42)

Bagian ini merangkum temuan Area 3 yang belum tercakup di Bagian A–C. Nomor merujuk pada
daftar tugas Area 3.

1. **Attached menyusut** — lihat A9.
2. **`device_metadata` tidak pernah dikirim backend** — Selesai sisi frontend, backend diserahkan.
   Baris Alamat tidak lagi memakai `d.description` mentah: kini
   `fromMasterOrDescription(d.address, meta?.address)` — hanya alamat hasil parse bila backend
   mengirim `device_metadata`; bila master kosong dan metadata tidak ada, tampil "—" dengan jujur.
   Pengiriman `device_metadata` dari backend tetap diserahkan ke pemilik `schemas/onu.py`/`get_onu`
   dan **belum** dikerjakan.
3. **State tidak di-reset** — lihat C14.
4. **Baseline basi** — lihat C15.
5. **Tick tumpang tindih** — lihat C15.
6. **Rx menjembatani null** — lihat C16.
7. **VLAN Eth/WiFi tidak dicek master** — lihat C10.
8. **VLAN management lewat attached-vlans** — lihat C10 (pengecualian yang disengaja).
9. **Mgmt-ip tidak ditulis balik** — lihat C11.
10. **Default EthPortModal tidak netral** — lihat C12.
11. **WiFi Clear** — lihat C13.
12. **Baris Mgmt IP menyembunyikan IP bila mode null + modal memakai IP DB usang** — Selesai.
    Chip IP live kini dirender terpisah dari mode, sehingga tampil meski `mgmtMode` null
    (bukan hanya "None"). `modalOnu.ip_address` kini diisi `ipLive` (live ?? cache DB).
    Label mode dilengkapi: `MGMT_MODE_LABEL` kini memuat `inactive: "Inactive"`.
13. **Nama pelanggan/Kontak memakai sumber field yang salah** — Selesai. Baris "Nama pelanggan" kini
    hanya `d.customer_name`, "Kontak" hanya `d.contact`, tanpa fallback ke `name`/`phone` yang tidak
    bisa dihapus lewat modal Location. Bila kosong, tampil `None`/— dengan jujur.
14. **Jalur perintah langsung tidak mengecek `config_state`** — lihat B8.
15. **Field body hilang/salah tipe jadi 500** — Selesai. `_build_commands` kini memakai helper ketat:
    `port` harus int non-bool dalam rentang (eth 1–24, wifi 1–8), `mode` harus string tidak kosong,
    `enabled` harus boolean bila ada (string `"false"` yang truthy di Python kini ditolak, bukan
    diterjemahkan sebagai unlock). `run_action` kini menangkap `KeyError`/`TypeError`/`AttributeError`
    di samping `ValueError` dan mengubahnya menjadi `ValidationError` (422).
16. **Kind move tanpa modal/UI** — lihat C61.
17. **Histori sinyal dua sumber** — lihat C17.
18. **Pesan 409 diagnostik menyamakan dua penyebab** — Selesai. Frontend kini membedakan berdasarkan
    pesan backend: mengandung `"not provisioned"` → "ONU ini belum ter-provisioning (belum ada
    onu_index atau konfigurasi belum sukses).", selain itu → "Pembacaan untuk ONU ini masih berjalan,
    tunggu selesai."
19. **Identifier ONU tanpa prefix rak 1/** — Selesai. `onuIf` kini `gpon-onu_1/{slot}/{port}:{id}`,
    sesuai `onu_iface` backend.
20. **Kolom Mode tabel Ethernet selalu "LAN"** — Selesai. Kolom Mode kini "Belum dibaca" seperti
    kolom Status, di tabel desktop maupun kartu mobile.
21. **Setelah Hapus/Replace-SN halaman jadi ErrorState 404** — Selesai. `onDone` kini: kind `delete`
    → `navigate("/configured")`; kind `replace-sn` dengan `d.id` tersedia →
    `navigate(`/onu/${d.id}`)` (ID tidak berubah saat replace-sn, tidak seperti serial).
    Bila ID tidak tersedia, perilaku lama (catatan saja) dipertahankan.
22. **SSID WiFi kosong diam-diam dipertahankan + SSID berspasi lolos** — Selesai sisi kejujuran UI,
    bukan dengan klaim palsu. Fakta yang diverifikasi: backend `validate_ssid` **tidak** menolak
    spasi tunggal (tes `test_wifi_port_lengkap` memakai `"Nexfiber Test"`), jadi frontend tidak boleh
    mengklaim backend menolak spasi. Yang diperbaiki: baris SSID kini ber-hint "Kosong = SSID lama
    dipertahankan, bukan dihapus."; SSID berspasi menampilkan peringatan "SSID berspasi bisa terpotong
    di CLI OLT (perintah dipisah spasi)."; SSID dibatasi `maxLength={32}`. Tidak ada sintaks quoting
    CLI yang dikarang — perintah SSID di builder tidak diubah.
23. **Mgmt-ip manual selalu /24 tanpa validasi** — Selesai. Modal Mgmt IP kini punya field Netmask
    (default `255.255.255.0`, hanya untuk mode manual, validasi format oktet di frontend, Save mati
    bila tidak valid). Service meneruskan `body.get("netmask")` ke `build_mgmt_ip` yang sudah menerima
    parameter itu dan memvalidasikannya lewat `validate_netmask` yang sudah ada (terverifikasi manual:
    `mgmt-ip 10.0.0.5 255.255.255.128`).
24. **Grafik histori trafik** — lihat C18.
25. **Titik tunggal Rx di tengah** — lihat C16.
26. **Rate limit dicatat sebelum baca SNMP** — Selesai. `read_sample` kini menghapus entri `_last_read`
    bila salah satu `_walk_octets` gagal, sehingga kegagalan SNMP tidak menghabiskan slot dan percobaan
    ulang langsung mendapat error SNMP yang sebenarnya, bukan 429. `_check_rate_limit` sendiri
    dipertahankan mencatat (sesuai tes yang ada yang mengandalkannya).
27. **Label sumbu/ambang Rx** — lihat C16.
28. **Sampler trafik membuang ONU satu tabel tanpa jejak** — Selesai lewat log, bukan baris palsu.
    `sample_olt` kini mencatat `logger.warning` dengan jumlah dan contoh serial ONU yang hanya muncul
    di satu tabel (RX saja/TX saja), dan mengembalikan `samples_partial_table` di hasil. Baris null
    sengaja **tidak** ditulis karena akan menjadi "sampel sebelumnya" dan merusak delta berikutnya.
29. **External ID >50 jadi 500** — Selesai dua lapis. Cabang external-id di `run_action` kini menangkap
    `ValidationError` Pydantic dari `OnuInfoBody.model_validate` dan mengubahnya menjadi
    `ValidationError` aplikasi (422). Frontend `ExternalIdModal` kini `maxLength={50}` dan Save mati
    bila > 50.
30. **Validasi panjang frontend lebih longgar** — Selesai. Replace-SN kini `^[A-Z0-9]{8,20}$`
    setelah upper (input dinormalisasi ke upper saat ketik, menggantikan syarat lama `length >= 4`);
    sandi WiFi 8–63 karakter tanpa spasi dan tanpa `?` (Save mati bila tidak valid); SSID 1–32 karakter
    tanpa `"` dan `?` (lihat no. 22 untuk spasi).
31. **Modal tipe ONU menawarkan tipe nonaktif** — Selesai dua lapis. `config_options` kini memfilter
    `OnuType.is_active.is_(True)`, selaras dengan daftar VLAN/speed profile. Di frontend,
    `OnuTypeModal` kini mematikan Save bila ID terpilih tidak ada di daftar opsi (tipe nonaktif dari
    nilai awal tidak bisa dikirim ulang).
32. **Backend location tidak cek kapasitas splitter/kecocokan zone-splitter/duplikat splitter_port** —
    Diserahkan (Area 2, `onu_service.py`) — Area 3 tidak mengeditnya. Sisi frontend yang sudah ada
    dipertahankan (pilihan port sesuai kapasitas splitter terpilih, splitter disaring ke zone terpilih).
    Status akhir: Area 2 **telah** memperbaiki validasi zone/splitter/preset/kapasitas di authorize
    (lihat B2) dan duplikat `splitter_port` di `update_info`; cek kapasitas pada update location
    secara spesifik tidak diklaim selesai di laporan Area 2 — **belum terkonfirmasi**.
33. **Koordinat lokasi bisa tersimpan sebelah saja** — Selesai. `LocationModal` kini mensyaratkan
    latitude dan longitude keduanya terisi atau keduanya kosong; bila hanya satu terisi, Save mati.
34. **Pensil Sektor membuka modal tanpa field sektor** — Selesai dengan menghapus pensil. Baris "Sektor"
    tetap ada (urutan acuan utuh, nilai `None`) tetapi tanpa `onEdit`, karena pensil menyiratkan sektor
    bisa disunting padahal modal yang terbuka tidak punya field itu. Baris tidak dihapus agar
    pemeriksaan label blok Identitas tetap lolos.
35. **Empty-state WiFi salah saat katalog belum ketemu** — Selesai. Kini dibedakan seperti cabang
    Ethernet: `specs` null → "Tipe ONU belum terdaftar di ONU Types.", `specs` ada tetapi `wifi_ssids`
    0 → "Tidak ada SSID WiFi".
36. **Judul seksi Rentang hanya mencerminkan rentang trafik** — Selesai. Header seksi kini
    "Trafik {range} · Sinyal {srange}"; judul masing-masing kartu sudah memakai rentangnya sendiri.
37. **Baris Link modal Ethernet selalu "—"** — Selesai dengan menghapus baris. Tidak ada sumber status
    link di halaman ini (satu-satunya pemanggil tidak pernah mengirim `link`), jadi baris dihapus
    daripada menampilkan "—" permanen. Prop `link` dipertahankan di tipe demi kompatibilitas pemanggil,
    tetapi tidak lagi dirender.
38. **Pencocokan katalog tipe memakai ID atau nama** — Selesai. `specs` kini dicari lewat ID dulu;
    nama hanya dipakai sebagai fallback bila `onu_type_id` null. Nama usang tidak lagi mengalahkan ID
    yang valid.
39. **Profil speed nonaktif masih bisa diterapkan lewat API** — Selesai sisi modal, validasi job diserahkan.
    `SpeedProfileModal` kini mematikan Save selama arah yang terpilih adalah nilai fallback di luar
    daftar aktif (nama lama tetap ditampilkan sebagai info, tetapi tidak bisa dikirim ulang; memilih
    placeholder kosong berarti lewati arah itu). Pengecekan `is_active` di validasi job/handler
    `apply_speed_profile` berada di `onu_service.py` (Area 2) — Area 2 **telah** menambahkan cek
    `is_active=False` di `_check_authorize` dan `_validate_job_payload` (lihat B10), sehingga sisi
    job ini kini tertutup.
40. **VLAN-ID trunk/transparent dikirim tapi diabaikan + allowed kosong tidak menghapus daftar lama** —
    Selesai lewat UI + validasi, tanpa perintah hapus karangan. Baris VLAN-ID kini hanya tampil untuk
    mode yang memakainya (lan/access/hybrid); untuk trunk/transparent `vlan_id` tidak dikirim (null).
    Trunk/hybrid dengan allowed kosong kini ditolak di frontend (Save mati) dan backend (422), karena
    tidak ada perintah hapus allowed list yang terbukti — mengirim allowed kosong sebelumnya hanya
    diam-diam mempertahankan daftar lama. Perintah hapus allowed yang terbukti tetap belum ada dan
    tidak dikarang.
41. **Live memakai min(counter_bits) vs histori per arah** — Selesai sebagian, perbaikan penuh diserahkan.
    `traffic.ts` kini menerima field opsional per arah (`in_counter_bits`/`out_counter_bits`) dan memakai
    modulus per arah bila ada, dengan fallback ke `counter_bits` tunggal. Backend tetap memakai `min()`
    sesuai tes yang ada (`test_mixed_width_reports_narrowest`: wrap terjadi pada counter tersempit;
    pada laju ONU normal delta < 2³² sehingga modulus 32-bit tetap benar untuk arah 64-bit).
    Perbaikan per arah penuh membutuhkan perubahan skema `schemas/onu_traffic.py` (milik agen lain)
    dan dicatat sebagai diserahkan.
42. **Debounce diagnostik hanya per view** — Diserahkan (Area 2, `onu_service.py`) — Area 3 tidak
    mengeditnya. Frontend sudah memblokir semua tombol diagnostik selama satu diagnostik berjalan,
    tetapi backend mengizinkan view berbeda berjalan bersamaan lewat tab kedua/API langsung.
    **Belum diperbaiki di backend.**

File Area 3: `backend/app/drivers/zte_onu_actions.py`, `backend/app/services/onu_action_service.py`,
`backend/app/services/onu_traffic_service.py`, `backend/app/services/onu_traffic_history_service.py`,
`frontend/src/pages/OnuDetail.tsx`, `frontend/src/components/onu/modals/BasicModals.tsx`,
`EthPortModal.tsx`, `WifiPortModal.tsx`, `LocationModal.tsx`, `ServiceModals.tsx`,
`OnuActionModals.tsx`, `MoveModal.tsx` (baru), `frontend/src/lib/traffic.ts`.
Tidak diubah Area 3: `VoipEnableModal`, `build_voip`, `schemas/onu.py`, `services/onu_service.py`,
`routers/onus/olts/jobs`, `schemas/onu_traffic.py`, dan semua berkas tes (bukan miliknya).

---

# Bagian E — Lintas bidang / deploy / migrasi / navigasi (Area 5)

1. **Indeks hilang** — Selesai. Indeks baru: `ix_activity_logs_olt_created`/`_user_created`/
   `_action_created`, `ix_onu_signal_onu_sampled`, `ix_jobs_olt_created` (model + migrasi).
2. **Partial unique** — Selesai, lihat B12 dan C26.
3. **Anti-pileup job diperluas** — Selesai sebagian, lihat B9 (catatan cakupan yang sengaja tidak penuh).
4. **Secret di install** — Selesai, lihat A10.
5. **pg_dump** — Selesai, lihat A10.
6. **Backup config saat uninstall** — Selesai, lihat A10.
7. **update.sh** — Selesai, lihat A10.
8. **Health check install** — Selesai, lihat A10.
9. **Validasi nama DB / escape password / URL-encode** — Selesai, lihat A10.
10. **HTTP/Caddy** — Peringatan ditambahkan, keputusan belum, lihat B15.
11. **Validasi Node/npm** — Selesai, lihat A10.
12. **Password DB tidak dicetak** — Selesai, lihat A10.
13. **Retensi/housekeeping (log, jobs, backup OLT)** — **Belum diimplementasikan.**
    Spesifikasi yang ditinggalkan Area 5 untuk pemilik worker: purge terjadwal `activity_logs` > 1 tahun,
    jobs lama, `olt_config_backups` lama, dan pembuatan partisi bulanan. Alasan tidak langsung
    diimplementasikan pada putaran ini: periode retensi log/jobs adalah keputusan produk (menghapus
    log audit tidak boleh diputuskan diam-diam oleh agen perbaikan). Purge graph yang sudah ada
    (`schedules.py`, 03:00) tidak diubah.
14. **SSE token di URL tidak pernah divalidasi ulang** — Selesai sebagian (Area 1 + Area 5).
    Area 1: stream membaca ulang user dari DB tiap ~60 detik dan berhenti bila user dinonaktifkan/
    dihapus. Area 5: `useJobStream` menutup koneksi saat token hilang dan tidak reconnect dengan
    token basi. Risiko token-di-URL itu sendiri tetap ada (didokumentasikan di kode) — butuh desain
    token SSE sekali-pakai/berumur pendek yang terpisah.
15. **Lockout in-memory** — Selesai sebagian (Area 1). `_prune_fails()` pada setiap login memangkas
    entri kedaluwarsa secara global dan membatasi 5000 kunci; keterbatasan tetap ada: single-process
    dan IP bersama proxy.
16. **`download()` di `lib/api.ts` tidak menangani 401/error jaringan** — Selesai (Area 5).
    `download()` kini menangani 401/error jaringan seperti `api()`.
17. **Dead-end `RequireAuth`** — Tidak dikerjakan Area 5 (file `auth.tsx` milik Area 1); Area 1
    memodifikasi `auth.tsx` untuk flow ganti password (lihat A7). Dead-end umum (mis. user nonaktif
    yang sudah login) tidak diklaim selesai.
18. **Tipe API** — Selesai, lihat C25.
19. **`job_service.enqueue` IntegrityError membuat session poisoned tanpa rollback** — Selesai sebagian.
    Area 1 memetakan `IntegrityError` di `_save` user berdasarkan nama constraint (pesan username vs
    email); Area 4 memetakan `IntegrityError` → 409 dengan rollback di jalur master data.
    Pemetaan umum di `enqueue` tidak diklaim selesai di semua jalur.
20. **Dokumen `docs/db-maintenance.md` dirujuk tapi tidak ada** — **Belum.** Tidak ada di laporan
    area mana pun. Bila dokumen itu memang dirujuk di kode/dokumen lain, perlu dibuat atau rujukannya
    dihapus.
21. **Kolom mati `Splitter.used_ports` / `PonPort.onu_count`** — Tidak diubah (Area 4).
    `Splitter.used_ports` hanya ada di model; tidak ada di `SplitterOut` maupun frontend mana pun
    (grep mengonfirmasi), jadi tidak ada tampilan menyesatkan yang perlu dihapus. Penghapusan kolom
    model diserahkan ke agen model dan tidak dilakukan (perlu migrasi).
22. **N+1 di daftar speed profile** — Tidak ada perbaikan eksplisit yang dilaporkan pada putaran ini.
    Status: **belum terkonfirmasi**.
23. **`snmp_community_rw` disimpan tapi tidak dipakai, namun memicu rantai reconnect** — Tidak ada
    perbaikan eksplisit yang dilaporkan pada putaran ini. Status: **belum terkonfirmasi**.
24. **Parser `parse_management_ip` gagal total bila satu ip-host tanpa gemport** — Selesai (Area 2).
    Satu `ip-host` tanpa `gemport` bernomor sama kini hanya dilewati, bukan membatalkan seluruh daftar
    (host berpasangan dengan bentuk tak dikenal tetap → `None`).
25. **Bug str-vs-int `_host_vlan_map`** — Selesai (Area 2). Bug `n` dari regex adalah str sedangkan
    kunci `out` int, yang membuat fallback flow selalu menimpa pasangan `vlan-filter` yang benar,
    sudah diperbaiki.
26. **Live traffic mengasumsikan rak/shelf 1** — Diduga, tidak dibuktikan salah pada putaran ini.
    Perbaikan `onuIf` (lihat D19) memakai `gpon-onu_1/...` sesuai `onu_iface` backend; asumsi rak/shelf
    di jalur lain tidak diubah tanpa bukti.
27. **GET `/api/` tidak dikenal mengembalikan 200+HTML** — Selesai (Area 1, lihat A11).
28. **Telnet plaintext warning di form OLT** — Diserahkan ke Area 4 (pemilik `OltManagement.tsx`);
    laporan akhir Area 4 tidak mengklaim peringatan ini. Status: **belum terkonfirmasi**.

---

# Bagian F — Driver (Area 2, irisan yang diizinkan)

- **Uplink hyphen vs underscore** — Selesai. `UPLINK_PORT_RE` dan `PORT_STATUS_RE` kini menerima
  pemisah `-` maupun `_`; `normalize_uplink_name` (baru) menyeragamkan ke `_` di `_list_uplink_ports`,
  `_parse_port_status`, dan `build_port_config_commands` (perintah selalu bentuk `_`). Sebelumnya
  `UPLINK_PREFIXES` menerima `gei-` tapi regex validasi hanya `_`, sehingga port hyphen lolos daftar
  tapi gagal saat push.
- **`wan_vlan_not_management`** — Selesai dengan catatan. Fallback dipertahankan karena tes refresh
  yang ada memberkatinya dan kandidatnya hanya flow ber-ip-host — sisa ambiguitas (multi-ip-host)
  dicatat di docstring, bukan disembunyikan.
- **Perintah hapus port VLAN di perangkat dan kirim ulang field VLAN** — **Belum** (lihat C19, C28).
  Payload `removed_ports` sudah disiapkan sebagai kontrak; implementasi driver butuh pemilik
  `zte_c320.py`.
- **Perintah hapus allowed-list VLAN dan perintah baca service-port** — **Belum, sengaja tidak dikarang**
  (lihat A9, D40). Tidak ada sintaks yang terbukti di repo.
- **WiFi Open tidak menghapus auth lama; sintaks destruktif belum terverifikasi
  (delete/set_state/reboot/restore_factory/set_onu_vlan/replace)** — **Tetap terbuka dari putaran 1.**
  Tidak diperbaiki dengan mengarang sintaks; butuh transkrip perangkat.

---

# Bagian G — VoIP (tetap ditunda atas instruksi pengguna)

Temuan yang **tidak** diperbaiki karena instruksi pengguna masih berlaku:

- Modal VoIP mengumpulkan nomor telepon/password, tetapi `build_voip` membuang keduanya dan hanya
  mengirim `voip protocol sip`.
- Tidak ada file VoIP yang diubah pada putaran ini (`VoipEnableModal`, `build_voip` tidak disentuh
  oleh area mana pun; Area 3 secara eksplisit mengonfirmasi hal ini).
- Bila VoIP ingin dikembangkan, instruksi penundaan ini harus dicabut dulu oleh pengguna.

---

# Bagian H — Yang sudah dicek dan dinyatakan OK pada audit (tidak perlu diperbaiki)

- Pola scope umum (404 bila di luar scope).
- Inti claim/backoff/debounce job dan advisory lock CLI.
- Matematika delta trafik live/history.
- Bucket sinyal identik frontend/backend.
- Enkripsi kredensial OLT dan redaksi `SECRET_FIELDS` di log.
- Matematika jendela retensi graph.
- Guard `delete_zone` lengkap.
- Pratinjau vs hasil hapus graph (payload sama, angka hasil tampil setelah hapus).
- `Configured.tsx` sudah mengirim multi-nilai; yang rusak adalah backend (sudah diperbaiki, B7).
- `Unconfigured.tsx` tidak perlu diubah — tombol rescan sudah mengirim `olt_id` yang benar.

---

# Bagian I — Daftar file yang berubah (verifikasi gabungan)

Diubah (77 file, dari `git status`):

- Backend: `core/config.py`, `core/deps.py`, `core/security.py`, `drivers/onu_report.py`,
  `drivers/types.py`, `drivers/zte_c320.py`, `drivers/zte_onu_actions.py`, `main.py`,
  `models/activity_log.py`, `models/job.py`, `models/olt.py`, `models/onu.py`,
  `models/onu_preset.py`, `models/onu_type.py`, `models/speed_profile.py`, `models/splitter.py`,
  `models/user.py`, `models/zone.py`, `repositories/activity_log_repo.py`, `repositories/job_repo.py`,
  `repositories/master_data_repo.py`, `repositories/onu_repo.py`, `routers/auth.py`,
  `routers/jobs.py`, `routers/onu_actions.py`, `routers/onus.py`, `routers/speed_profiles.py`,
  `schemas/activity_log.py`, `services/activity_log_service.py`, `services/auth_service.py`,
  `services/graph_data_service.py`, `services/job_service.py`, `services/master_data_service.py`,
  `services/olt_onboarding.py`, `services/olt_service.py`, `services/onu_action_service.py`,
  `services/onu_service.py`, `services/onu_traffic_history_service.py`,
  `services/onu_traffic_service.py`, `services/speed_profile_service.py`,
  `services/sync_service.py`, `services/user_service.py`, `services/vlan_service.py`,
  `worker/main.py`, `tests/test_onu_actions.py`, `tests/test_onu_diagnostics.py`,
  `tests/test_onu_detail_layout.py`.
- Frontend: `components/Layout.tsx`, `components/onu/modals/BasicModals.tsx`,
  `EthPortModal.tsx`, `LocationModal.tsx`, `ModalShell.tsx`, `OnuActionModals.tsx`,
  `ServiceModals.tsx`, `WifiPortModal.tsx`, `lib/api.ts`, `lib/auth.tsx`, `lib/jobs.ts`,
  `lib/nav.ts`, `lib/onuActions.ts`, `lib/traffic.ts`, `main.tsx`, `pages/AuthorizeOnu.tsx`,
  `pages/Dashboard.tsx`, `pages/Lainnya.tsx`, `pages/Logs.tsx`, `pages/OltDetail.tsx`,
  `pages/OnuDetail.tsx`, `pages/settings/GraphData.tsx`, `pages/settings/OltManagement.tsx`,
  `pages/settings/OnuTypes.tsx`, `pages/settings/SpeedProfile.tsx`,
  `pages/settings/Splitters.tsx`, `pages/settings/UserManagement.tsx`,
  `tests/onu-detail.check.mjs`, `tests/graph-data.check.mjs`.
- Deploy: `install.sh`, `update.sh`, `uninstall.sh`.

Baru (5 file):

- `backend/alembic/versions/a5f100000001_area5_indexes_partial_unique.py`
  (revision `a5f100000001`, down_revision `d7e8f9a0b1c2` — migrasi baru, migrasi lama tidak diubah).
- `backend/tests/test_auth_area1.py` (Area 1).
- `backend/tests/test_area2_lifecycle.py` (Area 2, 8 tes).
- `backend/tests/test_log_category_filter.py` (putaran 2, sudah ada sebelum putaran ini).
- `frontend/src/components/onu/modals/MoveModal.tsx` (Area 3).

Catatan: `drivers/types.py` dan `routers/onu_actions.py` tampak berubah di `git status` tetapi tidak
dirinci di laporan area mana pun — kemungkinan perubahan kecil antar-agen (mis. penyesuaian
interface/route terkait). Sebelum commit, diff kedua file itu sebaiknya dibaca sekali lagi.

---

# Bagian J — Yang masih terbuka / perlu keputusan pengguna / perlu dicek sebelum rilis

**Butuh keputusan pengguna (tidak boleh diputuskan agen sendiri):**

1. **Caddy+TLS vs LAN-only** (B15) — installer kini jujur memperingatkan HTTP saja; arsitektur belum diubah.
2. **VoIP** (Bagian G) — tetap ditunda sampai pengguna mencabut penundaan.
3. **Retensi/housekeeping log/jobs/backup** (E13) — periode retensi belum diputuskan; jangan dihapus
   diam-diam.
4. **Commit/push** — belum pernah diizinkan; semua perubahan masih uncommitted/unpushed.
5. **Retensi graph per-tenant** (B4) — bila diinginkan, itu perubahan produk.

**Belum selesai / sebagian (perlu putaran lanjutan bila diinginkan):**

6. Perintah hapus port VLAN di driver, kirim ulang field VLAN, perintah hapus allowed-list,
   perintah baca service-port (C19, C28, D40, Bagian F) — butuh sintaks perangkat yang terbukti.
7. WiFi Open tidak menghapus auth lama; sintaks destruktif belum terverifikasi (Bagian F) — butuh
   transkrip perangkat.
8. Refresh-metrics OltDetail membuang `job_id`; daftar ONU OltDetail terpotong 200 (C45).
9. Pengiriman `device_metadata` dari backend (D2).
10. Debounce diagnostik per-ONU di backend (D42).
11. Perbaikan per-arah `counter_bits` penuh, butuh perubahan skema `schemas/onu_traffic.py` (D41).
12. Validasi `next` di Login masih meloloskan `//evil.com` (C52).
13. Preset tanpa endpoint update (C47).
14. Migrasi Fernet ke salt/KDF — akan merusak kredensial tersimpan bila dilakukan tanpa migrasi kunci (B14).
15. Revokasi token retroaktif penuh — butuh kolom versi token (A7).
16. Token SSE di URL — butuh desain token sekali-pakai/berumur pendek (E14).
17. Unique DB `(splitter_id, splitter_port)` dan `customer_id` (B2, C57) — cek aplikasi sudah ada,
    balapan persis belum tertutup.
18. Pemeriksaan ulang guard hapus VLAN di worker — butuh `scalar()` di `FakeDb` tes (A4).
19. Penambahan `fetch_pon_oper_states` ke interface `OltDriver` resmi (B11) — saat ini via `getattr`.
20. Penulis status OLT keempat (`onu_traffic_history_service.py`) belum ditinjau (C47).
21. `docs/db-maintenance.md` dirujuk tapi tidak ada (E20).
22. N+1 daftar speed profile dan `snmp_community_rw` tidak dipakai (E22, E23) — belum terkonfirmasi.
23. Telnet plaintext warning di form OLT (E28) — belum terkonfirmasi.
24. Arah sebaliknya konsistensi VLAN primer vs attached (C6) dan penghapusan pending row di jalur
    replace-sn langsung (C60) — belum terkonfirmasi.
25. Cek kapasitas pada update location (D32) — belum terkonfirmasi.
26. Gate manager per-kind aksi langsung (A8) dan validasi kepemilikan PATCH OLT (B6) — perlu audit
    ulang sebelum rilis karena laporan area tidak merincinya satu per satu.
27. Diff `drivers/types.py` dan `routers/onu_actions.py` perlu dibaca sekali lagi sebelum commit
    (Bagian I).

**Belum diverifikasi terhadap sistem nyata (bukan klaim):**

28. Tidak ada pengujian ke OLT ZTE nyata dan tidak ada Postgres nyata.
29. Migrasi baru belum dijalankan ke DB nyata (hanya `upgrade --sql`).
30. Skrip install/update/uninstall belum dijalankan end-to-end (hanya `bash -n`).
31. Multi-filter Configured belum diverifikasi end-to-end terhadap DB nyata.
32. Pemeriksaan layout Playwright tidak bisa dijalankan di lingkungan ini.

---

# Penutup

Putaran ini menutup sebagian besar temuan Kritis dan Tinggi dari audit menyeluruh, dengan
verifikasi gabungan akhir **backend 331 passed / 27 skipped / 0 failed**, **frontend build lolos**,
dan **frontend check lolos (exit 0)**. Yang sengaja tidak ditutup ditulis di Bagian J dengan
alasannya masing-masing, supaya tidak ada yang diklaim selesai padahal belum — termasuk VoIP yang
tetap ditunda atas instruksi pengguna, dan keputusan Caddy vs LAN-only yang masih menunggu pengguna.

---

# Putaran 4 — Audit menyeluruh lagi dan fix (2026-10-28 malam)

Instruksi pengguna: "lanjut audit menyeluruh lagi dan fix". Audit putaran 4 dilakukan
6 agen read-only paralel, lalu perbaikan oleh 5 agen paralel + rekonsiliasi agen utama.
Tidak ada commit/push. VoIP tidak disentuh sama sekali. Tidak ada sintaks CLI yang
dikarang. Tidak ada migrasi Alembic lama yang diubah.

## Koreksi atas klaim putaran 3 (jujur dicatat, bukan disembunyikan)

- **A8 (gate manager) tidak akurat.** Backend hanya meng-gate `MANAGER_KINDS =
  {delete, restore-factory, replace-sn, move}` + endpoint tertentu; `POST /{serial}/vlan`
  dan aksi langsung lain memang terbuka untuk role `user` dalam scope. PRD §3.7
  mengizinkan aksi operasional user, jadi gate TIDAK diperluas diam-diam di putaran 4;
  penyelarasan gate adalah keputusan produk.
- **B1 (config_options) hanya separuh benar.** VLAN/profile sudah ber-scope, tetapi
  Zone/Splitter diambil tanpa filter. Diperbaiki putaran 4 (filter owner via zone).
- **B6 (owner_id OLT) tidak tuntas.** `_owner_id` menulis ulang `owner_id` non-Superadmin
  menjadi id pemanggil, bukan menolak. Diperbaiki putaran 4: kini ditolak
  `ValidationAppError`, dan `_manager` juga mengecek `is_active`.
- **A3 (re-replace) regresi.** Setelah replace gagal, baris `config_state="failed"`
  diblokir gate umum yang menuntut `success`. Diperbaiki putaran 4: cabang gate
  `replace_onu` mengizinkan dari `success`/`failed`.
- **Klaim lama soal prompt (y/n) salah.** `AUTO_ANSWER_PROMPTS` di `transport/ssh.py`
  adalah dead code; `send_command` tidak menjawab prompt. Diperbaiki putaran 4:
  prompt konfirmasi dijawab "n" (batal) lalu job gagal dengan jelas, bukan sukses palsu.

## Temuan kritis putaran 4 dan perbaikannya

- **K1 — Pola error ZTE berlubang → sukses palsu.** `ZTE_ERROR_PATTERNS` tidak
  mengenal `%error`/`%code` generik, padahal repo sendiri mengutip `%Error 20206`,
  `%Code 63953`, `%Error 20200`. Perintah ditolak perangkat bisa ter-commit ke DB
  sebagai sukses. Perbaikan: pola generik ditambahkan (dari teks yang benar-benar
  ada di repo) + fixture tes di `test_lifecycle_round2.py`.
- **K2 — `send_config_set` tidak berhenti pada perintah ditolak.** 12 blok diganti
  `_send_config` per-perintah: berhenti pada error pertama, `raw_command` hanya
  memuat perintah yang benar-benar terkirim. Tidak ada rollback CLI (perintah yang
  sudah terkirim tetap teraplikasi) — yang dicegah adalah eksekusi sesudah error.
- **SSE tidak pernah kedaluwarsa.** Stream hanya mengecek `is_active`/`deleted_at`
  tiap ~60 detik, tidak pernah `exp`, klaim `ph`, dan scope dihitung sekali.
  Perbaikan: tiap interval, token di-decode ulang (termasuk `exp`), user dibaca
  ulang, klaim `ph` dibandingkan `password_hash`, dan scope dihitung ulang lewat
  `scope_olt_ids`. Tanpa token, fallback lama dipertahankan.
- **`must_change_password` hanya di frontend.** Kini ditegakkan di server
  (`get_current_user`): user ber-flag hanya boleh `POST /api/auth/change-password`
  dan `GET /api/auth/me`, endpoint lain 403. Terverifikasi TestClient.
- **VLAN `is_active` berbohong dua arah.** Create men-commit `is_active=True`
  sebelum job jalan; delete men-set `False` saat enqueue. Perbaikan: create OLT
  dengan `False`, `push_create` men-set `True` saat sukses; delete tidak lagi
  mengubah nilai saat enqueue (tetap aktif sampai worker sukses). Frontend
  `VlanDrawer` kini memakai `job_id` + JobTrace.
- **Backup config OLT plaintext + tanpa retensi.** Tetap terbuka (lihat bawah):
  format penyimpanan tidak diubah tanpa migrasi + pengujian; retensi butuh
  keputusan pengguna.
- **Installer satu secret bersama.** Kini `install.sh` menulis `app_secret_key`
  dan `jwt_secret_key` terpisah; config lama dengan satu `secret_key` tetap jalan
  lewat fallback per kunci.
- **`update.sh` bisa meninggalkan service mati.** Kini ada trap `ERR` yang
  me-restore kode lama dari backup dan me-restart service; `pg_dump` kini wajib
  (update dan uninstall membatalkan bila dump tidak tersedia/gagal, kecuali
  uninstall tanpa `config.ini` sama sekali). Rollback = restore kode sumber;
  `venv/`/`dist/` tidak ikut di-backup, jadi gagal `pip`/`build` masih butuh
  instal/build ulang manual — didokumentasikan di `docs/db-maintenance.md`.
- **Partisi activity_logs tidak pernah dibuat.** Kini ada job scheduler tiap
  tanggal 25 pukul 04:00 yang membuat partisi bulan berikutnya; pemindahan baris
  dari partisi DEFAULT tetap langkah manual di jendela perawatan. Dokumen baru
  `docs/db-maintenance.md` dibuat (sebelumnya dirujuk tapi tidak ada).
- **Email soft-delete unique bug (sama seperti username).** Migrasi baru
  `c6a200000001`: `users.email` kehilangan `unique=True`, mendapat partial
  unique `uq_users_email_active`; kolom TIDAK dihapus (DB lama bisa berisi email).
  Catatan: pemetaan error `user_service._save` untuk email lama masih memakai
  nama constraint lama — jalur ini praktis tidak terjangkau karena tidak ada API
  yang menulis email.
- **Kolom mati dihapus.** `Splitter.used_ports` dan `PonPort.onu_count` dihapus
  lewat migrasi baru `b5f200000001` (grep membuktikan tidak ada pembaca/penulis;
  `PonPortOut.onu_count` diisi dari hitungan query). Dua migrasi putaran 4 sempat
  ber-head ganda (down_revision sama `a5f100000001`); agen frontend merantainya
  (`c6a200000001` setelah `b5f200000001`), dan agen utama menambah
  `d7a300000001` di atasnya — head akhir tunggal (lihat verifikasi).
- **Lainnya (pilihan):** cancel job sistem hanya manager/pembuat; dummy-hash
  argon2 menutup timing oracle login; lockout tidak lagi mengusir entri aktif
  (percobaan baru saat penuh dilupakan, bukan mengusir lockout korban); guard
  `_username_taken_by_deleted` dihapus + pemetaan constraint diperbarui;
  Login `next` menolak `//`, `/\`, `/login`, `/setup`; batas panjang
  username ≤64 / password ≤128 / old_password ≤128; RequireAuth error page
  mendapat tombol Coba lagi/Keluar; UserManagement POST tidak lagi mengembalikan
  `superadmin` untuk non-Superadmin (PATCH tetap tanpa role; penghapusan total
  akan membuat POST Admin 422 karena `UserCreate.role` wajib — penegak terakhir
  tetap backend `_may_set_role`); proteksi Superadmin terakhir memakai
  `pg_advisory_xact_lock`; worker authorize memvalidasi ulang VLAN/profile
  (`is_active`, scope, arah download/upload) dan gagal sebelum kirim, bukan
  mengirim `None` diam-diam; gate `is_active` OLT di enqueue (404/409, bukan
  baris `configuring` buntu); `enqueue` rollback pada IntegrityError;
  Unconfigured menampilkan lagi baris `failed` (anti-join hanya `success`/
  `configuring`) + tombol "Coba lagi" diganti resync langsung; guard None
  optik per kolom; `_mark_olt_ok` hanya bila ada pembacaan sukses;
  `list_unconfigured` gagal sebelum wipe bila output mengandung pola error;
  delete idempotent di `replace_onu`; `set_onu_vlan` menangani `old is None` +
  dedup; `set_state` worker menolak non-bool; normalisasi serial di `_get_row`
  dan bulk; `customer_id` kosong setelah normalisasi ditolak dan endpoint
  `customer_id_taken` kini ber-scope (semantik unique global TIDAK diubah);
  `list_interfaces` di bawah `olt_cli_lock` (409 bila sibuk); penanda
  `unreachable` `test_connection` di-commit sebelum `_fail` rollback;
  normalisasi hyphen/underscore `set_port_config`; `update_info` mendapat cek
  zone–splitter/kapasitas/port-tanpa-splitter; splitter authorize dicek
  OLT/PON; dropdown splitter AuthorizeOnu difilter OLT/zone; `preset_id`
  berdiri sendiri TIDAK ditolak (preset = template pengisi form, authorize
  tetap memakai VLAN/profile eksplisit — bila pengguna ingin menolak, itu satu
  baris validasi di `_check_authorize`); `fetch_pon_oper_states` masuk interface
  `OltDriver` sebagai method non-abstrak default `{}`; gate enqueue bersama
  `_check_onu_job_gate` (DRY); `config_options` Zone/Splitter ber-scope;
  cabang `onu-type` menolak tipe nonaktif; `refresh-ip` non-ZTE 501 bukan 500;
  attached-VLANs sukses menyesuaikan `vlan_id` primer bila primer dihapus;
  replace-sn langsung menghapus baris pending serial baru; `ActionResult`
  mendapat `job_id`, OnuDetail + PrimaryVlanModal menampilkan JobTrace dan
  tidak menutup modal sebagai sukses bila `r.ok === false`; debounce
  diagnostik per-ONU (ketiga tipe); onu-mode/IPTV 501 kini dialog "Segera"
  bukan form yang bisa diisi; Refresh-metrics OltDetail menyimpan `job_id` +
  JobTrace + merender `refresh.error`; daftar ONU OltDetail paginasi penuh
  (`page`/`size=50`, label "X–Y dari N"); N+1 `list_profiles` menjadi satu
  query scalar_subquery; preset mendapat PATCH + tab edit/hapus di Splitters
  (tanpa route baru — `main.tsx` di luar daftar agen; halaman
  `/settings/presets` sendiri adalah tindak lanjut); Telnet mendapat peringatan
  plaintext + default port mengikuti protokol (22/23, hanya bila port masih
  default); guard hapus VLAN cek preset kini ber-scope pemilik (VLAN global
  sengaja tanpa batas, konservatif); `update_vlan` MENOLAK ubah `type` saat
  masih dirujuk (bukan peringatan — karena update DB-only tanpa push ulang
  tipe ke perangkat); worker `push_delete` memeriksa ulang guard hapus VLAN;
  splitter kapasitas NULL = "belum diketahui" (label merah di Splitters);
  Configured: sanitasi page/size, search controlled + debounce 300 ms, Reset
  mengosongkan teks, peringatan export >50.000, filter tipe gabungan katalog +
  nilai baris; query `["me"]` staleTime 60 detik; kartu OLT Aktif Dashboard
  hanya link untuk manager; ActivityFeed kini benar-benar link ke Logs;
  SSE `invalidateFor` menambah kunci interfaces/vlans OltDetail; `api()` 401
  mempertahankan `next` + menampilkan body error non-JSON terpotong 200 karakter;
  Logs UI mengekspos `user_id`/`since`/`until`/`size`; halaman ganti password
  mandiri `/akun/password` (logout paksa sesudahnya); `set_port_config`
  mendapat gate `ensure_writes_allowed` di enqueue + worker; unique
  `(splitter_id, splitter_port)` partial di migrasi `c6a200000001`;
  `OltManagement` kini merender `recheck.isError`.

## Rekonsiliasi agen utama (bukan klaim agen)

- **`scope_olt_ids` yatim — DIPERBAIKI induk.** Agen auth terhalang daftar file
  (`rbac.py` di luar daftarnya). Patch 1 baris diterapkan induk: non-Superadmin
  dengan `owner is None` kini mendapat scope kosong (`select(Olt.id).where(False)`),
  bukan `None` tanpa batasan.
- **Penulisan status OLT di sumber sampler — DIPERBAIKI induk.** Baris
  `olt.status/last_error = "online"/None` di `onu_traffic_history_service.sample_olt`
  dihapus di sumbernya; wrapper pemulih di handler worker kini menjadi no-op
  yang tidak berbahaya dan dibiarkan.
- **Penolakan splitter kapasitas NULL — DIPERBAIKI induk.** Agen master data
  memutuskan kebijakan (tolak sampai ratio diisi) tetapi implementasinya hidup
  di `onu_service._check_authorize`/`update_info` milik agen lifecycle yang tidak
  menerapkannya. Induk menambahkan penolakan di kedua tempat dengan pesan
  "Kapasitas splitter belum diisi; isi dulu ratio splitter".
- **`device_metadata` — DIPERBAIKI induk.** Agen OnuDetail terhalang skema
  (`schemas/onu.py` di luar daftarnya). Induk menambah field `device_metadata`
  (`DeviceMetadataOut`) ke `OnuDetail` dan mengisinya di `get_onu` lewat
  `parse_device_description` yang sudah ada.
- **`counter_bits` per arah — DIPERBAIKI induk.** `OnuTrafficSample` mendapat
  `in_counter_bits`/`out_counter_bits` opsional; `read_sample` mengisinya
  (masuk = download, keluar = upload) sambil mempertahankan `counter_bits=min`
  untuk klien lama.
- **Sumber histori sinyal — DIPERBAIKI induk.** Kolom nullable baru
  `onu_signal_history.source` lewat migrasi baru `d7a300000001` (down_revision
  `c6a200000001`); penulis baru: `sync_onu_status` → `"status_change"`,
  `sync_onu_optical` → `"optical"`; baris lama NULL = tidak diketahui, tanpa
  backfill tebakan; `SignalPoint` meneruskan field apa adanya.
- **`build_speed_profile` dead code — TIDAK dihapus.** Hanya dipakai tes
  (`test_onu_actions.py`, di luar daftar agen); docstring kini mencatatnya
  eksplisit supaya penghapusan fungsi + tes dilakukan sekaligus oleh pemilik tes.
- **Anti-pileup partial unique untuk `set_vlan_ports`/`set_port_config`/
  `push_speed_profile` — TIDAK dibuat.** Cek aplikasi `OLT_LEVEL_SINGLE_ACTIVE`
  sudah mencakup ketiganya; index baru berisiko menolak job aktif sah dengan
  payload berbeda. Partial unique `(splitter_id, splitter_port)` justru dibuat
  agen frontend (migrasi `c6a200000001`) — laporan lifecycle yang menyebutnya
  belum dibuat sudah kedaluwarsa oleh pekerjaan paralel itu.
- **OltManagement JobTrace per baris — TIDAK penuh.** Backend `_fail`
  `test_connection` sudah diperbaiki (status/last_error kini ter-commit) dan
  UI kini merender `recheck.isError`; JobTrace per baris penuh belum dibuat.

## Verifikasi gabungan putaran 4 (agen utama, setelah semua agen selesai)

- Backend: `cd backend && /tmp/nexfiber-venv2/bin/python -m pytest tests/ -q`
  → **340 passed, 27 skipped, 0 failed** (baseline putaran 3: 331 passed;
  +9 = tes baru `test_lifecycle_round2.py`). Catatan lingkungan: venv lama
  `/tmp/nexfiber-venv` sudah hilang (ephemeral `/tmp`); agen-agen memakai
  `/tmp/nexfiber-venv2`, `/tmp/nf-venv`, `/tmp/nxvenv`.
- Frontend: `npm run build` lolos (9,73 detik), `npm run check` lolos
  (exit 0, 71 baris `ok` + 4 pemeriksaan Graph Data). Selama pengerjaan sempat
  ada error tsc di `UserManagement.tsx` dan `OltDetail.tsx` dari agen paralel;
  keduanya sudah diperbaiki pemilik file masing-masing sebelum verifikasi akhir.
- Alembic: **satu head: `d7a300000001`**; `upgrade d7a300000001 --sql`
  menghasilkan `ALTER TABLE onu_signal_history ADD COLUMN source VARCHAR(32)`.
- Skrip: `bash -n install.sh update.sh uninstall.sh` → OK (tidak dijalankan
  end-to-end; butuh root/Postgres/instalasi nyata).
- Git: 95 file berubah, +4699/−837 terhadap base `4c77449`, semua
  uncommitted/unpushed. Tidak ada file VoIP dalam diff. Tidak ada migrasi lama
  yang diubah.

## Masih terbuka setelah putaran 4 (tidak diklaim selesai)

Semua yang terbuka dari Bagian J yang belum disebut di atas tetap terbuka, plus:

- Perintah CLI UNVERIFIED (reboot `reset`, restore factory, `set_state`
  shutdown, `set_onu_vlan` `no flow`, move, delete) + tidak ada `write` +
  rack hardcode `1` — hanya deteksi/validasi/DB yang diperbaiki, sintaks tidak
  diubah; butuh transkrip uji ONU nyata.
- VoIP (ditunda atas instruksi pengguna), Fernet KDF migration, kolom versi
  token + logout server-side, token SSE sekali-pakai, cookie httpOnly,
  Caddy vs LAN-only, retensi log/jobs/backup (periode = keputusan pengguna),
  backup config plaintext, PPPoE provisioning ke perangkat, arah gate
  sync UI vs backend, semantik unique `customer_id` global, live-DB/live-device
  verification (migrasi baru hanya `upgrade --sql`, skrip hanya `bash -n`).
- Migrasi tabel lockout (bila batas 5000 kunci sering tercapai) sebagai
  pengganti eviction yang benar.
- Kolom `email` + pemetaan error `_save` untuk nama constraint email baru.
- Halaman `/settings/presets` sendiri (saat ini tab di Splitters).
- JobTrace per baris cek koneksi OltManagement (baru `isError` yang dirender).
- `get_or_create_splitter` tetap membuat splitter kapasitas NULL; penolakan
  authorize ke splitter NULL kini aktif, jadi operator wajib mengisi ratio dulu.
