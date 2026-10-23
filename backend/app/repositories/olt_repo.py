"""Pure queries for olts / pon_ports (PRD repository convention: no business rules)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Scope, scoped
from app.models.olt import Olt, PonPort
from app.models.onu import Onu


async def get_active(db: AsyncSession, olt_id: int, scope: Scope) -> Olt | None:
    stmt = scoped(select(Olt).where(Olt.id == olt_id, Olt.deleted_at.is_(None)), Olt.id, scope)
    return await db.scalar(stmt)

async def list_active(db: AsyncSession, scope: Scope) -> list[Olt]:
    stmt = scoped(select(Olt).where(Olt.deleted_at.is_(None)).order_by(Olt.name), Olt.id, scope)
    return list((await db.execute(stmt)).scalars().all())

def _onu_count():
    return (
        select(func.count(Onu.id))
        .where(Onu.pon_port_id == PonPort.id, Onu.deleted_at.is_(None))
        .scalar_subquery()
    )

async def list_pon_ports(db: AsyncSession, olt_id: int) -> list[tuple[PonPort, int]]:
    stmt = (
        select(PonPort, _onu_count())
        .where(PonPort.olt_id == olt_id)
        .order_by(PonPort.slot, PonPort.port)
    )
    return [(pon, count) for pon, count in await db.execute(stmt)]

async def count_by_status(db: AsyncSession, scope: Scope) -> dict[str, int]:
    stmt = (
        select(Olt.status, func.count())
        .where(Olt.deleted_at.is_(None), Olt.is_active.is_(True))
        .group_by(Olt.status)
    )
    return {status: n for status, n in await db.execute(scoped(stmt, Olt.id, scope))}

async def last_sync_at(db: AsyncSession, scope: Scope):
    stmt = select(func.max(Olt.last_sync_at)).where(Olt.deleted_at.is_(None))
    return await db.scalar(scoped(stmt, Olt.id, scope))
