"""Zone / ONU type / Splitter CRUD (PRD 3.4.10–3.4.11). No OLT contact, so no jobs here.

Scope rules, enforced per endpoint via the service:
  * zones + splitters: owner-scoped (`rbac.owner_of`), Superadmin sees everything;
  * onu_types: global catalog, written by Superadmin only, read by everyone.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.rbac import SUPERADMIN, owner_of
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.onu_preset import OnuPreset
from app.models.onu_type import OnuType
from app.models.splitter import Splitter
from app.models.user import User
from app.models.zone import Zone
from app.repositories import master_data_repo as repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.master_data import (
    OnuPresetCreate,
    OnuPresetOut,
    OnuTypeCreate,
    OnuTypeOut,
    OnuTypeUpdate,
    SplitterCreate,
    SplitterDetail,
    SplitterOnu,
    SplitterOut,
    SplitterUpdate,
    ZoneCreate,
    ZoneOut,
    ZoneUpdate,
)

RATIO_CAPACITY = {"1:2": 2, "1:4": 4, "1:8": 8, "1:16": 16, "1:32": 32, "1:64": 64}


def _writer_owner(user: User) -> int:
    """Owner an Admin/Superadmin writes as. Users never reach here (router gates the role)."""
    return user.id if user.role == SUPERADMIN else (owner_of(user) or user.id)


async def _save(db: AsyncSession, obj, *, action: str, entity: str, user: User,
                after: dict | None = None):
    db.add(obj)
    await db.flush()
    await log_activity(db, action=action, entity_type=entity, entity_id=str(obj.id),
                       success=True, user_id=user.id, after=after)
    await db.commit()
    await db.refresh(obj)
    return obj


def _apply(obj, values: dict) -> None:
    for field, value in values.items():
        setattr(obj, field, value)


# --- zones -------------------------------------------------------------------

def _zone_out(zone: Zone, splitters: int, onus: int) -> ZoneOut:
    return ZoneOut(
        id=zone.id, owner_id=zone.owner_id, name=zone.name, external_id=zone.external_id,
        latitude=zone.latitude, longitude=zone.longitude,
        splitter_count=splitters, onu_count=onus,
    )


async def list_zones(db: AsyncSession, user: User, q: str | None) -> list[ZoneOut]:
    rows = await repo.list_zones(db, owner_of(user), q)
    return [_zone_out(*r) for r in rows]


async def get_zone(db: AsyncSession, zone_id: int, user: User) -> ZoneOut:
    row = await repo.get_zone_row(db, zone_id, owner_of(user))
    if row is None:
        raise NotFoundError(f"Zone {zone_id} tidak ditemukan")
    return _zone_out(*row)


async def _zone_for_write(db: AsyncSession, zone_id: int, user: User) -> Zone:
    zone = await db.get(Zone, zone_id)
    owner = owner_of(user)
    if zone is None or (owner is not None and zone.owner_id != owner):
        raise NotFoundError(f"Zone {zone_id} tidak ditemukan")
    return zone


async def create_zone(db: AsyncSession, body: ZoneCreate, user: User) -> ZoneOut:
    owner_id = _writer_owner(user)
    if await repo.zone_name_taken(db, owner_id, body.name, None):
        raise ConflictError(f"Zone '{body.name}' sudah ada")
    zone = Zone(owner_id=owner_id, **body.model_dump())
    await _save(db, zone, action="zone.create", entity="zone", user=user,
                after=body.model_dump(mode="json"))
    return await get_zone(db, zone.id, user)


async def update_zone(db: AsyncSession, zone_id: int, body: ZoneUpdate, user: User) -> ZoneOut:
    zone = await _zone_for_write(db, zone_id, user)
    values = body.model_dump(exclude_unset=True)
    name = values.get("name")
    if name and await repo.zone_name_taken(db, zone.owner_id, name, zone.id):
        raise ConflictError(f"Zone '{name}' sudah ada")
    _apply(zone, values)
    await _save(db, zone, action="zone.update", entity="zone", user=user,
                after=body.model_dump(exclude_unset=True, mode="json"))
    return await get_zone(db, zone.id, user)


async def delete_zone(db: AsyncSession, zone_id: int, user: User) -> None:
    zone = await _zone_for_write(db, zone_id, user)
    used = (await repo.count_rows(db, Splitter, Splitter.zone_id == zone_id)
            or await repo.count_rows(db, OnuPreset, OnuPreset.zone_id == zone_id)
            or await repo.count_onus(db, Onu.zone_id == zone_id))
    if used:
        raise ConflictError("Zone masih dipakai splitter/ONU/preset, pindahkan dulu")
    await db.delete(zone)
    await log_activity(db, action="zone.delete", entity_type="zone", entity_id=str(zone.id),
                       success=True, user_id=user.id)
    await db.commit()


# --- onu types ---------------------------------------------------------------

def _onu_type_out(t: OnuType, onus: int) -> OnuTypeOut:
    return OnuTypeOut(**{f: getattr(t, f) for f in OnuTypeOut.model_fields if f != "onu_count"},
                      onu_count=onus)


async def list_onu_types(db: AsyncSession, q: str | None, active_only: bool) -> list[OnuTypeOut]:
    return [_onu_type_out(*r) for r in await repo.list_onu_types(db, q, active_only)]


async def get_onu_type(db: AsyncSession, type_id: int) -> OnuTypeOut:
    row = await repo.get_onu_type_row(db, type_id)
    if row is None:
        raise NotFoundError(f"Tipe ONU {type_id} tidak ditemukan")
    return _onu_type_out(*row)


async def create_onu_type(db: AsyncSession, body: OnuTypeCreate, user: User) -> OnuTypeOut:
    if await repo.onu_type_name_taken(db, body.name, None):
        raise ConflictError(f"Tipe ONU '{body.name}' sudah ada")
    onu_type = OnuType(**body.model_dump())
    await _save(db, onu_type, action="onu_type.create", entity="onu_type", user=user,
                after=body.model_dump(mode="json"))
    return await get_onu_type(db, onu_type.id)


async def update_onu_type(db: AsyncSession, type_id: int, body: OnuTypeUpdate,
                          user: User) -> OnuTypeOut:
    onu_type = await db.get(OnuType, type_id)
    if onu_type is None:
        raise NotFoundError(f"Tipe ONU {type_id} tidak ditemukan")
    values = body.model_dump(exclude_unset=True)
    name = values.get("name")
    if name and await repo.onu_type_name_taken(db, name, type_id):
        raise ConflictError(f"Tipe ONU '{name}' sudah ada")
    _apply(onu_type, values)
    await _save(db, onu_type, action="onu_type.update", entity="onu_type", user=user,
                after=body.model_dump(exclude_unset=True, mode="json"))
    return await get_onu_type(db, type_id)


async def delete_onu_type(db: AsyncSession, type_id: int, user: User) -> None:
    onu_type = await db.get(OnuType, type_id)
    if onu_type is None:
        raise NotFoundError(f"Tipe ONU {type_id} tidak ditemukan")
    if await repo.count_onus(db, Onu.onu_type_id == type_id):
        raise ConflictError("Tipe ONU masih dipakai ONU, tidak bisa dihapus")
    await db.delete(onu_type)
    await log_activity(db, action="onu_type.delete", entity_type="onu_type",
                       entity_id=str(type_id), success=True, user_id=user.id)
    await db.commit()


# --- splitters ---------------------------------------------------------------

def _splitter_out(s: Splitter, zone_name: str | None, parent_name: str | None,
                  onus: int) -> SplitterOut:
    fields = {f: getattr(s, f) for f in SplitterOut.model_fields
              if f not in {"zone_name", "parent_name", "onu_count"}}
    return SplitterOut(**fields, zone_name=zone_name, parent_name=parent_name, onu_count=onus)


async def list_splitters(db: AsyncSession, user: User, q: str | None,
                         zone_id: int | None) -> list[SplitterOut]:
    rows = await repo.list_splitters(db, owner_of(user), q, zone_id)
    return [_splitter_out(*r) for r in rows]


async def get_splitter(db: AsyncSession, splitter_id: int, user: User) -> SplitterDetail:
    row = await repo.get_splitter_row(db, splitter_id, owner_of(user))
    if row is None:
        raise NotFoundError(f"Splitter {splitter_id} tidak ditemukan")
    onus = await repo.splitter_onus(db, splitter_id)
    return SplitterDetail(
        **_splitter_out(*row).model_dump(),
        onus=[SplitterOnu(id=o.id, serial_number=o.serial_number, name=o.name,
                          customer_name=o.customer_name, splitter_port=o.splitter_port)
              for o in onus],
    )


async def _check_refs(db: AsyncSession, values: dict, user: User, splitter_id: int | None) -> None:
    """Zone must be in scope; parent/OLT/PON must exist and stay consistent."""
    if values.get("zone_id") is not None:
        await _zone_for_write(db, values["zone_id"], user)
    parent_id = values.get("parent_id")
    if parent_id is not None:
        if parent_id == splitter_id:
            raise ValidationAppError("Splitter tidak bisa jadi induk dirinya sendiri")
        parent = await repo.get_splitter_row(db, parent_id, owner_of(user))
        if parent is None:
            raise NotFoundError(f"Splitter induk {parent_id} tidak ditemukan")
    if values.get("olt_id") is not None and await db.get(Olt, values["olt_id"]) is None:
        raise NotFoundError(f"OLT {values['olt_id']} tidak ditemukan")
    pon_port_id = values.get("pon_port_id")
    if pon_port_id is not None:
        pon = await db.get(PonPort, pon_port_id)
        if pon is None:
            raise NotFoundError(f"PON port {pon_port_id} tidak ditemukan")
        if values.get("olt_id") and pon.olt_id != values["olt_id"]:
            raise ValidationAppError("PON port bukan milik OLT yang dipilih")


async def create_splitter(db: AsyncSession, body: SplitterCreate, user: User) -> SplitterDetail:
    values = body.model_dump()
    await _check_refs(db, values, user, None)
    splitter = Splitter(**values, capacity=RATIO_CAPACITY[body.ratio])
    await _save(db, splitter, action="splitter.create", entity="splitter", user=user,
                after=body.model_dump(mode="json"))
    return await get_splitter(db, splitter.id, user)


async def update_splitter(db: AsyncSession, splitter_id: int, body: SplitterUpdate,
                          user: User) -> SplitterDetail:
    row = await repo.get_splitter_row(db, splitter_id, owner_of(user))
    if row is None:
        raise NotFoundError(f"Splitter {splitter_id} tidak ditemukan")
    splitter: Splitter = row[0]
    values = body.model_dump(exclude_unset=True)
    await _check_refs(db, values, user, splitter_id)
    if values.get("ratio"):
        values["capacity"] = RATIO_CAPACITY[values["ratio"]]
    _apply(splitter, values)
    await _save(db, splitter, action="splitter.update", entity="splitter", user=user,
                after=body.model_dump(exclude_unset=True, mode="json"))
    return await get_splitter(db, splitter_id, user)


async def delete_splitter(db: AsyncSession, splitter_id: int, user: User) -> None:
    row = await repo.get_splitter_row(db, splitter_id, owner_of(user))
    if row is None:
        raise NotFoundError(f"Splitter {splitter_id} tidak ditemukan")
    if await repo.count_onus(db, Onu.splitter_id == splitter_id):
        raise ConflictError("Splitter masih dipakai ONU, tidak bisa dihapus")
    if await repo.count_children(db, splitter_id):
        raise ConflictError("Splitter masih punya splitter turunan, hapus turunannya dulu")
    await db.delete(row[0])
    await log_activity(db, action="splitter.delete", entity_type="splitter",
                       entity_id=str(splitter_id), success=True, user_id=user.id)
    await db.commit()


# --- auto-provisioning master data dari isi perangkat ------------------------
# Dipakai onboarding_sync saat OLT BARU di-onboarding: nama zone/ODP yang sudah tertulis
# di `description` ONU dipetakan ke baris master. Pencocokan case-insensitive supaya
# "Ngadirojo" dan "ngadirojo" tidak jadi dua baris.
# CATATAN IZIN: pembuatan baris master baru di sini otomatis — user belum menjawab izin
# eksplisit, jadi pemanggil WAJIB membatasinya ke OLT yang baru onboarding (lihat
# onboarding_sync.sync_onu_metadata) dan `create` bisa dimatikan lewat argumen.


def normalize_master_name(name: str) -> str:
    """Kunci pencocokan nama master: huruf kecil, `_` dianggap spasi, spasi dirapatkan.

    Perangkat menulis nama zone yang SAMA dengan dua gaya (OLT WNG nyata:
    `zone_Kecamatan_Selogiri_...` dan `zone_Kecamatan Selogiri_...`). Tanpa normalisasi
    ini keduanya jadi dua baris Zone terpisah.
    """
    return " ".join(name.replace("_", " ").split()).lower()


async def get_or_create_zone(db: AsyncSession, owner_id: int, name: str,
                             *, create: bool = True) -> Zone | None:
    """Zone milik `owner_id` dengan nama ini; dibuat kalau belum ada dan create=True.

    Idempoten: dipanggil dua kali dengan nama sama tidak pernah membuat baris kedua.
    """
    name = name.strip()
    if not name:
        return None
    key = normalize_master_name(name)
    existing = await db.scalar(
        select(Zone).where(
            Zone.owner_id == owner_id,
            func.lower(func.regexp_replace(Zone.name, r"[_\s]+", " ", "g")) == key,
        )
    )
    if existing is not None or not create:
        return existing
    # Simpan gaya yang bisa dibaca manusia (spasi), bukan `Kecamatan_Selogiri`.
    zone = Zone(owner_id=owner_id, name=" ".join(name.replace("_", " ").split())[:100])
    db.add(zone)
    await db.flush()
    return zone


async def get_or_create_splitter(db: AsyncSession, name: str, *, zone_id: int | None,
                                 olt_id: int | None, create: bool = True) -> Splitter | None:
    """Splitter/ODP bernama ini di zone yang sama; dibuat sebagai tipe `odp` bila perlu.

    Nama ODP di perangkat sudah unik per area (mis. `WNG-01B0213`), jadi kuncinya
    (zone_id, nama ter-normalisasi). `ratio`/`capacity` TIDAK ditebak — perangkat tidak
    melaporkannya, operator mengisi nanti di Settings > Splitter.
    """
    name = name.strip()
    if not name:
        return None
    key = normalize_master_name(name)
    stmt = select(Splitter).where(
        func.lower(func.regexp_replace(Splitter.name, r"[_\s]+", " ", "g")) == key
    )
    stmt = stmt.where(Splitter.zone_id == zone_id) if zone_id is not None \
        else stmt.where(Splitter.zone_id.is_(None))
    existing = await db.scalar(stmt)
    if existing is not None or not create:
        return existing
    splitter = Splitter(name=" ".join(name.replace("_", " ").split())[:100], type="odp",
                        zone_id=zone_id, olt_id=olt_id)
    db.add(splitter)
    await db.flush()
    return splitter


# --- onu presets -------------------------------------------------------------
# "Gunakan preset" + "Simpan sebagai preset" di Form Otorisasi (PRD 3.4.4). Scope ikut
# pola zone/splitter: owner-scoped lewat rbac.owner_of, Superadmin lihat semua.

async def list_presets(db: AsyncSession, user: User) -> list[OnuPresetOut]:
    return [OnuPresetOut.model_validate(p) for p in await repo.list_presets(db, owner_of(user))]


async def create_preset(db: AsyncSession, body: OnuPresetCreate, user: User) -> OnuPresetOut:
    owner_id = _writer_owner(user)
    if await repo.preset_name_taken(db, owner_id, body.name):
        raise ConflictError(f"Preset '{body.name}' sudah ada")
    if await db.get(OnuType, body.onu_type_id) is None:
        raise NotFoundError(f"Tipe ONU {body.onu_type_id} tidak ditemukan")
    if body.zone_id is not None:
        await _zone_for_write(db, body.zone_id, user)
    if body.splitter_id is not None and await repo.get_splitter_row(
        db, body.splitter_id, owner_of(user)
    ) is None:
        raise NotFoundError(f"Splitter {body.splitter_id} tidak ditemukan")
    preset = OnuPreset(owner_id=owner_id, **body.model_dump())
    await _save(db, preset, action="onu_preset.create", entity="onu_preset", user=user,
                after=body.model_dump(mode="json"))
    return OnuPresetOut.model_validate(preset)


async def delete_preset(db: AsyncSession, preset_id: int, user: User) -> None:
    preset = await db.get(OnuPreset, preset_id)
    owner = owner_of(user)
    if preset is None or (owner is not None and preset.owner_id != owner):
        raise NotFoundError(f"Preset {preset_id} tidak ditemukan")
    await db.delete(preset)
    await log_activity(db, action="onu_preset.delete", entity_type="onu_preset",
                       entity_id=str(preset_id), success=True, user_id=user.id)
    await db.commit()
