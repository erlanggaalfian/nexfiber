"""Pure queries for onus / unconfigured_onus / onu logs (PRD repository convention)."""

from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.rbac import Scope, scoped
from app.core.signal import BUCKETS, bucket_filter, rx_bucket
from app.models.activity_log import ActivityLog
from app.models.olt import Olt, PonPort
from app.models.onu import Onu, OnuSignalHistory
from app.models.onu_preset import OnuPreset
from app.models.speed_profile import SpeedProfile
from app.models.splitter import Splitter
from app.models.unconfigured_onu import UnconfiguredOnu
from app.models.user import User
from app.models.vlan import Vlan
from app.models.zone import Zone

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
    DownProfile = aliased(SpeedProfile)
    UpProfile = aliased(SpeedProfile)
    return (
        select(Onu, Olt.name, PonPort.slot, PonPort.port, DownProfile.name, UpProfile.name,
               Vlan.vlan_id, Zone.name, Splitter.name, OnuPreset.name, User.username)
        .join(Olt, Olt.id == Onu.olt_id)
        .join(PonPort, PonPort.id == Onu.pon_port_id)
        .outerjoin(DownProfile, DownProfile.id == Onu.download_speed_profile_id)
        .outerjoin(UpProfile, UpProfile.id == Onu.upload_speed_profile_id)
        .outerjoin(Vlan, Vlan.id == Onu.vlan_id)
        .outerjoin(Zone, Zone.id == Onu.zone_id)
        .outerjoin(Splitter, Splitter.id == Onu.splitter_id)
        .outerjoin(OnuPreset, OnuPreset.id == Onu.preset_id)
        .outerjoin(User, User.id == Onu.registered_by)
        .where(Onu.deleted_at.is_(None))
    )

def _apply_filters(stmt: Select, *, q, olt_id, pon_port_id, state,
                   download_speed_profile_id, upload_speed_profile_id,
                   rx_warn_dbm: float, signal=None, status=None, vlan_id=None, zone_id=None,
                   splitter_id=None, onu_type=None, olt_ids=None, vlan_ids=None,
                   zone_ids=None, splitter_ids=None, download_speed_profile_ids=None,
                   upload_speed_profile_ids=None, onu_types=None) -> Select:
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            Onu.serial_number.ilike(like), Onu.customer_name.ilike(like),
            Onu.customer_id.ilike(like), Onu.mac_address.ilike(like), Onu.name.ilike(like),
            Onu.address.ilike(like), Onu.pppoe_username.ilike(like), Onu.external_id.ilike(like),
        ))
    # Daftar multi-nilai menggantikan nilai tunggal bila diisi (UI Configured
    # mengirim filter berulang); daftar kosong = tidak difilter, bukan "tidak ada".
    if olt_ids:
        stmt = stmt.where(Onu.olt_id.in_(olt_ids))
    elif olt_id:
        stmt = stmt.where(Onu.olt_id == olt_id)
    if pon_port_id:
        stmt = stmt.where(Onu.pon_port_id == pon_port_id)
    if download_speed_profile_ids:
        stmt = stmt.where(Onu.download_speed_profile_id.in_(download_speed_profile_ids))
    elif download_speed_profile_id:
        stmt = stmt.where(Onu.download_speed_profile_id == download_speed_profile_id)
    if upload_speed_profile_ids:
        stmt = stmt.where(Onu.upload_speed_profile_id.in_(upload_speed_profile_ids))
    elif upload_speed_profile_id:
        stmt = stmt.where(Onu.upload_speed_profile_id == upload_speed_profile_id)
    if vlan_ids:
        stmt = stmt.where(Onu.vlan_id.in_(vlan_ids))
    elif vlan_id:
        stmt = stmt.where(Onu.vlan_id == vlan_id)
    if zone_ids:
        stmt = stmt.where(Onu.zone_id.in_(zone_ids))
    elif zone_id:
        stmt = stmt.where(Onu.zone_id == zone_id)
    if splitter_ids:
        stmt = stmt.where(Onu.splitter_id.in_(splitter_ids))
    elif splitter_id:
        stmt = stmt.where(Onu.splitter_id == splitter_id)
    if onu_types:
        stmt = stmt.where(Onu.onu_type.in_(onu_types))
    elif onu_type:
        stmt = stmt.where(Onu.onu_type == onu_type)
    if status:
        stmt = stmt.where(Onu.status.in_(status))
    if signal:
        # DECISIONS.md: satu definisi bucket, dari app.core.signal. Jangan ulangi batas dBm di sini.
        stmt = stmt.where(or_(*(bucket_filter(Onu.rx_power_dbm, b) for b in signal)))
    if state == "online":
        stmt = stmt.where(Onu.status == "online")
    elif state == "down":
        stmt = stmt.where(Onu.status.in_(DOWN_STATUSES))
    elif state == "rx_warn":
        stmt = stmt.where(Onu.rx_power_dbm < rx_warn_dbm)
    elif state == "not_configured":
        stmt = stmt.where(Onu.config_state != "success")
    return stmt

async def search(db: AsyncSession, scope: Scope, *, q, olt_id, pon_port_id, state,
                 download_speed_profile_id, upload_speed_profile_id,
                 rx_warn_dbm: float, sort: str, page: int, size: int, signal=None, status=None,
                 vlan_id=None, zone_id=None, splitter_id=None, onu_type=None,
                 olt_ids=None, vlan_ids=None, zone_ids=None, splitter_ids=None,
                 download_speed_profile_ids=None, upload_speed_profile_ids=None,
                 onu_types=None) -> tuple[list, int]:
    filters = dict(q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
                   download_speed_profile_id=download_speed_profile_id,
                   upload_speed_profile_id=upload_speed_profile_id,
                   rx_warn_dbm=rx_warn_dbm, signal=signal,
                   status=status, vlan_id=vlan_id, zone_id=zone_id, splitter_id=splitter_id,
                   onu_type=onu_type, olt_ids=olt_ids, vlan_ids=vlan_ids, zone_ids=zone_ids,
                   splitter_ids=splitter_ids,
                   download_speed_profile_ids=download_speed_profile_ids,
                   upload_speed_profile_ids=upload_speed_profile_ids, onu_types=onu_types)
    total = await db.scalar(scoped(_apply_filters(
        select(func.count(Onu.id)).where(Onu.deleted_at.is_(None)), **filters
    ), Onu.olt_id, scope))
    column = SORT_COLUMNS[sort.lstrip("-")]
    order = column.desc().nulls_last() if sort.startswith("-") else column.asc().nulls_last()
    stmt = (scoped(_apply_filters(_onu_rows(), **filters), Onu.olt_id, scope)
            .order_by(order, Onu.id))
    if size is not None:
        stmt = stmt.offset((page - 1) * size).limit(size)
    return list(await db.execute(stmt)), total or 0

async def get_row_by_serial(db: AsyncSession, serial: str, scope: Scope):
    stmt = scoped(_onu_rows().where(Onu.serial_number == serial), Onu.olt_id, scope)
    return (await db.execute(stmt)).first()

async def get_serial_by_id(db: AsyncSession, onu_id: int, scope: Scope) -> str | None:
    """Serial dari id internal ONU (kunci URL UI). None kalau tidak ada / di luar scope /
    sudah soft-delete — pemanggil yang memutuskan 404."""
    stmt = scoped(select(Onu.serial_number).where(Onu.id == onu_id, Onu.deleted_at.is_(None)),
                  Onu.olt_id, scope)
    return await db.scalar(stmt)

async def get_active(db: AsyncSession, onu_id: int) -> Onu | None:
    onu = await db.get(Onu, onu_id)
    return onu if onu and onu.deleted_at is None else None

async def exists_serial(db: AsyncSession, olt_id: int, serial: str,
                        exclude_id: int | None = None) -> bool:
    """Serial sudah dipakai OLT ini? exclude_id = baris yang sedang diproses sendiri
    (authorize ulang / replace): tanpa ini, baris itu memblokir dirinya sendiri."""
    stmt = select(Onu.id).where(Onu.olt_id == olt_id, Onu.serial_number == serial,
                                Onu.deleted_at.is_(None))
    if exclude_id is not None:
        stmt = stmt.where(Onu.id != exclude_id)
    return await db.scalar(stmt) is not None

async def exists_index(db: AsyncSession, pon_port_id: int, onu_index: int,
                       exclude_id: int | None = None) -> bool:
    stmt = select(Onu.id).where(Onu.pon_port_id == pon_port_id, Onu.onu_index == onu_index,
                                Onu.deleted_at.is_(None))
    if exclude_id is not None:
        stmt = stmt.where(Onu.id != exclude_id)
    return await db.scalar(stmt) is not None

async def exists_customer_id(db: AsyncSession, customer_id: str) -> bool:
    stmt = select(Onu.id).where(Onu.customer_id == customer_id, Onu.deleted_at.is_(None))
    return await db.scalar(stmt) is not None


