"""Pure queries for onus / unconfigured_onus / onu logs (PRD repository convention)."""

from datetime import datetime

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.olt import Olt, PonPort
from app.models.onu import Onu, OnuSignalHistory
from app.models.speed_profile import SpeedProfile
from app.models.unconfigured_onu import UnconfiguredOnu
from app.models.user import User
from app.models.vlan import Vlan

DOWN_STATUSES = ("offline", "los", "dying_gasp", "power_off")
SORT_COLUMNS = {
    "serial": Onu.serial_number,
    "customer": Onu.customer_name,
    "rx": Onu.rx_power_dbm,
    "olt_rx": Onu.olt_rx_power_dbm,
    "status": Onu.status,
    "last_seen": Onu.last_seen_at,
}

def _onu_rows() -> Select:
    return (
        select(Onu, Olt.name, PonPort.slot, PonPort.port, SpeedProfile.name)
        .join(Olt, Olt.id == Onu.olt_id)
        .join(PonPort, PonPort.id == Onu.pon_port_id)
        .outerjoin(SpeedProfile, SpeedProfile.id == Onu.speed_profile_id)
        .where(Onu.deleted_at.is_(None))
    )

def _apply_filters(stmt: Select, *, q, olt_id, pon_port_id, state, speed_profile_id,
                   rx_warn_dbm: float) -> Select:
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            Onu.serial_number.ilike(like), Onu.customer_name.ilike(like),
            Onu.customer_id.ilike(like), Onu.mac_address.ilike(like), Onu.name.ilike(like),
        ))
    if olt_id:
        stmt = stmt.where(Onu.olt_id == olt_id)
    if pon_port_id:
        stmt = stmt.where(Onu.pon_port_id == pon_port_id)
    if speed_profile_id:
        stmt = stmt.where(Onu.speed_profile_id == speed_profile_id)
    if state == "online":
        stmt = stmt.where(Onu.status == "online")
    elif state == "down":
        stmt = stmt.where(Onu.status.in_(DOWN_STATUSES))
    elif state == "rx_warn":
        stmt = stmt.where(Onu.rx_power_dbm < rx_warn_dbm)
    elif state == "not_configured":
        stmt = stmt.where(Onu.config_state != "success")
    return stmt

async def search(db: AsyncSession, *, q, olt_id, pon_port_id, state, speed_profile_id,
                 rx_warn_dbm: float, sort: str, page: int, size: int) -> tuple[list, int]:
    filters = dict(q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
                   speed_profile_id=speed_profile_id, rx_warn_dbm=rx_warn_dbm)
    total = await db.scalar(_apply_filters(
        select(func.count(Onu.id)).where(Onu.deleted_at.is_(None)), **filters
    ))
    column = SORT_COLUMNS[sort.lstrip("-")]
    order = column.desc().nulls_last() if sort.startswith("-") else column.asc().nulls_last()
    stmt = (_apply_filters(_onu_rows(), **filters)
            .order_by(order, Onu.id).offset((page - 1) * size).limit(size))
    return list(await db.execute(stmt)), total or 0

async def get_row_by_serial(db: AsyncSession, serial: str):
    stmt = _onu_rows().where(Onu.serial_number == serial)
    return (await db.execute(stmt)).first()

async def get_active(db: AsyncSession, onu_id: int) -> Onu | None:
    onu = await db.get(Onu, onu_id)
    return onu if onu and onu.deleted_at is None else None

async def exists_serial(db: AsyncSession, olt_id: int, serial: str) -> bool:
    stmt = select(Onu.id).where(Onu.olt_id == olt_id, Onu.serial_number == serial,
                                Onu.deleted_at.is_(None))
    return await db.scalar(stmt) is not None

async def exists_index(db: AsyncSession, pon_port_id: int, onu_index: int) -> bool:
    stmt = select(Onu.id).where(Onu.pon_port_id == pon_port_id, Onu.onu_index == onu_index,
                                Onu.deleted_at.is_(None))
    return await db.scalar(stmt) is not None

async def exists_customer_id(db: AsyncSession, customer_id: str) -> bool:
    stmt = select(Onu.id).where(Onu.customer_id == customer_id, Onu.deleted_at.is_(None))
    return await db.scalar(stmt) is not None

async def list_pending(db: AsyncSession, olt_id: int | None) -> list:
    stmt = (
        select(UnconfiguredOnu, Olt.name, PonPort.slot, PonPort.port)
        .join(Olt, Olt.id == UnconfiguredOnu.olt_id)
        .join(PonPort, PonPort.id == UnconfiguredOnu.pon_port_id)
        .order_by(UnconfiguredOnu.first_seen_at)
    )
    if olt_id:
        stmt = stmt.where(UnconfiguredOnu.olt_id == olt_id)
    return list(await db.execute(stmt))

async def get_pending(db: AsyncSession, olt_id: int, serial: str) -> UnconfiguredOnu | None:
    stmt = select(UnconfiguredOnu).where(UnconfiguredOnu.olt_id == olt_id,
                                         UnconfiguredOnu.serial_number == serial)
    return await db.scalar(stmt)

async def count_pending(db: AsyncSession) -> int:
    return await db.scalar(select(func.count(UnconfiguredOnu.id))) or 0

async def signal_history(db: AsyncSession, onu_id: int, since: datetime) -> list:
    stmt = (
        select(OnuSignalHistory)
        .where(OnuSignalHistory.onu_id == onu_id, OnuSignalHistory.sampled_at >= since)
        .order_by(OnuSignalHistory.sampled_at)
    )
    return list((await db.execute(stmt)).scalars().all())

async def logs(db: AsyncSession, onu_id: int, limit: int) -> list:
    stmt = (
        select(ActivityLog, User.username)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .where(ActivityLog.onu_id == onu_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    return list(await db.execute(stmt))

async def count_by_status(db: AsyncSession) -> dict[str, int]:
    stmt = select(Onu.status, func.count()).where(Onu.deleted_at.is_(None)).group_by(Onu.status)
    return {status: n for status, n in await db.execute(stmt)}

async def count_down_since(db: AsyncSession, before: datetime) -> int:
    stmt = select(func.count(Onu.id)).where(
        Onu.deleted_at.is_(None), Onu.status.in_(("los",)), Onu.last_down_at <= before
    )
    return await db.scalar(stmt) or 0

async def count_registered_since(db: AsyncSession, since: datetime) -> int:
    stmt = select(func.count(Onu.id)).where(Onu.deleted_at.is_(None), Onu.registered_at >= since)
    return await db.scalar(stmt) or 0

async def rx_histogram(db: AsyncSession, warn_dbm: float, crit_dbm: float) -> dict[str, int]:
    bucket = case(
        (Onu.rx_power_dbm < crit_dbm, "bad"),
        (Onu.rx_power_dbm < warn_dbm, "warn"),
        else_="normal",
    )
    stmt = (
        select(bucket, func.count())
        .where(Onu.deleted_at.is_(None), Onu.status == "online", Onu.rx_power_dbm.is_not(None))
        .group_by(bucket)
    )
    return {name: n for name, n in await db.execute(stmt)}


async def list_vlans(db: AsyncSession, olt_id: int | None) -> list[Vlan]:
    stmt = select(Vlan).where(Vlan.is_active.is_(True)).order_by(Vlan.vlan_id)
    if olt_id:
        stmt = stmt.where(or_(Vlan.olt_id == olt_id, Vlan.olt_id.is_(None)))
    return list((await db.execute(stmt)).scalars().all())

async def list_speed_profiles(db: AsyncSession, olt_id: int | None) -> list[SpeedProfile]:
    stmt = select(SpeedProfile).where(SpeedProfile.is_active.is_(True)).order_by(SpeedProfile.name)
    if olt_id:
        stmt = stmt.where(or_(SpeedProfile.olt_id == olt_id, SpeedProfile.olt_id.is_(None)))
    return list((await db.execute(stmt)).scalars().all())
