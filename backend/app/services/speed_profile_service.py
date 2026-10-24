"""Speed Profile CRUD (PRD 3.4.12) + push/read ke OLT lewat job.

Opsi A (TODO Speed Profile pisah Download/Upload): satu baris = satu arah lewat kolom
`direction`. push_to_olt kirim satu profile per job (bukan pasangan UP+DN sekaligus);
sync_from_olt memasangkan tiap <name>_UP / <name>_DN device jadi 2 baris terpisah.

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

# Suffix nama profile di device per arah (dipakai push_to_olt + sync_from_olt).
DEVICE_SUFFIX = {"download": "_DN", "upload": "_UP"}

# Suffix yang DIPAKAI PERANGKAT NYATA dan harus dilepas saat menamai baris master, supaya
# "SMARTOLT-HFA_Lite-UP" + "SMARTOLT-HFA_Lite-DOWN" jadi satu nama profil "SMARTOLT-HFA_Lite"
# di dua arah. Terbaca di OLT WNG (C320, 2026-10-25): arah upload berakhiran `-UP`/`_UP`,
# download `-DOWN`/`_DN`. Profil tanpa suffix (mis. `SMARTOLT-VOIPMNG-10M`, dipakai di dua
# arah sekaligus) dipakai apa adanya — nama tidak dikarang.
DEVICE_NAME_SUFFIXES = {
    "upload": ("-UP", "_UP"),
    "download": ("-DOWN", "_DOWN", "-DN", "_DN"),
}


def strip_device_suffix(device_name: str, direction: str) -> str:
    """`SMARTOLT-HFA_Lite-UP` + upload -> `SMARTOLT-HFA_Lite`. Tanpa suffix: apa adanya."""
    for suffix in DEVICE_NAME_SUFFIXES[direction]:
        if device_name.upper().endswith(suffix):
            return device_name[: -len(suffix)]
    return device_name


def _row(profile: SpeedProfile, olt_name: str | None, vlan: Vlan | None,
         onu_count: int) -> SpeedProfileRow:
    return SpeedProfileRow(
        id=profile.id, name=profile.name, direction=profile.direction,
        speed_kbps=profile.speed_kbps, olt_id=profile.olt_id, olt_name=olt_name,
        vlan_db_id=profile.vlan_db_id, vlan_id=vlan.vlan_id if vlan else None,
        vlan_name=vlan.name if vlan else None, device_profile_id=profile.device_profile_id,
        description=profile.description, is_active=profile.is_active, onu_count=onu_count,
    )


async def list_profiles(db: AsyncSession, olt_id: int | None, user: User) -> list[SpeedProfileRow]:
    # DRY: filter global-or-scoped sudah ada di onu_repo.list_speed_profiles; di sini butuh
    # kolom tambahan (olt_name, vlan, onu_count) jadi query-nya join sendiri, tapi daftar id
    # yang boleh dilihat tetap diambil dari helper yang sama.
    allowed = {p.id for p in await onu_repo.list_speed_profiles(db, olt_id, scope_olt_ids(user))}
    stmt = (
        select(SpeedProfile, Olt.name, Vlan)
        .outerjoin(Olt, Olt.id == SpeedProfile.olt_id)
        .outerjoin(Vlan, Vlan.id == SpeedProfile.vlan_db_id)
        .where(SpeedProfile.id.in_(allowed))
        .order_by(SpeedProfile.name, SpeedProfile.direction)
    )
    rows = []
    for profile, olt_name, vlan in await db.execute(stmt):
        count_col = Onu.download_speed_profile_id if profile.direction == "download" \
            else Onu.upload_speed_profile_id
        onu_count = await db.scalar(
            select(func.count(Onu.id)).where(count_col == profile.id, Onu.deleted_at.is_(None))
        )
        rows.append(_row(profile, olt_name, vlan, onu_count or 0))
    return rows


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


async def get_or_create_from_device(db: AsyncSession, olt_id: int, device_name: str,
                                    direction: str, kbps: int | None) -> SpeedProfile | None:
    """Baris `speed_profiles` untuk profil yang SUDAH ADA di perangkat.

    Kunci = (olt_id, lower(device_profile_id)): nama device-nya yang unik, bukan nama
    tampilan. Idempoten; `speed_kbps` hanya diisi sekali supaya nilai yang diubah operator
    tidak ditimpa tiap sinkron. kbps None = perangkat tidak melaporkannya -> tidak dibuat
    (kolom `speed_kbps` NOT NULL, dan angkanya tidak boleh dikarang).
    """
    device_name = device_name.strip()
    if not device_name or direction not in DEVICE_NAME_SUFFIXES:
        return None
    # `sync_speed_profiles` (jalur "Baca dari OLT") menyimpan device_profile_id dengan
    # DEVICE_SUFFIX ditambahkan, jadi profil `SMARTOLT-100M-DOWN` di perangkat tersimpan
    # sebagai `SMARTOLT-100M-DOWN_DN`. Cocokkan KEDUA bentuk, kalau tidak baris master
    # yang sama akan terduplikat tiap sinkron.
    candidates = {device_name.lower(), (device_name + DEVICE_SUFFIX[direction]).lower()}
    existing = await db.scalar(
        select(SpeedProfile).where(
            SpeedProfile.olt_id == olt_id,
            SpeedProfile.direction == direction,
            func.lower(SpeedProfile.device_profile_id).in_(candidates),
        )
    )
    if existing is not None:
        return existing
    if kbps is None:
        return None
    profile = SpeedProfile(
        name=strip_device_suffix(device_name, direction)[:100], direction=direction,
        speed_kbps=kbps, olt_id=olt_id, device_profile_id=device_name[:50],
    )
    db.add(profile)
    await db.flush()
    return profile


async def list_one(db: AsyncSession, profile_id: int, user: User) -> SpeedProfileRow:
    rows = [r for r in await list_profiles(db, None, user) if r.id == profile_id]
    if not rows:
        raise NotFoundError(f"Speed profile {profile_id} not found")
    return rows[0]


async def delete_profile(db: AsyncSession, profile_id: int, user: User) -> None:
    profile = await _get(db, profile_id, user)
    col = Onu.download_speed_profile_id if profile.direction == "download" \
        else Onu.upload_speed_profile_id
    in_use = await db.scalar(
        select(Onu.id).where(col == profile.id, Onu.deleted_at.is_(None)).limit(1)
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
    result = await driver.create_traffic_profile(
        profile.name, profile.direction, profile.speed_kbps
    )
    await log_activity(db, action="speed_profile.push", entity_type="speed_profile",
                       entity_id=str(profile.id), success=result.success,
                       user_id=job.created_by, job_id=job.id, olt_id=profile.olt_id,
                       raw_command=result.raw_command, raw_output=result.raw_output)
    if not result.success:
        await db.commit()
        raise CommandRejectedError(result.message or "OLT rejected command")
    # Nama profile di device = yang dipakai saat authorize/modify ONU.
    profile.device_profile_id = f"{profile.name}{DEVICE_SUFFIX[profile.direction]}"
    return {"raw_command": result.raw_command}


def merge_profiles(existing: list[SpeedProfile], device: list) -> list[tuple[str, str, int]]:
    """Ubah tiap <name>_UP / <name>_DN dari device jadi (name, direction, kbps) untuk
    profile per-arah yang belum ada di DB. Pure function supaya bisa diuji tanpa device."""
    known = {(p.name, p.direction) for p in existing}
    rows = []
    for item in device:
        suffix = DEVICE_SUFFIX[item.direction]
        name = item.name.removesuffix(suffix)
        if (name, item.direction) in known or item.kbps is None:
            continue
        rows.append((name, item.direction, item.kbps))
    return rows


async def sync_from_olt(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    device = await driver.list_traffic_profiles()
    existing = list((await db.execute(
        select(SpeedProfile).where(SpeedProfile.olt_id == job.olt_id)
    )).scalars().all())
    added = merge_profiles(existing, device)
    for name, direction, kbps in added:
        db.add(SpeedProfile(name=name, direction=direction, speed_kbps=kbps,
                            olt_id=job.olt_id,
                            device_profile_id=f"{name}{DEVICE_SUFFIX[direction]}"))
    return {"found": len(device), "added": len(added)}
