"""Speed Profile CRUD (PRD 3.4.12) + push/read ke OLT lewat job.

Job type yang dipakai: `push_speed_profile` ("Simpan ke OLT") dan `sync_speed_profiles`
("Baca dari OLT") — keduanya baru di fase ini, dibuat lewat job_service.enqueue yang sudah
ada (tabel jobs + SKIP LOCKED), bukan antrean baru.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CommandRejectedError, ConflictError, NotFoundError
from app.core.rbac import scope_olt_ids
from app.drivers.base import OltDriver
from app.models.job import Job
from app.models.olt import Olt
from app.models.onu import Onu
from app.models.speed_profile import SpeedProfile
from app.models.user import User
from app.models.vlan import Vlan
from app.repositories import olt_repo, onu_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.speed_profile import SpeedProfileCreate, SpeedProfileRow, SpeedProfileUpdate
from app.services import job_service
from app.services.onu_service import ensure_writes_allowed


def _onu_count_sq():
    return (
        select(func.count(Onu.id))
        .where(Onu.speed_profile_id == SpeedProfile.id, Onu.deleted_at.is_(None))
        .scalar_subquery()
    )


def _row(profile: SpeedProfile, olt_name: str | None, vlan: Vlan | None,
         onu_count: int) -> SpeedProfileRow:
    return SpeedProfileRow(
        id=profile.id, name=profile.name, download_kbps=profile.download_kbps,
        upload_kbps=profile.upload_kbps, olt_id=profile.olt_id, olt_name=olt_name,
        vlan_db_id=profile.vlan_db_id, vlan_id=vlan.vlan_id if vlan else None,
        vlan_name=vlan.name if vlan else None, line_profile_id=profile.line_profile_id,
        srv_profile_id=profile.srv_profile_id, description=profile.description,
        is_active=profile.is_active, onu_count=onu_count,
    )


async def list_profiles(db: AsyncSession, olt_id: int | None, user: User) -> list[SpeedProfileRow]:
    # DRY: filter global-or-scoped sudah ada di onu_repo.list_speed_profiles; di sini butuh
    # kolom tambahan (olt_name, vlan, onu_count) jadi query-nya join sendiri, tapi daftar id
    # yang boleh dilihat tetap diambil dari helper yang sama.
    allowed = {p.id for p in await onu_repo.list_speed_profiles(db, olt_id, scope_olt_ids(user))}
    stmt = (
        select(SpeedProfile, Olt.name, Vlan, _onu_count_sq())
        .outerjoin(Olt, Olt.id == SpeedProfile.olt_id)
        .outerjoin(Vlan, Vlan.id == SpeedProfile.vlan_db_id)
        .where(SpeedProfile.id.in_(allowed))
        .order_by(SpeedProfile.name)
    )
    return [_row(*r) for r in await db.execute(stmt)]


async def _check_refs(db: AsyncSession, olt_id: int | None, vlan_db_id: int | None,
                      user: User) -> None:
    if olt_id is not None:
        if await olt_repo.get_active(db, olt_id, scope_olt_ids(user)) is None:
            raise NotFoundError(f"OLT {olt_id} not found")
    if vlan_db_id is not None and await db.get(Vlan, vlan_db_id) is None:
        raise NotFoundError(f"VLAN {vlan_db_id} not found")


async def _get(db: AsyncSession, profile_id: int, user: User) -> SpeedProfile:
    profile = await db.get(SpeedProfile, profile_id)
    if profile is None:
        raise NotFoundError(f"Speed profile {profile_id} not found")
    if profile.olt_id is not None:
        await _check_refs(db, profile.olt_id, None, user)
    return profile


async def create_profile(db: AsyncSession, body: SpeedProfileCreate,
                         user: User) -> SpeedProfileRow:
    await _check_refs(db, body.olt_id, body.vlan_db_id, user)
    profile = SpeedProfile(**body.model_dump())
    db.add(profile)
    await db.flush()
    await log_activity(db, action="speed_profile.create", entity_type="speed_profile",
                       entity_id=str(profile.id), success=True, user_id=user.id,
                       olt_id=profile.olt_id)
    await db.commit()
    return (await list_one(db, profile.id, user))


async def update_profile(db: AsyncSession, profile_id: int, body: SpeedProfileUpdate,
                         user: User) -> SpeedProfileRow:
    profile = await _get(db, profile_id, user)
    values = body.model_dump(exclude_unset=True)
    await _check_refs(db, values.get("olt_id"), values.get("vlan_db_id"), user)
    for field, value in values.items():
        setattr(profile, field, value)
    await log_activity(db, action="speed_profile.update", entity_type="speed_profile",
                       entity_id=str(profile.id), success=True, user_id=user.id,
                       olt_id=profile.olt_id, after=values)
    await db.commit()
    return await list_one(db, profile_id, user)


async def list_one(db: AsyncSession, profile_id: int, user: User) -> SpeedProfileRow:
    rows = [r for r in await list_profiles(db, None, user) if r.id == profile_id]
    if not rows:
        raise NotFoundError(f"Speed profile {profile_id} not found")
    return rows[0]


async def delete_profile(db: AsyncSession, profile_id: int, user: User) -> None:
    profile = await _get(db, profile_id, user)
    in_use = await db.scalar(
        select(Onu.id).where(Onu.speed_profile_id == profile.id,
                             Onu.deleted_at.is_(None)).limit(1)
    )
    if in_use is not None:
        raise ConflictError("Speed profile masih dipakai ONU")
    await db.delete(profile)
    await log_activity(db, action="speed_profile.delete", entity_type="speed_profile",
                       entity_id=str(profile_id), success=True, user_id=user.id,
                       olt_id=profile.olt_id)
    await db.commit()


async def enqueue_push(db: AsyncSession, profile_id: int, user: User) -> int:
    """Tombol "Simpan ke OLT" -> job push_speed_profile."""
    ensure_writes_allowed()
    profile = await _get(db, profile_id, user)
    if profile.olt_id is None:
        raise ConflictError("Profile global (semua OLT) tidak bisa dipush ke satu OLT")
    job = await job_service.enqueue(db, "push_speed_profile", olt_id=profile.olt_id,
                                    payload={"speed_profile_id": profile.id},
                                    created_by=user.id)
    await db.commit()
    return job.id


async def enqueue_sync(db: AsyncSession, olt_id: int, user: User) -> int:
    """Tombol "Baca dari OLT" -> job sync_speed_profiles."""
    if await olt_repo.get_active(db, olt_id, scope_olt_ids(user)) is None:
        raise NotFoundError(f"OLT {olt_id} not found")
    job = await job_service.enqueue(db, "sync_speed_profiles", olt_id=olt_id,
                                    created_by=user.id)
    await db.commit()
    return job.id


# --- worker handlers ---------------------------------------------------------

async def push_to_olt(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    profile = await db.get(SpeedProfile, job.payload["speed_profile_id"])
    if profile is None:
        raise NotFoundError(f"Speed profile {job.payload['speed_profile_id']} not found")
    result = await driver.create_traffic_profiles(
        profile.name, profile.download_kbps, profile.upload_kbps
    )
    await log_activity(db, action="speed_profile.push", entity_type="speed_profile",
                       entity_id=str(profile.id), success=result.success,
                       user_id=job.created_by, job_id=job.id, olt_id=profile.olt_id,
                       raw_command=result.raw_command, raw_output=result.raw_output)
    if not result.success:
        await db.commit()
        raise CommandRejectedError(result.message or "OLT rejected command")
    # Nama profile di device = yang dipakai saat authorize/modify ONU.
    profile.srv_profile_id = f"{profile.name}_UP"
    profile.line_profile_id = f"{profile.name}_DN"
    return {"raw_command": result.raw_command}


def merge_profiles(existing: list[SpeedProfile], device: list) -> list[tuple[str, int, int]]:
    """Pasangkan <name>_UP / <name>_DN dari device jadi (name, download, upload) untuk
    profile yang belum ada di DB. Pure function supaya bisa diuji tanpa device."""
    up = {p.name.removesuffix("_UP"): p.kbps for p in device if p.direction == "upload"}
    dn = {p.name.removesuffix("_DN"): p.kbps for p in device if p.direction == "download"}
    known = {p.name for p in existing}
    rows = []
    for name in sorted(up.keys() & dn.keys()):
        if name in known or up[name] is None or dn[name] is None:
            continue
        rows.append((name, dn[name], up[name]))
    return rows


async def sync_from_olt(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    device = await driver.list_traffic_profiles()
    existing = list((await db.execute(
        select(SpeedProfile).where(SpeedProfile.olt_id == job.olt_id)
    )).scalars().all())
    added = merge_profiles(existing, device)
    for name, download, upload in added:
        db.add(SpeedProfile(name=name, download_kbps=download, upload_kbps=upload,
                            olt_id=job.olt_id, srv_profile_id=f"{name}_UP",
                            line_profile_id=f"{name}_DN"))
    return {"found": len(device), "added": len(added)}
