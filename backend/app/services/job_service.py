"""Job enqueue/status (PRD 4.5.A: callers never know the queue implementation, only call
enqueue()). enqueue() does NOT commit â€” it must ride the caller's transaction so "create ONU
+ enqueue provisioning job" is one atomic commit, per the PRD's core argument for choosing
a DB-table queue over Celery+Redis.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.exceptions import ConflictError, NotFoundError
from app.core.rbac import Scope, scoped
from app.models.job import Job
from app.schemas.job import JobOut


async def enqueue(
    db: AsyncSession,
    job_type: str,
    *,
    olt_id: int | None = None,
    onu_id: int | None = None,
    payload: dict | None = None,
    priority: int = 100,
    created_by: int | None = None,
    max_attempts: int = 3,
) -> Job:
    """Insert a pending job. Does not commit â€” caller's transaction decides.

    For sync_* job types the partial unique index (uq_jobs_sync_pending_per_olt) is the only
    anti-pileup check (PRD 4.4: "scheduler tidak membuat job baru bila job sejenis ... masih
    pending/running") — we don't duplicate that check here, we just surface the resulting
    unique violation as a ConflictError so the scheduler can skip it quietly. Index kedua
    (uq_jobs_active_per_onu) melakukan hal sama untuk job per ONU, jadi dua proses yang
    menekan tombol sama bersamaan tetap menghasilkan tepat satu job.
    """
    job = Job(
        job_type=job_type,
        olt_id=olt_id,
        onu_id=onu_id,
        payload=payload or {},
        priority=priority,
        created_by=created_by,
        max_attempts=max_attempts,
        run_after=datetime.now(UTC),
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Job {job_type} untuk target ini masih pending/running"
        ) from exc
    return job

async def get_job(db: AsyncSession, job_id: int, scope: Scope) -> Job:
    job = await db.scalar(scoped(select(Job).where(Job.id == job_id), Job.olt_id, scope))
    if job is None:
        raise NotFoundError("Job not found")
    return job

async def list_jobs(
    db: AsyncSession,
    scope: Scope,
    *,
    status: str | None = None,
    olt_id: int | None = None,
    onu_id: int | None = None,
    limit: int = 50,
) -> list[Job]:
    stmt = scoped(select(Job).order_by(Job.id.desc()).limit(limit), Job.olt_id, scope)
    if status:
        stmt = stmt.where(Job.status == status)
    if olt_id:
        stmt = stmt.where(Job.olt_id == olt_id)
    if onu_id:
        stmt = stmt.where(Job.onu_id == onu_id)
    return list((await db.execute(stmt)).scalars().all())

async def cancel_job(db: AsyncSession, job_id: int, scope: Scope) -> Job:
    job = await get_job(db, job_id, scope)
    if job.status not in ("pending",):
        raise ConflictError(f"Cannot cancel a job in status '{job.status}'")
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db.commit()
    return job


STREAM_INTERVAL_S = 1.0
# updated_at = now() = transaction START, so a row can commit with a timestamp already behind
# the cursor. Re-read this window each tick and dedupe. Matches the worker's STALE_AFTER:
# a job running longer than that is requeued anyway.
STREAM_OVERLAP = timedelta(minutes=15)

async def _changed_since(since: datetime, scope: Scope) -> list[Job]:
    # Fresh short session per tick: a stream must not hold one transaction open for hours.
    async with SessionLocal() as db:
        stmt = select(Job).where(Job.updated_at > since).order_by(Job.updated_at).limit(500)
        stmt = scoped(stmt, Job.olt_id, scope)
        return list((await db.execute(stmt)).scalars().all())

async def stream_job_events(scope: Scope) -> AsyncIterator[str]:
    """SSE frames for every job whose row changed (PRD 4.5.C). DB polling, no LISTEN/NOTIFY."""
    started = datetime.now(UTC)
    sent: dict[tuple[int, datetime], datetime] = {}
    while True:
        cutoff = datetime.now(UTC) - STREAM_OVERLAP
        new = False
        for job in await _changed_since(max(started, cutoff), scope):
            if (job.id, job.updated_at) in sent:
                continue
            sent[(job.id, job.updated_at)] = job.updated_at
            new = True
            yield f"event: job\ndata: {JobOut.model_validate(job).model_dump_json()}\n\n"
        sent = {k: t for k, t in sent.items() if t > cutoff}
        if not new:
            yield ": ping\n\n"
        await asyncio.sleep(STREAM_INTERVAL_S)
