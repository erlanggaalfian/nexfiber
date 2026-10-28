"""Housekeeping terjadwal: purge baris yang sudah melewati retensi.

Yang SUDAH jalan sebelum file ini ada: purge data graph (trafik/sinyal) tiap
03:00 oleh scheduler (`worker/schedules.py::purge_graph_data`), mengikuti
retensi per jenis dari Settings -> Graph Data. File ini menutup sisanya yang
ditinggalkan audit putaran 4 (Area 5) sebagai "belum diimplementasikan":
`activity_logs`, `jobs` terminal, dan `olt_config_backups`.

Asal tiap periode (jangan diubah diam-diam — menghapus log audit adalah
keputusan produk):
- `activity_logs`: 365 hari — ADA di PRD (halaman Logs: "dibersihkan otomatis
  oleh retensi (default 365 hari)"; raw_command/raw_output retensi 1 tahun)
  dan di docstring model ActivityLog ("Retention 1 year").
- `jobs`: 180 hari — PROVISIONAL, PRD diam. Konservatif (menyimpan lebih lama
  daripada log) karena job adalah jejak eksekusi; hanya job terminal yang
  dihapus, dan hanya bila tidak dirujuk activity_log mana pun (FK
  activity_logs.job_id -> jobs.id akan menolak penghapusan bila tidak dicek).
  Periode ini MASIH BUTUH konfirmasi pemilik sebelum dianggap final.
- `olt_config_backups`: 90 hari — PROVISIONAL, PRD diam (PRD hanya bilang
  backup disimpan bila checksum berubah). Backup terbaru tiap OLT TIDAK PERNAH
  dihapus, berapapun umurnya, supaya purge tidak pernah meninggalkan OLT tanpa
  backup sama sekali. Periode ini MASIH BUTUH konfirmasi pemilik.
  Enkripsi isi backup adalah area terpisah dan TIDAK diubah di sini.

Aturan keras untuk semua purge di sini:
- Hanya baris yang LEBIH TUA dari cutoff (`< cutoff`, bukan `<=`) yang dihapus;
  baris di dalam retensi tidak pernah disentuh.
- Hapus BERBATCH (pola yang sama dengan graph_data_service._delete_batched:
  DELETE ... WHERE id IN (SELECT ... LIMIT n) + commit per batch) supaya lock
  cepat dilepas. Helper lokal karena helper graph bersifat privat modul itu.
- Setiap jalan purge mencatat SATU baris activity log ringkas
  (action `housekeeping.purge`, jumlah baris per tabel, tanpa isi baris),
  supaya purge itu sendiri bisa diaudit. Baris ringkasan itu dibuat SETELAH
  purge log, dengan created_at = sekarang, jadi tidak ikut terhapus.
- Bukan job queue: seperti purge graph, housekeeping tidak menyentuh perangkat,
  jadi scheduler APScheduler memanggilnya langsung (lihat schedules.py).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.job import Job
from app.models.olt import OltConfigBackup
from app.repositories import activity_log_repo

# Lihat docstring modul untuk asal tiap angka.
ACTIVITY_LOG_RETENTION_DAYS = 365
JOB_RETENTION_DAYS = 180  # PROVISIONAL — PRD diam, butuh konfirmasi pemilik.
BACKUP_RETENTION_DAYS = 90  # PROVISIONAL — PRD diam, butuh konfirmasi pemilik.

BATCH = 20_000


async def _delete_batched(db: AsyncSession, model, conds: list) -> int:
    total = 0
    while True:
        ids = select(model.id).where(*conds).limit(BATCH).scalar_subquery()
        result = await db.execute(delete(model).where(model.id.in_(ids)))
        removed = result.rowcount or 0
        total += removed
        await db.commit()
        if removed < BATCH:
            return total


async def purge_activity_logs(db: AsyncSession, now: datetime | None = None) -> int:
    """Hapus log aktivitas lebih tua dari 365 hari (PRD). Tabel terpartisi per
    bulan: DELETE pada tabel induk berlaku ke semua partisi."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=ACTIVITY_LOG_RETENTION_DAYS)
    return await _delete_batched(db, ActivityLog, [ActivityLog.created_at < cutoff])


async def purge_jobs(db: AsyncSession, now: datetime | None = None) -> int:
    """Hapus job TERMINAL (success/failed/cancelled) lebih tua dari 180 hari.
    Job pending/running TIDAK PERNAH dihapus (menghapusnya merusak antrean).
    Job yang masih dirujuk activity_log juga dilewati (FK menolak hapus)."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=JOB_RETENTION_DAYS)
    finished = or_(
        Job.finished_at < cutoff,
        and_(Job.finished_at.is_(None), Job.updated_at < cutoff),
    )
    referenced = exists().where(ActivityLog.job_id == Job.id)
    return await _delete_batched(
        db, Job,
        [Job.status.in_(("success", "failed", "cancelled")), finished, ~referenced],
    )


async def purge_backups(db: AsyncSession, now: datetime | None = None) -> int:
    """Hapus backup config OLT lebih tua dari 90 hari, KECUALI backup terbaru
    tiap OLT (backup terbaru tidak pernah dihapus, berapapun umurnya)."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=BACKUP_RETENTION_DAYS)
    b2 = OltConfigBackup.__table__.alias("b2")
    newer_exists = exists().where(
        and_(
            b2.c.olt_id == OltConfigBackup.olt_id,
            or_(
                b2.c.taken_at > OltConfigBackup.taken_at,
                and_(b2.c.taken_at == OltConfigBackup.taken_at,
                     b2.c.id > OltConfigBackup.id),
            ),
        )
    )
    return await _delete_batched(
        db, OltConfigBackup,
        [OltConfigBackup.taken_at < cutoff, ~newer_exists],
    )


async def purge_all(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Jalankan ketiga purge + catat satu baris ringkasan di activity log.
    Urutan penting: log dipurge dulu, ringkasan ditulis terakhir (created_at =
    sekarang) sehingga ringkasan tidak ikut terhapus. Commit ringkasan di sini;
    purge batch sudah commit per batch di jalurnya masing-masing."""
    purged = {
        "activity_logs": await purge_activity_logs(db, now),
        "jobs": await purge_jobs(db, now),
        "backups": await purge_backups(db, now),
    }
    await activity_log_repo.log_activity(
        db, action="housekeeping.purge", entity_type="housekeeping", success=True,
        after={"purged": purged, "total": sum(purged.values())},
    )
    await db.commit()
    return purged