async def exists_customer_id_scoped(db: AsyncSession, customer_id: str,
                                    scope: Scope) -> bool:
    """Varian ber-scope untuk endpoint pengecekan: tanpa ini, siapa pun bisa
    menguji apakah customer_id milik tenant lain sudah dipakai (oracle global).
    Keunikan global customer_id sendiri TIDAK diubah (keputusan produk) — yang
    diubah hanya apa yang terlihat lewat endpoint cek: pemanggil hanya melihat
    baris dalam scope OLT-nya sendiri.
    """
    stmt = scoped(
        select(Onu.id).where(Onu.customer_id == customer_id, Onu.deleted_at.is_(None)),
        Onu.olt_id, scope)
    return await db.scalar(stmt) is not None

async def list_pending(db: AsyncSession, olt_id: int | None, scope: Scope) -> list:
    # Anti-join ke onus: serial yang sudah terdaftar dan SUKSES (atau sedang
    # configuring) tidak boleh ditawarkan untuk diotorisasi — klik itu selalu
    # ditolak exists_serial tanpa jalan keluar. Baris config_state=failed
    # DIKECUALIKAN dari anti-join: pending-nya tetap terlihat, karena baris
    # gagal itu memang butuh tindakan operator (resync/hapus), bukan disembunyikan
    # seolah tidak ada. OLT yang sudah soft-delete juga tidak ditampilkan.
    registered = select(Onu.id).where(
        Onu.olt_id == UnconfiguredOnu.olt_id,
        Onu.serial_number == UnconfiguredOnu.serial_number,
        Onu.deleted_at.is_(None),
        Onu.config_state.in_(("success", "configuring")),
    ).exists()
    stmt = (
        select(UnconfiguredOnu, Olt.name, PonPort.slot, PonPort.port)
        .join(Olt, Olt.id == UnconfiguredOnu.olt_id)
        .join(PonPort, PonPort.id == UnconfiguredOnu.pon_port_id)
        .where(~registered, Olt.deleted_at.is_(None))
        .order_by(UnconfiguredOnu.first_seen_at)
    )
    if olt_id:
        stmt = stmt.where(UnconfiguredOnu.olt_id == olt_id)
    return list(await db.execute(scoped(stmt, UnconfiguredOnu.olt_id, scope)))

async def get_pending(db: AsyncSession, olt_id: int, serial: str) -> UnconfiguredOnu | None:
    stmt = select(UnconfiguredOnu).where(UnconfiguredOnu.olt_id == olt_id,
                                         UnconfiguredOnu.serial_number == serial)
    return await db.scalar(stmt)

async def count_pending(db: AsyncSession, scope: Scope) -> int:
    stmt = scoped(select(func.count(UnconfiguredOnu.id)), UnconfiguredOnu.olt_id, scope)
    return await db.scalar(stmt) or 0

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

async def count_by_status(db: AsyncSession, scope: Scope) -> dict[str, int]:
    stmt = select(Onu.status, func.count()).where(Onu.deleted_at.is_(None)).group_by(Onu.status)
    return {status: n for status, n in await db.execute(scoped(stmt, Onu.olt_id, scope))}

async def count_by_signal(db: AsyncSession, scope: Scope) -> dict[str, int]:
    """Baris bucket sinyal Dashboard (PRD 3.4.2) — pakai bucket_filter() dari core.signal,
    jangan tulis ulang batas dBm di sini."""
    counts = {b: 0 for b in BUCKETS}
    stmt = scoped(select(Onu.rx_power_dbm).where(Onu.deleted_at.is_(None)), Onu.olt_id, scope)
    for (rx,) in await db.execute(stmt):
        counts[rx_bucket(rx)] += 1
    return counts

def _global_or_scoped(stmt: Select, col, olt_id: int | None, scope: Scope) -> Select:
    """Rows with olt_id NULL are global; per-OLT rows follow the OLT scope."""
    if olt_id:
        stmt = stmt.where(or_(col == olt_id, col.is_(None)))
    if scope is not None:
        stmt = stmt.where(or_(col.is_(None), col.in_(scope)))
    return stmt

async def list_vlans(db: AsyncSession, olt_id: int | None, scope: Scope) -> list[Vlan]:
    stmt = select(Vlan).where(Vlan.is_active.is_(True)).order_by(Vlan.vlan_id)
    stmt = _global_or_scoped(stmt, Vlan.olt_id, olt_id, scope)
    return list((await db.execute(stmt)).scalars().all())

async def list_speed_profiles(db: AsyncSession, olt_id: int | None,
                              scope: Scope) -> list[SpeedProfile]:
    stmt = select(SpeedProfile).where(SpeedProfile.is_active.is_(True)).order_by(SpeedProfile.name)
    stmt = _global_or_scoped(stmt, SpeedProfile.olt_id, olt_id, scope)
    return list((await db.execute(stmt)).scalars().all())
