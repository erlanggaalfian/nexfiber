"""APScheduler -> enqueue periodic jobs per active OLT (PRD 4.4). Runs inside the worker
process. Pileup guard is the DB partial unique index; ConflictError = skip this tick.
"""

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.core.exceptions import ConflictError
from app.models.olt import Olt
from app.repositories import activity_log_repo
from app.services import graph_data_service, housekeeping_service, job_service, olt_onboarding
from app.services import onu_traffic_history_service as traffic_history_service

log = logging.getLogger("nexfiber.schedules")

# Higher number = lower priority: user-triggered jobs (100) jump ahead of periodic sync.
SYNC_PRIORITY = 200

async def enqueue_for_active_olts(job_type: str) -> None:
    async with SessionLocal() as db:
        olt_ids = (await db.execute(
            select(Olt.id).where(Olt.is_active.is_(True), Olt.deleted_at.is_(None))
        )).scalars().all()
    for olt_id in olt_ids:
        async with SessionLocal() as db:
            try:
                await job_service.enqueue(db, job_type, olt_id=olt_id, priority=SYNC_PRIORITY)
                await db.commit()
            except ConflictError:
                await db.rollback()
                log.debug("%s for OLT %s still pending/running; skipped", job_type, olt_id)

async def purge_graph_data() -> None:
    """Retensi data graph (Settings -> Graph Data). Bukan job per OLT: satu tabel global,
    tidak menyentuh perangkat, jadi dijalankan langsung di worker tanpa lewat job queue.
    Purge dicatat ringkas di activity log (jumlah per jenis, tanpa isi baris),
    bukan hanya log.info — sama seperti purge housekeeping di bawah.
    """
    async with SessionLocal() as db:
        purged = await graph_data_service.purge_expired(db)
        await activity_log_repo.log_activity(
            db, action="housekeeping.purge_graph", entity_type="graph_data",
            success=True, after={"purged": purged, "total": sum(purged.values())},
        )
        await db.commit()
    log.info("purge graph data: %s", purged)


async def purge_housekeeping() -> None:
    """Retensi log/jobs/backup (housekeeping_service). Bukan job per OLT dan tidak
    menyentuh perangkat, jadi dijalankan langsung seperti purge graph — setelahnya
    (03:30) supaya tidak berebut lock dengan purge graph 03:00."""
    async with SessionLocal() as db:
        purged = await housekeeping_service.purge_all(db)
    log.info("purge housekeeping: %s", purged)

def _next_month_first(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


async def create_next_activity_log_partition(today: date | None = None) -> None:
    """Buat partisi activity_logs untuk bulan berikutnya, satu bulan sebelumnya.

    Aman tanpa DB nyata untuk dinilai: hanya DDL CREATE TABLE ... PARTITION OF
    (IF NOT EXISTS), tidak memindahkan satu baris pun. Baris yang sudah terlanjur
    masuk partisi DEFAULT tetap di DEFAULT — memindahkannya butuh jendela
    perawatan dan ditulis sebagai langkah manual di docs/db-maintenance.md,
    bukan dilakukan scheduler ini. Bila partisi sudah ada, IF NOT EXISTS
    membuatnya no-op; bila DDL gagal, dicatat dan tidak menggagalkan scheduler.
    """
    start = _next_month_first(today or date.today())
    end = _next_month_first(start)
    name = f"activity_logs_{start.year:04d}_{start.month:02d}"
    sql = (
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF activity_logs "
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
    )
    try:
        async with SessionLocal() as db:
            await db.execute(text(sql))
            await db.commit()
    except Exception:
        log.exception("create_next_activity_log_partition gagal untuk %s", name)
        return
    log.info("activity_logs partition ready: %s", name)


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    def add(job_type: str, trigger: str, **when: int) -> None:
        scheduler.add_job(enqueue_for_active_olts, trigger, args=[job_type],
                          max_instances=1, coalesce=True, **when)

    add("sync_onu_status", "interval", minutes=1)
    # Histori trafik: sampel counter per ONU, 2 bulkwalk per OLT per siklus (bukan per
    # ONU). 5 menit = kompromi yang dipakai aplikasi referensi: cukup halus untuk grafik
    # 24 jam, cukup jarang supaya 30 hari × 1000 ONU tetap wajar di tabel biasa.
    add("sample_onu_traffic", "interval",
        minutes=traffic_history_service.SAMPLE_INTERVAL_MINUTES)
    # DECISIONS "Job & scheduling": optical + kesehatan OLT satu job (sync_olt_metrics),
    # satu koneksi per OLT tiap 15 menit. Jangan tambah job sync_olt_health terpisah.
    add("sync_olt_metrics", "interval", minutes=15)
    add("sync_unconfigured", "interval", minutes=1)
    add("backup_olt_config", "cron", hour=2)  # PRD only says "harian"; 02:00 = quiet hours
    # Purge retensi data graph: 03:00, setelah backup, jauh dari jam sibuk.
    scheduler.add_job(purge_graph_data, "cron", hour=3, max_instances=1, coalesce=True)
    # Purge retensi log/jobs/backup: 03:30, setelah purge graph selesai.
    scheduler.add_job(purge_housekeeping, "cron", hour=3, minute=30,
                      max_instances=1, coalesce=True)
    # Partisi activity_logs bulan berikutnya dibuat tanggal 25 tiap bulan,
    # sebelum bulan itu dimulai — tidak memindahkan data DEFAULT (lihat fungsi).
    scheduler.add_job(create_next_activity_log_partition, "cron", day=25, hour=4,
                      max_instances=1, coalesce=True)
    # Rantai onboarding OLT: tahap berikutnya diantre begitu tahap sebelumnya sukses.
    # 5 detik = progres terasa langsung di UI tanpa membebani DB (query 1 tabel settings).
    scheduler.add_job(olt_onboarding.advance_active_chains, "interval", seconds=5,
                      max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler
