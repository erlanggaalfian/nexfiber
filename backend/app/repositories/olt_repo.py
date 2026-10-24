"""Pure queries for olts / pon_ports (PRD repository convention: no business rules)."""

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.rbac import Scope, scoped
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.user import User


async def get_active(db: AsyncSession, olt_id: int, scope: Scope) -> Olt | None:
    stmt = scoped(select(Olt).where(Olt.id == olt_id, Olt.deleted_at.is_(None)), Olt.id, scope)
    return await db.scalar(stmt)

async def list_active(db: AsyncSession, scope: Scope) -> list[Olt]:
    stmt = scoped(select(Olt).where(Olt.deleted_at.is_(None)).order_by(Olt.name), Olt.id, scope)
    return list((await db.execute(stmt)).scalars().all())

def _olt_onu_count():
    return (
        select(func.count(Onu.id))
        .join(PonPort, Onu.pon_port_id == PonPort.id)
        .where(PonPort.olt_id == Olt.id, Onu.deleted_at.is_(None))
        .scalar_subquery()
    )

def _olt_onu_online_count():
    return (
        select(func.count(Onu.id))
        .join(PonPort, Onu.pon_port_id == PonPort.id)
        .where(PonPort.olt_id == Olt.id, Onu.deleted_at.is_(None), Onu.status == "online")
        .scalar_subquery()
    )

async def list_rows(db: AsyncSession, scope: Scope, search: str | None = None):
    """Rows for OLT Management (PRD 3.4.8) + Dashboard baris 3 (PRD 3.4.2): OLT + owner
    name + jumlah ONU total/online + kesehatan (cpu/ram/suhu), satu query dipakai dua halaman."""
    owner = aliased(User)
    stmt = (
        select(Olt, owner.full_name, _olt_onu_count(), _olt_onu_online_count())
        .join(owner, Olt.owner_id == owner.id)
        .where(Olt.deleted_at.is_(None))
        .order_by(Olt.name)
    )
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Olt.name.ilike(like), cast(Olt.host, String).ilike(like), Olt.model.ilike(like))
        )
    return [tuple(row) for row in await db.execute(scoped(stmt, Olt.id, scope))]

async def count_onus(db: AsyncSession, olt_id: int) -> int:
    stmt = (
        select(func.count(Onu.id))
        .join(PonPort, Onu.pon_port_id == PonPort.id)
        .where(PonPort.olt_id == olt_id, Onu.deleted_at.is_(None))
    )
    return await db.scalar(stmt) or 0

async def soft_delete_onus(db: AsyncSession, olt_id: int, when) -> int:
    """ONU ikut soft-delete bersama OLT-nya; perangkat tidak disentuh (PRD 3.4.8)."""
    pon_ids = select(PonPort.id).where(PonPort.olt_id == olt_id)
    result = await db.execute(
        update(Onu)
        .where(Onu.pon_port_id.in_(pon_ids), Onu.deleted_at.is_(None))
        .values(deleted_at=when)
    )
    return result.rowcount or 0

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

async def owner_name(db: AsyncSession, olt: Olt) -> str:
    return await db.scalar(select(User.full_name).where(User.id == olt.owner_id)) or "—"

async def onu_count_by_status(db: AsyncSession, olt_id: int) -> dict[str, int]:
    """Ringkasan status ONU satu OLT untuk header Detail OLT (PRD 3.4.7)."""
    stmt = (
        select(Onu.status, func.count())
        .join(PonPort, Onu.pon_port_id == PonPort.id)
        .where(PonPort.olt_id == olt_id, Onu.deleted_at.is_(None))
        .group_by(Onu.status)
    )
    return {status: n for status, n in await db.execute(stmt)}

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
