"""activity_logs: insert helper + read query for Logs page (PRD 3.4.15).
raw_command/raw_output are mandatory for every OLT write (PRD 4.3/4.6) — this is the one
place that enforces that at the code level.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Scope, scoped
from app.models.activity_log import ActivityLog
from app.models.olt import Olt
from app.models.onu import Onu
from app.models.user import User


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


def _apply_filters(stmt, *, q, olt_id, user_id, actions, since, until):
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(ActivityLog.action.ilike(like), ActivityLog.entity_id.ilike(like),
                               User.username.ilike(like), Onu.serial_number.ilike(like)))
    if olt_id:
        stmt = stmt.where(ActivityLog.olt_id == olt_id)
    if user_id:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if actions:
        stmt = stmt.where(ActivityLog.action.in_(actions))
    if since:
        stmt = stmt.where(ActivityLog.created_at >= since)
    if until:
        stmt = stmt.where(ActivityLog.created_at <= until)
    return stmt


def _base():
    return (
        select(ActivityLog, User.username, Olt.name, Onu.serial_number)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .outerjoin(Olt, Olt.id == ActivityLog.olt_id)
        .outerjoin(Onu, Onu.id == ActivityLog.onu_id)
    )


async def search(db: AsyncSession, scope: Scope, *, q: str | None, olt_id: int | None,
                 user_id: int | None, actions: list[str] | None, since: datetime | None,
                 until: datetime | None, page: int, size: int) -> tuple[list, int]:
    filters = dict(q=q, olt_id=olt_id, user_id=user_id, actions=actions, since=since, until=until)
    total = await db.scalar(scoped(_apply_filters(
        select(func.count(ActivityLog.id)).outerjoin(User, User.id == ActivityLog.user_id)
        .outerjoin(Onu, Onu.id == ActivityLog.onu_id), **filters,
    ), ActivityLog.olt_id, scope))
    stmt = (scoped(_apply_filters(_base(), **filters), ActivityLog.olt_id, scope)
            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .offset((page - 1) * size).limit(size))
    return list(await db.execute(stmt)), total or 0
