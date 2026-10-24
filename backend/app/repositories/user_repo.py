"""Pure queries for users (PRD repository convention: no business rules).

Visibility (PRD 3.7 table "User Management"): Superadmin = every user, Admin = only the
Users whose admin_id is itself. User has no access at all (blocked by the role gate).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.rbac import SUPERADMIN
from app.models.olt import Olt
from app.models.user import User

Parent = aliased(User)

Row = tuple[User, str | None, int]


def _olt_count():
    return (
        select(func.count(Olt.id))
        .where(Olt.owner_id == User.id, Olt.deleted_at.is_(None))
        .scalar_subquery()
    )


def _visible(stmt, viewer: User):
    stmt = stmt.where(User.deleted_at.is_(None))
    if viewer.role == SUPERADMIN:
        return stmt
    return stmt.where(User.admin_id == viewer.id)


def _rows():
    return (
        select(User, Parent.username, _olt_count())
        .outerjoin(Parent, Parent.id == User.admin_id)
    )


async def list_visible(db: AsyncSession, viewer: User, role: str | None) -> list[Row]:
    stmt = _visible(_rows(), viewer).order_by(User.username)
    if role:
        stmt = stmt.where(User.role == role)
    return [(u, parent, n) for u, parent, n in await db.execute(stmt)]


async def get_visible(db: AsyncSession, user_id: int, viewer: User) -> Row | None:
    stmt = _visible(_rows().where(User.id == user_id), viewer)
    return (await db.execute(stmt)).first()


async def count_owned_olts(db: AsyncSession, owner_id: int) -> int:
    return await db.scalar(
        select(func.count(Olt.id)).where(Olt.owner_id == owner_id, Olt.deleted_at.is_(None))
    )


async def count_active_superadmins(db: AsyncSession) -> int:
    return await db.scalar(
        select(func.count(User.id)).where(
            User.role == SUPERADMIN, User.is_active.is_(True), User.deleted_at.is_(None)
        )
    )
