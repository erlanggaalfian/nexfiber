"""APScheduler -> enqueue periodic jobs per active OLT (PRD 4.4). Runs inside the worker
process. Pileup guard is the DB partial unique index; ConflictError = skip this tick.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.exceptions import ConflictError
from app.models.olt import Olt
from app.services import graph_data_service, job_service, olt_onboarding
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
    """
    async with SessionLocal() as db:
        purged = await graph_data_service.purge_expired(db)
    log.info("purge graph data: %s", purged)

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
    # Rantai onboarding OLT: tahap berikutnya diantre begitu tahap sebelumnya sukses.
    # 5 detik = progres terasa langsung di UI tanpa membebani DB (query 1 tabel settings).
    scheduler.add_job(olt_onboarding.advance_active_chains, "interval", seconds=5,
                      max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler
