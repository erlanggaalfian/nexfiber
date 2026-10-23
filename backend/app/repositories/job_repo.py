"""Pure DB access for the jobs table — no business logic (PRD repository convention). The
SKIP LOCKED claim query is the core of decision 4.5.A: a single worker (today) uses it so
the same code keeps working unchanged if a second worker is ever added.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


async def claim_next(db: AsyncSession, worker_name: str) -> Job | None:
    """Lock and claim the single highest-priority runnable job, or None if none is ready.
    Caller owns the transaction: commit to keep the claim, rollback to release the lock.
    """
    stmt = (
        select(Job)
        .where(Job.status == "pending", Job.run_after <= datetime.now(UTC))
        .order_by(Job.priority, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.locked_at = datetime.now(UTC)
    job.locked_by = worker_name
    job.started_at = datetime.now(UTC)
    await db.flush()
    return job

async def mark_success(db: AsyncSession, job: Job, result: dict) -> None:
    now = datetime.now(UTC)
    job.status = "success"
    job.result = result
    job.finished_at = now
    job.duration_ms = _duration_ms(job.started_at, now)
    await db.commit()

async def mark_failed(db: AsyncSession, job: Job, error_message: str, error_code: str | None = None) -> None:
    """Exponential backoff (PRD 4.5.A: retry/backoff written by hand). Gives up and marks
    the job permanently failed once max_attempts is reached.
    """
    now = datetime.now(UTC)
    job.error_message = error_message[:1000]
    job.error_code = error_code
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = now
        job.duration_ms = _duration_ms(job.started_at, now)
    else:
        job.status = "pending"
        job.run_after = now + timedelta(seconds=30 * (2 ** (job.attempts - 1)))
        job.locked_at = None
        job.locked_by = None
    await db.commit()

async def release_stale_locks(db: AsyncSession, older_than: timedelta) -> int:
    """Safety net for jobs whose worker died mid-run (PRD 4.5.A "timeout job gantung"):
    requeue anything still 'running' with a locked_at older than the given threshold.
    """
    cutoff = datetime.now(UTC) - older_than
    stmt = (
        update(Job)
        .where(Job.status == "running", Job.locked_at < cutoff)
        .values(status="pending", locked_at=None, locked_by=None)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0

def _duration_ms(started_at: datetime | None, finished_at: datetime) -> int | None:
    if started_at is None:
        return None
    return int((finished_at - started_at).total_seconds() * 1000)
