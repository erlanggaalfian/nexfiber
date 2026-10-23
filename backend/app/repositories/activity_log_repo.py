"""Insert-only helper for activity_logs. raw_command/raw_output are mandatory for every
OLT write (PRD 4.3/4.6) — this is the one place that enforces that at the code level.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog


async def log_activity(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    success: bool,
    entity_id: str | None = None,
    user_id: int | None = None,
    job_id: int | None = None,
    olt_id: int | None = None,
    onu_id: int | None = None,
    raw_command: str | None = None,
    raw_output: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        ActivityLog(
            created_at=datetime.now(UTC),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            success=success,
            user_id=user_id,
            job_id=job_id,
            olt_id=olt_id,
            onu_id=onu_id,
            raw_command=raw_command,
            raw_output=raw_output,
            before=before,
            after=after,
        )
    )
    await db.flush()
