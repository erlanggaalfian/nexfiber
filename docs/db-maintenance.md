# Perawatan Database Nexfiber

Dokumen ini dirujuk kode (`backend/app/models/activity_log.py` dan migrasi awal
`fa25488b1bab`) tetapi sebelumnya tidak ada filenya. Isinya ditulis jujur:
mana yang sudah otomatis, mana yang masih manual.

## 1. Partisi `activity_logs`

Tabel `activity_logs` dipartisi RANGE per bulan pada `created_at` (PK komposit
`id, created_at`). Migrasi awal hanya membuat partisi `activity_logs_default`
(partisi DEFAULT yang menampung baris di luar rentang partisi eksplisit),
sehingga insert tidak pernah gagal meski partisi bulan berjalan belum dibuat.

### Otomatis (sudah ada)

- Scheduler worker (`backend/app/worker/schedules.py`,
  `create_next_activity_log_partition`) berjalan tiap tanggal 25 pukul 04:00
  dan membuat partisi bulan berikutnya dengan
  `CREATE TABLE IF NOT EXISTS activity_logs_YYYY_MM PARTITION OF activity_logs
  FOR VALUES FROM (...) TO (...)`. Bila partisi sudah ada, perintah ini no-op.
- Job ini **tidak memindahkan data**. Baris yang sudah masuk
  `activity_logs_default` tetap di sana sampai dipindahkan manual (lihat bawah).

### Manual (jendela perawatan, belum otomatis — sengaja)

Memindahkan baris dari DEFAULT ke partisi bulannya masing-masing butuh
jendela perawatan karena melibatkan pemindahan baris antar partisi pada tabel
yang terus ditulis worker. Langkahnya, setelah backup (lihat §3):

```sql
-- 1. Lihat dulu berapa baris yang ada di DEFAULT dan rentangnya.
SELECT count(*), min(created_at), max(created_at)
FROM activity_logs_default;

-- 2. Buat partisi bulan yang belum ada (bila scheduler belum membuatnya).
CREATE TABLE IF NOT EXISTS activity_logs_YYYY_MM
  PARTITION OF activity_logs
  FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM-01');

-- 3. Pindahkan per bulan (ulangi per bulan yang ada di DEFAULT).
--    Postgres memindahkan baris ke partisi yang sesuai secara otomatis
--    saat baris di-UPDATE ke nilai yang masih dalam rentang yang sama;
--    cara yang aman adalah DELETE + INSERT dalam satu transaksi per batch,
--    atau pg_partman bila sudah dipakai. Jangan menjalankan UPDATE massal
--    tanpa batas pada tabel produksi yang sedang ditulis.
```

Status jujur: prosedur langkah 3 di atas belum pernah dijalankan/dites
terhadap database produksi di repo ini. Jangan menjalankannya tanpa backup
terbaru dan tanpa mengukur ukuran `activity_logs_default` dulu.

## 2. Retensi — otomatis, kecuali dua periode provisional

- Retensi data graph (trafik/sinyal) **sudah otomatis**: purge harian pukul
  03:00 oleh scheduler (`purge_graph_data`), mengikuti setting di
  Settings → Graph Data (default trafik 30 hari, sinyal 90 hari). Purge ini
  dicatat ringkas di activity log (`housekeeping.purge_graph`: jumlah per
  jenis, tanpa isi baris).
- Retensi `activity_logs`, `jobs`, dan `olt_config_backups` **sudah otomatis**
  lewat `housekeeping_service.purge_all`, dijadwalkan pukul 03:30 oleh
  scheduler (`purge_housekeeping`), setelah purge graph. Aturan: hanya baris
  melewati retensi yang dihapus, ber-batch, dan setiap jalan purge mencatat
  satu baris ringkasan `housekeeping.purge` (jumlah per tabel, tanpa isi).
  - `activity_logs`: 365 hari — angka ini ADA di PRD (Logs: retensi default
    365 hari; raw_command/raw_output retensi 1 tahun) dan docstring model.
  - `jobs`: 180 hari, hanya job terminal (success/failed/cancelled), tidak
    pernah job pending/running, dan tidak pernah job yang masih dirujuk
    activity_log. **PROVISIONAL: PRD diam soal retensi jobs, periode ini
    masih butuh konfirmasi pemilik sebelum dianggap final.**
  - `olt_config_backups`: 90 hari, dengan pengecualian backup terbaru tiap
    OLT tidak pernah dihapus. **PROVISIONAL: PRD diam soal retensi backup,
    periode ini masih butuh konfirmasi pemilik sebelum dianggap final.**
- Enkripsi backup config: **belum diubah**. Backup (`olt_config_backups`)
  menyimpan running-config apa adanya; mengubah format penyimpanannya
  menjadi terenkripsi butuh migrasi data + pengujian baca-tulis dan tidak
  dilakukan diam-diam di sini.

## 3. Backup

- `update.sh` dan `uninstall.sh` **membatalkan** bila `pg_dump` tidak tersedia
  atau nama database tidak bisa dibaca — tidak lagi lanjut tanpa backup DB.
  File backup di `/var/backups/nexfiber` dibuat dengan `umask 027` dan
  `chmod 640` (hanya pemilik + grup yang bisa baca; file berisi config dan
  dump DB, jadi jangan diubah izinnya menjadi lebih longgar).
- `update.sh`: bila gagal sebelum health check, service lama di-restart
  lewat trap (lihat §4). Restore DB dari dump bersifat manual dan tidak
  otomatis: `sudo -u postgres psql <nama_db> < file-dump.sql` — jalankan
  hanya bila migrasi sudah berjalan dan perlu dibatalkan.

## 4. Update dan rollback (update.sh)

- Backup kode lama: `rsync` dari `/opt/nexfiber` ke
  `/var/backups/nexfiber/app-<timestamp>` — dengan pengecualian `venv/`,
  `node_modules/`, `dist/`, `__pycache__/`. Artinya **venv dan dist tidak
  ikut di-backup**; rollback mengembalikan kode sumber, lalu service
  di-restart dengan venv/dist yang ada. Bila `pip install` atau `npm run build`
  yang gagal, venv/dist bisa berada dalam keadaan campuran — dalam kasus
  itu, jalankan ulang `pip install -r backend/requirements.txt` dan
  `npm ci && npm run build` secara manual setelah rollback, atau pulihkan
  dari snapshot filesystem bila ada. Alternatif yang dipertimbangkan dan
  tidak dipilih: build di direktori staging dulu — lebih aman untuk build,
  tetapi mengubah lebih banyak alur update dan belum dites end-to-end,
  sehingga tidak diklaim di sini.
- Trap: kegagalan apa pun setelah service dihentikan (sebelum health check)
  menjalankan restart service lama (dari kode yang sudah ter-backup bila
  rsync sudah jalan, atau dari kode lama bila belum). Bila health check
  gagal setelah update, kode lama di-restore dari backup dan service
  di-restart, lalu skrip exit 1. DB **tidak** di-rollback otomatis.
- `install.sh` menulis `app_secret_key` dan `jwt_secret_key` terpisah
  (dua nilai acak) pada `config.ini` baru; config lama yang hanya punya
  `secret_key` tetap jalan karena config membaca fallback ke `secret_key`
  untuk kunci yang tidak ditulis.
