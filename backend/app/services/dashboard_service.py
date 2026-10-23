"""Dashboard numbers (PRD 3.4.2), scoped to the caller's OLTs. Every number is a real query."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import scope_olt_ids
from app.models.user import User
from app.repositories import olt_repo, onu_repo


async def summary(db: AsyncSession, user: User) -> dict:
    scope = scope_olt_ids(user)
    olts = await olt_repo.count_by_status(db, scope)
    return {
        "olt_by_status": olts,
        "onu_by_status": await onu_repo.count_by_status(db, scope),
        "unconfigured": await onu_repo.count_pending(db, scope),
        "last_poll_at": await olt_repo.last_sync_at(db, scope),
    }
