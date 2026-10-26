"""Worker loop (PRD 4.5.A): claim job -> execute -> write result. Beberapa job jalan
bersamaan (batas dari NEXFIBER_WORKER_CONCURRENCY) sehingga OLT berbeda tidak saling
menunggu, sedangkan SATU OLT tetap satu sesi CLI pada satu waktu — dijaga advisory lock
Postgres per olt_id (PRD 4.3), jadi aman walau worker/proses-nya lebih dari satu.
"""

import asyncio
import logging
import os
import signal
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from app.core.db import SessionLocal, olt_cli_lock
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

# Job yang HANYA pakai SNMP (lihat driver: fetch_onu_status/fetch_optical tidak membuka
# CLI). Job ini tidak perlu kunci CLI, jadi status/optical satu OLT boleh jalan bersamaan
# dengan job CLI OLT lain tanpa ikut mengantre.
SNMP_ONLY_JOBS = frozenset({"sync_onu_status", "sync_onu_optical", "sample_onu_traffic"})
# OLT sedang dipakai sesi CLI lain: bukan error, cuma antre. Coba lagi sebentar lagi.
CLI_BUSY_RETRY = timedelta(seconds=5)

def _concurrency() -> int:
    """Berapa job paralel per proses worker. Dibatasi di bawah pool koneksi DB (10+5)
    supaya API/scheduler selalu kebagian koneksi."""
    try:
        value = int(os.environ.get("NEXFIBER_WORKER_CONCURRENCY", "8"))
    except ValueError:
        value = 8
    return max(1, min(value, 12))

MAX_PARALLEL_JOBS = _concurrency()
_slots = asyncio.Semaphore(MAX_PARALLEL_JOBS)

async def claim_one() -> tuple[int, int | None] | None:
    async with SessionLocal() as db:
        job = await job_repo.claim_next(db, WORKER_NAME)
        await db.commit()
        return (job.id, job.olt_id) if job else None

async def run_job(job_id: int, olt_id: int | None) -> None:
    """Whole body guarded: one bad job/OLT marks that job failed, never kills the worker."""
    async with _slots, SessionLocal() as db:
        job = await db.get(Job, job_id)
        try:
            olt = await db.get(Olt, olt_id) if olt_id else None
            if olt is None:
                raise NotFoundError(f"Job {job_id} has no valid olt_id")
            if job.job_type in SNMP_ONLY_JOBS:
                await _execute(db, job, olt)
                return
            # Kunci lintas proses: satu OLT = satu sesi CLI, OLT lain tidak terpengaruh.
            # try_ (tanpa menunggu) supaya tidak ada deadlock dan slot tidak tertahan;
            # job dikembalikan ke antrean tanpa dihitung gagal.
            async with olt_cli_lock(olt.id) as acquired:
                if not acquired:
                    log.info("OLT %s sedang dipakai sesi CLI lain; job %s diantre ulang",
                             olt.id, job_id)
                    await job_repo.requeue_unpenalized(
                        db, job, CLI_BUSY_RETRY, "Menunggu sesi CLI OLT yang sedang dipakai"
                    )
                    return
                await _execute(db, job, olt)
        except Exception as exc:
            log.warning("job %s (%s) failed: %s", job_id, job.job_type, exc)
            await _fail(db, job_id, exc)

async def _execute(db, job: Job, olt: Olt) -> None:
    result = await HANDLERS[job.job_type](db, job, olt, build_driver(olt))
    await job_repo.mark_success(db, job, result)

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
            # Klaim sebanyak slot yang masih bebas saja. Kalau semua slot penuh, job
            # dibiarkan pending supaya worker lain (atau siklus berikutnya) bisa ambil —
            # bukan ditahan sebagai 'running' tanpa dikerjakan.
            while len(tasks) < MAX_PARALLEL_JOBS and (claimed := await claim_one()) is not None:
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
