"""Pure queries for olts / pon_ports (PRD repository convention: no business rules)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.olt import Olt, PonPort
from app.models.onu import Onu


async def get_active(db: AsyncSession, olt_id: int) -> Olt | None:
    olt = await db.get(Olt, olt_id)
    return olt if olt and olt.deleted_at is None else None

async def list_active(db: AsyncSession) -> list[Olt]:
    stmt = select(Olt).where(Olt.deleted_at.is_(None)).order_by(Olt.name)
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

async def busiest_pon_ports(db: AsyncSession, limit: int) -> list[tuple[PonPort, Olt, int]]:
    count = _onu_count().label("used")
    stmt = (
        select(PonPort, Olt, count)
        .join(Olt, Olt.id == PonPort.olt_id)
        .where(Olt.deleted_at.is_(None))
        .order_by(count.desc())
        .limit(limit)
    )
    return [(pon, olt, n) for pon, olt, n in await db.execute(stmt)]

async def count_by_status(db: AsyncSession) -> dict[str, int]:
    stmt = (
        select(Olt.status, func.count())
        .where(Olt.deleted_at.is_(None), Olt.is_active.is_(True))
        .group_by(Olt.status)
    )
    return {status: n for status, n in await db.execute(stmt)}

async def last_sync_at(db: AsyncSession):
    return await db.scalar(select(func.max(Olt.last_sync_at)).where(Olt.deleted_at.is_(None)))
