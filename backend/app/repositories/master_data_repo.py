"""Pure queries for zones / onu_types / splitters (PRD repository convention: no business rules).

Owner scope: zones belong to an Admin (`zones.owner_id`), splitters inherit it through their
zone. `rbac.owner_of` is the single source of truth for which owner a user may see.
"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onu import Onu
from app.models.onu_type import OnuType
from app.models.splitter import Splitter
from app.models.zone import Zone


def _onu_count(col) -> Select:
    return (
        select(func.count(Onu.id))
        .where(col, Onu.deleted_at.is_(None))
        .scalar_subquery()
    )


def owned(stmt: Select, owner_id: int | None) -> Select:
    """owner_id None = Superadmin, no restriction (same contract as rbac.scoped)."""
    return stmt if owner_id is None else stmt.where(Zone.owner_id == owner_id)


# --- zones -------------------------------------------------------------------

def _zone_rows() -> Select:
    splitters = (
        select(func.count(Splitter.id)).where(Splitter.zone_id == Zone.id).scalar_subquery()
    )
    return select(Zone, splitters, _onu_count(Onu.zone_id == Zone.id))


async def list_zones(db: AsyncSession, owner_id: int | None, q: str | None) -> list[tuple]:
    stmt = owned(_zone_rows(), owner_id).order_by(Zone.name)
    if q:
        stmt = stmt.where(Zone.name.ilike(f"%{q}%"))
    return list(await db.execute(stmt))


async def get_zone_row(db: AsyncSession, zone_id: int, owner_id: int | None) -> tuple | None:
    stmt = owned(_zone_rows().where(Zone.id == zone_id), owner_id)
    return (await db.execute(stmt)).first()


async def zone_name_taken(db: AsyncSession, owner_id: int, name: str, skip_id: int | None) -> bool:
    stmt = select(Zone.id).where(Zone.owner_id == owner_id, func.lower(Zone.name) == name.lower())
    if skip_id:
        stmt = stmt.where(Zone.id != skip_id)
    return await db.scalar(stmt) is not None


# --- onu types ---------------------------------------------------------------

def _onu_type_rows() -> Select:
    return select(OnuType, _onu_count(Onu.onu_type_id == OnuType.id))


async def list_onu_types(db: AsyncSession, q: str | None, active_only: bool) -> list[tuple]:
    stmt = _onu_type_rows().order_by(OnuType.pon_type, OnuType.name)
    if q:
        stmt = stmt.where(OnuType.name.ilike(f"%{q}%"))
    if active_only:
        stmt = stmt.where(OnuType.is_active.is_(True))
    return list(await db.execute(stmt))


async def get_onu_type_row(db: AsyncSession, type_id: int) -> tuple | None:
    return (await db.execute(_onu_type_rows().where(OnuType.id == type_id))).first()


async def onu_type_name_taken(db: AsyncSession, name: str, skip_id: int | None) -> bool:
    stmt = select(OnuType.id).where(func.lower(OnuType.name) == name.lower())
    if skip_id:
        stmt = stmt.where(OnuType.id != skip_id)
    return await db.scalar(stmt) is not None


# --- splitters ---------------------------------------------------------------

Parent = Splitter.__table__.alias("parent")


def _splitter_rows() -> Select:
    return (
        select(Splitter, Zone.name, Parent.c.name, _onu_count(Onu.splitter_id == Splitter.id))
        .join(Zone, Zone.id == Splitter.zone_id)
        .outerjoin(Parent, Parent.c.id == Splitter.parent_id)
    )


async def list_splitters(db: AsyncSession, owner_id: int | None, q: str | None,
                         zone_id: int | None) -> list[tuple]:
    stmt = owned(_splitter_rows(), owner_id).order_by(Splitter.name)
    if q:
        stmt = stmt.where(Splitter.name.ilike(f"%{q}%"))
    if zone_id:
        stmt = stmt.where(Splitter.zone_id == zone_id)
    return list(await db.execute(stmt))


async def get_splitter_row(db: AsyncSession, splitter_id: int,
                           owner_id: int | None) -> tuple | None:
    stmt = owned(_splitter_rows().where(Splitter.id == splitter_id), owner_id)
    return (await db.execute(stmt)).first()


async def splitter_onus(db: AsyncSession, splitter_id: int) -> list[Onu]:
    stmt = (
        select(Onu)
        .where(Onu.splitter_id == splitter_id, Onu.deleted_at.is_(None))
        .order_by(Onu.splitter_port, Onu.serial_number)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_children(db: AsyncSession, splitter_id: int) -> int:
    return await count_rows(db, Splitter, Splitter.parent_id == splitter_id)


async def count_rows(db: AsyncSession, model, where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(where))


async def count_onus(db: AsyncSession, col) -> int:
    return await db.scalar(select(func.count(Onu.id)).where(col, Onu.deleted_at.is_(None)))
