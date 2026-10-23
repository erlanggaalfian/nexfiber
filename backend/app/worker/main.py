"""Worker loop (PRD 4.5.A): claim job -> execute -> write result. One process; each job runs
as its own task so a slow/unreachable OLT never blocks another OLT's jobs, while a per-OLT
asyncio.Lock keeps one CLI session per OLT (PRD 4.3).
"""

import asyncio
import logging
import signal
import socket
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.core.db import SessionLocal
from app.core.exceptions import CommandRejectedError, ForbiddenError, NotFoundError
from app.drivers.factory import build_driver
from app.models.job import Job
from app.models.olt import Olt
from app.models.setting import Setting
from app.repositories import job_repo
from app.worker.handlers import HANDLERS, NotImplementedPhase2
from app.worker.schedules import start_scheduler

log = logging.getLogger("nexfiber.worker")

POLL_INTERVAL_S = 1
STALE_CHECK_INTERVAL_S = 60
HEARTBEAT_INTERVAL_S = 30
# Must exceed the longest job incl. time spent waiting on its OLT lock behind other jobs.
STALE_AFTER = timedelta(minutes=15)
WORKER_NAME = f"{socket.gethostname()}:worker"

# Deterministic failures: retrying can't help and, for writes, could double-apply.
PERMANENT_ERRORS = (
    CommandRejectedError, ForbiddenError, NotFoundError, NotImplementedPhase2, KeyError,
)

_olt_locks: defaultdict[int | None, asyncio.Lock] = defaultdict(asyncio.Lock)
# Caps concurrent DB sessions below the engine pool (10+5) so the scheduler/API path keeps
# headroom. Taken after the OLT lock, so jobs queued behind a busy OLT hold no connection.
_slots = asyncio.Semaphore(8)

async def claim_one() -> tuple[int, int | None] | None:
    async with SessionLocal() as db:
        job = await job_repo.claim_next(db, WORKER_NAME)
        await db.commit()
        return (job.id, job.olt_id) if job else None

async def run_job(job_id: int, olt_id: int | None) -> None:
    """Whole body guarded: one bad job/OLT marks that job failed, never kills the worker."""
    async with _olt_locks[olt_id], _slots, SessionLocal() as db:
        job = await db.get(Job, job_id)
        try:
            olt = await db.get(Olt, olt_id) if olt_id else None
            if olt is None:
                raise NotFoundError(f"Job {job_id} has no valid olt_id")
            result = await HANDLERS[job.job_type](db, job, olt, build_driver(olt))
            await job_repo.mark_success(db, job, result)
        except Exception as exc:
            log.warning("job %s (%s) failed: %s", job_id, job.job_type, exc)
            await _fail(db, job_id, exc)

async def _fail(db, job_id: int, exc: Exception) -> None:
    await db.rollback()
    job = await db.get(Job, job_id, populate_existing=True)
    is_sync = job.job_type.startswith("sync_")
    # sync_* never retries: the next scheduled tick is the retry, and anti-pileup holds
    # new ticks back while a retry sits pending.
    if is_sync or isinstance(exc, PERMANENT_ERRORS):
        job.attempts = job.max_attempts
    if job.olt_id and not isinstance(exc, PERMANENT_ERRORS):
        olt = await db.get(Olt, job.olt_id, populate_existing=True)
        olt.status = "unreachable"
        olt.last_error = str(exc)[:500]
    await job_repo.mark_failed(db, job, str(exc) or type(exc).__name__, type(exc).__name__[:50])

async def release_stale() -> None:
    async with SessionLocal() as db:
        released = await job_repo.release_stale_locks(db, STALE_AFTER)
        if released:
            log.warning("requeued %s stale job(s)", released)

async def heartbeat() -> None:
    """Read by GET /api/system/status (PRD 3.4: worker aktif bila < 2 menit)."""
    value = {"at": datetime.now(UTC).isoformat(), "worker": WORKER_NAME}
    stmt = insert(Setting).values(key="worker_heartbeat", value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Setting.key], set_={"value": value, "updated_at": datetime.now(UTC)}
    )
    async with SessionLocal() as db:
        await db.execute(stmt)
        await db.commit()

async def run(stop: asyncio.Event) -> None:
    tasks: set[asyncio.Task] = set()
    loop = asyncio.get_running_loop()
    next_stale_check = 0.0
    next_heartbeat = 0.0
    while not stop.is_set():
        try:
            if loop.time() >= next_stale_check:
                await release_stale()
                next_stale_check = loop.time() + STALE_CHECK_INTERVAL_S
            if loop.time() >= next_heartbeat:
                await heartbeat()
                next_heartbeat = loop.time() + HEARTBEAT_INTERVAL_S
            while (claimed := await claim_one()) is not None:
                task = asyncio.create_task(run_job(*claimed))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except Exception:
            log.exception("worker loop error (DB down?); retrying")
        try:
            await asyncio.wait_for(stop.wait(), POLL_INTERVAL_S)
        except TimeoutError:
            pass
    if tasks:
        log.info("waiting for %s running job(s)", len(tasks))
        await asyncio.gather(*tasks, return_exceptions=True)

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows dev box; Ctrl+C still raises KeyboardInterrupt
            pass
    scheduler = start_scheduler()
    log.info("worker %s started", WORKER_NAME)
    try:
        await run(stop)
    finally:
        scheduler.shutdown(wait=False)
