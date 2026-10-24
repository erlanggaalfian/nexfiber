"""APScheduler -> enqueue periodic jobs per active OLT (PRD 4.4). Runs inside the worker
process. Pileup guard is the DB partial unique index; ConflictError = skip this tick.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.exceptions import ConflictError
from app.models.olt import Olt
from app.services import job_service

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

def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    def add(job_type: str, trigger: str, **when: int) -> None:
        scheduler.add_job(enqueue_for_active_olts, trigger, args=[job_type],
                          max_instances=1, coalesce=True, **when)

    add("sync_onu_status", "interval", minutes=1)
    # DECISIONS "Job & scheduling": optical + kesehatan OLT satu job (sync_olt_metrics),
    # satu koneksi per OLT tiap 15 menit. Jangan tambah job sync_olt_health terpisah.
    add("sync_olt_metrics", "interval", minutes=15)
    add("sync_unconfigured", "interval", minutes=1)
    add("backup_olt_config", "cron", hour=2)  # PRD only says "harian"; 02:00 = quiet hours
    scheduler.start()
    return scheduler
