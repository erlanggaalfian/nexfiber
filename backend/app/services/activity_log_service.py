"""Logs — PRD 3.4.15. Read-only; tidak ada aksi hapus (retensi otomatis)."""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import scope_olt_ids
from app.models.user import User
from app.repositories import activity_log_repo
from app.schemas.activity_log import LogCategory, LogPage, LogRow, category_of


def _row(log, username, olt_name, onu_serial) -> LogRow:
    return LogRow(
        id=log.id, created_at=log.created_at, username=username, action=log.action,
        category=category_of(log.action), olt_id=log.olt_id, olt_name=olt_name,
        onu_id=log.onu_id, onu_serial=onu_serial, entity_type=log.entity_type,
        entity_id=log.entity_id, success=log.success,
        raw_command=log.raw_command, raw_output=log.raw_output,
    )


async def search_logs(db: AsyncSession, user: User, *, q: str | None, olt_id: int | None,
                      user_id: int | None, category: LogCategory | None,
                      since: datetime | None, until: datetime | None,
                      page: int, size: int) -> LogPage:
    rows, total = await activity_log_repo.search(
        db, scope_olt_ids(user), q=q, olt_id=olt_id, user_id=user_id,
        category=category, since=since, until=until, page=page, size=size,
        viewer_id=user.id,
    )
    return LogPage(items=[_row(*r) for r in rows], total=total, page=page, size=size)
