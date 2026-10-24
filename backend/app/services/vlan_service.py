"""VLAN master data + push ke OLT (DECISIONS: fase ini backend-only, UI penuh nanti di
Detail OLT). API side: tulis baris + enqueue job dalam satu commit. Worker side: kirim
command ke OLT lewat driver, hasil mentah dicatat ke activity_logs.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CommandRejectedError, ConflictError, NotFoundError
from app.core.rbac import scope_olt_ids
from app.drivers.base import OltDriver
from app.drivers.types import DriverResult, debug_log
from app.models.job import Job
from app.models.onu import Onu
from app.models.speed_profile import SpeedProfile
from app.models.user import User
from app.models.vlan import Vlan
from app.repositories import olt_repo, onu_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.vlan import VlanCreate, VlanUpdate
from app.services import job_service
from app.services.onu_service import ensure_writes_allowed


async def list_vlans(db: AsyncSession, olt_id: int | None, user: User) -> list[Vlan]:
    # DRY: query + scope VLAN sudah ada di onu_repo.list_vlans (dipakai dropdown lama).
    return await onu_repo.list_vlans(db, olt_id, scope_olt_ids(user))


async def _get_scoped(db: AsyncSession, vlan_db_id: int, user: User) -> Vlan:
    vlan = await db.get(Vlan, vlan_db_id)
    if vlan is None:
        raise NotFoundError(f"VLAN {vlan_db_id} not found")
    if vlan.olt_id is not None:
        # Di luar cakupan OLT = 404, sama seperti endpoint lain (PRD 3.7).
        await _get_olt(db, vlan.olt_id, user)
    return vlan


async def _get_olt(db: AsyncSession, olt_id: int, user: User):
    olt = await olt_repo.get_active(db, olt_id, scope_olt_ids(user))
    if olt is None:
        raise NotFoundError(f"OLT {olt_id} not found")
    return olt


async def create_vlan(db: AsyncSession, body: VlanCreate, user: User) -> tuple[Vlan, int | None]:
    """Baris VLAN + job push dalam satu commit. olt_id NULL = VLAN global, tanpa job."""
    if body.olt_id is not None:
        await _get_olt(db, body.olt_id, user)
        ensure_writes_allowed()
    vlan = Vlan(**body.model_dump())
    db.add(vlan)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(f"VLAN {body.vlan_id} already exists on this OLT") from exc
    job_id = None
    if vlan.olt_id is not None:
        job = await job_service.enqueue(db, "create_vlan", olt_id=vlan.olt_id,
                                        payload={"vlan_db_id": vlan.id}, created_by=user.id)
        job_id = job.id
    await log_activity(db, action="vlan.create", entity_type="vlan", entity_id=str(vlan.id),
                       success=True, user_id=user.id, olt_id=vlan.olt_id)
    await db.commit()
    await db.refresh(vlan)
    return vlan, job_id


async def update_vlan(db: AsyncSession, vlan_db_id: int, body: VlanUpdate, user: User) -> Vlan:
    """Edit atribut VLAN di DB saja. Nama/deskripsi/gemport tidak mengubah objek VLAN di
    perangkat (ZTE hanya kenal `vlan <id>` + description), jadi tidak ada job di sini —
    kecuali description, yang ikut terkirim pada push berikutnya.
    """
    vlan = await _get_scoped(db, vlan_db_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(vlan, field, value)
    await log_activity(db, action="vlan.update", entity_type="vlan", entity_id=str(vlan.id),
                       success=True, user_id=user.id, olt_id=vlan.olt_id,
                       after=body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    await db.refresh(vlan)
    return vlan


async def set_ports(db: AsyncSession, vlan_db_id: int, ports: dict[str, str],
                    user: User) -> int:
    """Konfigurasi tagged/untagged port uplink: simpan niat lalu enqueue job push.

    Menyentuh perangkat = job (AGENTS.md), tidak pernah panggil driver dari endpoint HTTP.
    """
    vlan = await _get_scoped(db, vlan_db_id, user)
    if vlan.olt_id is None:
        raise ConflictError("VLAN global tidak punya port uplink; pilih VLAN milik OLT")
    ensure_writes_allowed()
    vlan.uplink_ports = ports
    job = await job_service.enqueue(db, "set_vlan_ports", olt_id=vlan.olt_id,
                                    payload={"vlan_db_id": vlan.id, "ports": ports},
                                    created_by=user.id)
    await log_activity(db, action="vlan.set_ports", entity_type="vlan", entity_id=str(vlan.id),
                       success=True, user_id=user.id, olt_id=vlan.olt_id, job_id=job.id,
                       after={"ports": ports})
    await db.commit()
    return job.id


async def delete_vlan(db: AsyncSession, vlan_db_id: int, user: User) -> int | None:
    """Global VLAN: hapus baris langsung. VLAN milik OLT: job hapus di device dulu,
    baris dihapus oleh worker setelah OLT menerima command."""
    vlan = await _get_scoped(db, vlan_db_id, user)
    await _ensure_unused(db, vlan)
    if vlan.olt_id is None:
        await db.delete(vlan)
        await log_activity(db, action="vlan.delete", entity_type="vlan", entity_id=str(vlan_db_id),
                           success=True, user_id=user.id)
        await db.commit()
        return None
    ensure_writes_allowed()
    vlan.is_active = False
    job = await job_service.enqueue(db, "delete_vlan", olt_id=vlan.olt_id,
                                    payload={"vlan_db_id": vlan.id}, created_by=user.id)
    await db.commit()
    return job.id


async def _ensure_unused(db: AsyncSession, vlan: Vlan) -> None:
    used_by_onu = await db.scalar(
        select(Onu.id).where(Onu.vlan_id == vlan.vlan_id, Onu.olt_id == vlan.olt_id,
                             Onu.deleted_at.is_(None)).limit(1)
    )
    if used_by_onu is not None:
        raise ConflictError(f"VLAN {vlan.vlan_id} masih dipakai ONU")
    used_by_profile = await db.scalar(
        select(SpeedProfile.id).where(SpeedProfile.vlan_db_id == vlan.id).limit(1)
    )
    if used_by_profile is not None:
        raise ConflictError(f"VLAN {vlan.vlan_id} masih dipakai speed profile")


# --- worker handlers ---------------------------------------------------------

async def _load(db: AsyncSession, job: Job) -> Vlan:
    vlan = await db.get(Vlan, job.payload["vlan_db_id"])
    if vlan is None:
        raise NotFoundError(f"VLAN {job.payload['vlan_db_id']} not found")
    return vlan


async def _record(db: AsyncSession, job: Job, vlan: Vlan, action: str,
                  result: DriverResult) -> None:
    # Pola sama dengan onu_service._record: log command mentah, commit sebelum raise.
    await log_activity(db, action=action, entity_type="vlan", entity_id=str(vlan.id),
                       success=result.success, user_id=job.created_by, job_id=job.id,
                       olt_id=vlan.olt_id, raw_command=result.raw_command,
                       raw_output=result.raw_output)
    if not result.success:
        # mark_failed tidak menulis job.result, dan worker me-rollback sebelum menandai
        # gagal — jadi jejak CLI harus ikut commit di sini supaya UI tetap bisa
        # menampilkannya saat aksi gagal.
        job.result = {"debug_log": debug_log(result)}
        await db.commit()
        raise CommandRejectedError(result.message or "OLT rejected command")


async def push_create(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    vlan = await _load(db, job)
    result = await driver.create_vlan(vlan.vlan_id, vlan.description or vlan.name)
    await _record(db, job, vlan, "vlan.push_create", result)
    vlan.is_active = True
    return {"debug_log": debug_log(result)}


async def push_delete(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    vlan = await _load(db, job)
    result = await driver.delete_vlan(vlan.vlan_id)
    await _record(db, job, vlan, "vlan.push_delete", result)
    await db.delete(vlan)
    return {"debug_log": debug_log(result)}


async def push_ports(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    vlan = await _load(db, job)
    ports: dict[str, str] = job.payload.get("ports", {})
    result = await driver.set_vlan_ports(vlan.vlan_id, ports)
    await _record(db, job, vlan, "vlan.push_ports", result)
    return {"debug_log": debug_log(result), "ports": len(ports)}
