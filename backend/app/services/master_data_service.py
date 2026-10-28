"""Zone / ONU type / Splitter CRUD (PRD 3.4.10–3.4.11). No OLT contact, so no jobs here.

Scope rules, enforced per endpoint via the service:
  * zones + splitters: owner-scoped (`rbac.owner_of`), Superadmin sees everything;
  * onu_types: global catalog, written by Superadmin only, read by everyone.
"""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.profile_name import clean_profile_name
from app.core.rbac import SUPERADMIN, owner_of, scope_olt_ids
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.onu_preset import OnuPreset
from app.models.onu_type import OnuType
from app.models.speed_profile import SpeedProfile
from app.models.splitter import Splitter
from app.models.user import User
from app.models.vlan import Vlan
from app.models.zone import Zone
from app.repositories import master_data_repo as repo, olt_repo
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
    try:
        await db.flush()
    except IntegrityError as exc:
        # Race duplikat / FK yang lolos cek aplikasi harus jadi 409, bukan 500,
        # dan sesi harus di-rollback sebelum dipakai lagi.
        await db.rollback()
        raise ConflictError("Data bertentangan dengan data yang sudah ada (duplikat)") from exc
    await log_activity(db, action=action, entity_type=entity, entity_id=str(obj.id),
                       success=True, user_id=user.id, after=after)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Data bertentangan dengan data yang sudah ada (duplikat)") from exc
    await db.refresh(obj)
    return obj


def _clean_name(name: str | None) -> str | None:
    return name.strip() if name else name


def _clean_zone_name(name: str) -> str:
    """Nama zone dinormalisasi seperti `get_or_create_zone` (spasi dirapatkan,
    `_` dianggap spasi), supaya "Jakarta ", "Jakarta", dan "Kecamatan_Selogiri"
    vs "Kecamatan Selogiri" tidak jadi baris ganda."""
    return " ".join(name.replace("_", " ").split())


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
    name = _clean_zone_name(body.name)
    if await repo.zone_name_taken(db, owner_id, name, None):
        raise ConflictError(f"Zone '{name}' sudah ada")
    zone = Zone(owner_id=owner_id, **body.model_dump(), name=name)
    await _save(db, zone, action="zone.create", entity="zone", user=user,
                after={**body.model_dump(mode="json"), "name": name})
    return await get_zone(db, zone.id, user)


async def update_zone(db: AsyncSession, zone_id: int, body: ZoneUpdate, user: User) -> ZoneOut:
    zone = await _zone_for_write(db, zone_id, user)
    values = body.model_dump(exclude_unset=True)
    name = values.get("name")
    if name:
        values["name"] = _clean_zone_name(name)
        name = values["name"]
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
    try:
        await db.delete(zone)
        await log_activity(db, action="zone.delete", entity_type="zone", entity_id=str(zone.id),
                           success=True, user_id=user.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Zone masih dipakai, tidak bisa dihapus") from exc


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
    name = _clean_name(body.name) or body.name
    if await repo.onu_type_name_taken(db, name, None):
        raise ConflictError(f"Tipe ONU '{name}' sudah ada")
    onu_type = OnuType(**body.model_dump(), name=name)
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
    if name:
        values["name"] = _clean_name(name) or name
        name = values["name"]
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
    if await repo.count_rows(db, OnuPreset, OnuPreset.onu_type_id == type_id):
        raise ConflictError("Tipe ONU masih dipakai preset, tidak bisa dihapus")
    try:
        await db.delete(onu_type)
        await log_activity(db, action="onu_type.delete", entity_type="onu_type",
                           entity_id=str(type_id), success=True, user_id=user.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Tipe ONU masih dipakai, tidak bisa dihapus") from exc


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


async def _check_refs(db: AsyncSession, values: dict, user: User, splitter_id: int | None,
                      current: Splitter | None = None) -> None:
    """Zone must be in scope; parent/OLT/PON must exist and stay consistent.

    Validasi memakai keadaan AKHIR (nilai lama + patch), bukan hanya field yang
    ikut di-patch: PATCH {"pon_port_id": PON milik OLT B} pada splitter OLT A
    dulu lolos karena `olt_id` tidak dikirim, dan PATCH {"olt_id": B} pada
    splitter dengan PON milik OLT A tidak dicek sama sekali. Pengecualian: pada
    update, invariant induk/OLT-PON hanya ditegakkan bila field terkait ikut
    di-patch — supaya baris lama (legacy) yang belum memenuhi invariant tetap
    bisa diedit field lain tanpa dipaksa memperbaiki relasi lama.
    """
    eff = {}
    if current is not None:
        eff = {"zone_id": current.zone_id, "parent_id": current.parent_id,
               "olt_id": current.olt_id, "pon_port_id": current.pon_port_id}
    eff.update(values)
    touched = set(values) if current is not None else None
    if eff.get("zone_id") is not None:
        await _zone_for_write(db, eff["zone_id"], user)
    parent_id = eff.get("parent_id")
    if parent_id is not None and (touched is None or touched & {"parent_id", "zone_id"}):
        if parent_id == splitter_id:
            raise ValidationAppError("Splitter tidak bisa jadi induk dirinya sendiri")
        parent = await repo.get_splitter_row(db, parent_id, owner_of(user))
        if parent is None:
            raise NotFoundError(f"Splitter induk {parent_id} tidak ditemukan")
        parent_obj: Splitter = parent[0]
        # Invariant produk (label UI "Induk (ODC)"): induk harus ODC dan satu zone
        # dengan splitter ini. Dulu ODP atau splitter zona lain bisa jadi induk.
        if parent_obj.type != "odc":
            raise ValidationAppError("Induk splitter harus bertipe ODC")
        if eff.get("zone_id") is not None and parent_obj.zone_id != eff["zone_id"]:
            raise ValidationAppError("Induk splitter harus satu zone dengan splitter ini")
        # Siklus tidak langsung (A induk B, lalu B induk A) juga harus ditolak:
        # telusuri rantai induk calon induk; kalau sampai ke splitter yang diubah,
        # itu siklus. Untuk splitter baru (splitter_id None) tidak mungkin ada siklus.
        if splitter_id is not None:
            seen = set()
            current_obj = parent_obj
            while current_obj is not None and current_obj.parent_id is not None \
                    and current_obj.id not in seen:
                if current_obj.parent_id == splitter_id:
                    raise ValidationAppError(
                        "Splitter induk membentuk siklus (induknya adalah turunan splitter ini)")
                seen.add(current_obj.id)
                current_obj = await db.get(Splitter, current_obj.parent_id)
    scope = scope_olt_ids(user)
    olt_id = eff.get("olt_id")
    if olt_id is not None and (touched is None or touched & {"olt_id", "pon_port_id"}):
        # get_active memfilter deleted_at; scope memastikan OLT milik tenant lain
        # tidak bisa ditautkan (dulu hanya db.get, tanpa scope dan tanpa deleted_at).
        if await olt_repo.get_active(db, olt_id, scope) is None:
            raise NotFoundError(f"OLT {olt_id} tidak ditemukan atau di luar scope")
    pon_port_id = eff.get("pon_port_id")
    if pon_port_id is not None and (touched is None or touched & {"olt_id", "pon_port_id"}):
        pon = await db.get(PonPort, pon_port_id)
        if pon is None:
            raise NotFoundError(f"PON port {pon_port_id} tidak ditemukan")
        if olt_id is not None and pon.olt_id != olt_id:
            raise ValidationAppError("PON port bukan milik OLT yang dipilih")
        if await olt_repo.get_active(db, pon.olt_id, scope) is None:
            raise NotFoundError("OLT pemilik PON port tidak ditemukan atau di luar scope")


async def create_splitter(db: AsyncSession, body: SplitterCreate, user: User) -> SplitterDetail:
    values = body.model_dump()
    if values.get("name"):
        values["name"] = _clean_name(values["name"]) or values["name"]
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
    if values.get("name"):
        values["name"] = _clean_name(values["name"]) or values["name"]
    # Zone tidak boleh dikosongkan lewat PATCH: zone menentukan pemilik splitter,
    # dan splitter tanpa zone menjadi tidak terlihat API (inner join ke Zone).
    if "zone_id" in values and values["zone_id"] is None:
        raise ValidationAppError("Zone splitter tidak boleh dikosongkan")
    await _check_refs(db, values, user, splitter_id, current=splitter)
    if values.get("ratio"):
        values["capacity"] = RATIO_CAPACITY[values["ratio"]]
        # Kapasitas adalah batas keras di sini: menurunkan ratio di bawah jumlah
        # ONU yang menempel ditolak, bukan diam-diam membuat splitter over-capacity.
        onu_count = await repo.count_onus(db, Onu.splitter_id == splitter_id)
        if onu_count > values["capacity"]:
            raise ConflictError(
                f"Ratio {values['ratio']} (kapasitas {values['capacity']}) lebih kecil "
                f"dari {onu_count} ONU yang menempel di splitter ini")
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
    if await repo.count_rows(db, OnuPreset, OnuPreset.splitter_id == splitter_id):
        raise ConflictError("Splitter masih dipakai preset, tidak bisa dihapus")
    try:
        await db.delete(row[0])
        await log_activity(db, action="splitter.delete", entity_type="splitter",
                           entity_id=str(splitter_id), success=True, user_id=user.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Splitter masih dipakai, tidak bisa dihapus") from exc


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


# Kode ODP operator: `WNG-01B0301` (3 huruf area, 2 digit, 1 huruf, 3-4 digit). Kode ini
# identitas ODP yang stabil; teks sesudahnya cuma label yang ditulis tak konsisten di
# perangkat (spasi vs `_`, huruf besar/kecil, terpotong batas panjang description OLT).
_ODP_CODE_RE = re.compile(r"^\s*([A-Za-z]{2,5}-\d{2}[A-Za-z]\d{3,5})(?![A-Za-z0-9])[\s_\-]*(.*)$", re.S)


def split_odp_name(name: str) -> tuple[str | None, str]:
    """`WNG-01B0301-Barat_PDAM` -> (`WNG-01B0301`, `Barat PDAM`). Tanpa kode -> (None, nama)."""
    m = _ODP_CODE_RE.match(name or "")
    if not m:
        return None, " ".join((name or "").replace("_", " ").split())
    label = " ".join(m.group(2).replace("_", " ").split()).strip(" -")
    # sisa token `_authd_` yang terpotong batas panjang description OLT
    label = re.sub(r"\s(?:au|aut|auth|authd)$", "", label, flags=re.I)
    return m.group(1).upper(), label


def splitter_key(name: str, zone_id: int | None = None) -> tuple:
    """Kunci identitas ODP: kode bila ada (zone diabaikan), kalau tidak nama+zone."""
    code, label = split_odp_name(name)
    return ("code", code) if code else ("name", normalize_master_name(label), zone_id)


def _same_odp_label(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a == b or a.startswith(b) or b.startswith(a)  # terpotong = awalan dari yang utuh


async def get_or_create_splitter(db: AsyncSession, name: str, *, zone_id: int | None,
                                 olt_id: int | None, create: bool = True) -> Splitter | None:
    """Splitter/ODP bernama ini; dibuat sebagai tipe `odp` bila perlu.

    Bila nama memuat kode ODP (`WNG-01B0301-...`) kuncinya KODE di OLT yang sama — varian
    `_` vs spasi, beda huruf besar, atau nama terpotong dianggap ODP yang sama, dan label
    terpanjang yang dipakai. Tanpa kode: (zone_id, nama ter-normalisasi) seperti dulu.
    `ratio`/`capacity` TIDAK ditebak — operator mengisi di Settings > Splitter.

    KEBIJAKAN KAPASITAS (dipilih pada audit 2026-10-28, dikoordinasikan ke area
    lifecycle lewat laporan): splitter auto-provision dengan capacity NULL
    berarti "kapasitas BELUM DIKETAHUI", BUKAN "tidak terbatas". Otorisasi ke
    splitter seperti itu HARUS ditolak sampai ratio diisi — tetapi penolakan itu
    hidup di `onu_service._check_authorize` (di luar file area ini), jadi di
    sini TIDAK diubah perilaku otorisasinya. Yang dilakukan sisi master data:
    capacity tetap NULL (tidak dikarang angka default, karena angka karangan
    bisa memblokir port yang sah atau meloloskan port yang melebihi splitter
    asli), dan UI Splitters menandai splitter tanpa kapasitas supaya operator
    melihat dan mengisinya sebelum dipakai otorisasi.
    """
    name = name.strip()
    if not name:
        return None
    code, label = split_odp_name(name)
    clean = " ".join(name.replace("_", " ").split())
    if code:
        full = f"{code}-{label}" if label else code
        # Filter akhir di Python (kode bisa ada di `code` ATAU awalan nama); SQL hanya menyempit.
        rows = (await db.execute(
            select(Splitter).where(Splitter.name.ilike(f"{code}%")))).scalars()
        cands = [c for c in rows
                 if split_odp_name(c.name)[0] == code
                 and (olt_id is None or c.olt_id in (olt_id, None))
                 and _same_odp_label(split_odp_name(c.name)[1], label)]
        if cands:
            ex = cands[0]
            if len(full) > len(ex.name):
                ex.name = full[:100]
            if ex.code is None:
                ex.code = code
            return ex
        clean = full
    else:
        key = normalize_master_name(name)
        stmt = select(Splitter).where(
            func.lower(func.regexp_replace(Splitter.name, r"[_\s]+", " ", "g")) == key)
        stmt = stmt.where(Splitter.zone_id == zone_id) if zone_id is not None \
            else stmt.where(Splitter.zone_id.is_(None))
        existing = await db.scalar(stmt)
        if existing is not None:
            return existing
    if not create:
        return None
    splitter = Splitter(name=clean[:100], code=code, type="odp", zone_id=zone_id, olt_id=olt_id)
    db.add(splitter)
    await db.flush()
    return splitter


# --- onu presets -------------------------------------------------------------
# "Gunakan preset" + "Simpan sebagai preset" di Form Otorisasi (PRD 3.4.4). Scope ikut
# pola zone/splitter: owner-scoped lewat rbac.owner_of, Superadmin lihat semua.

def _preset_out(preset: OnuPreset) -> OnuPresetOut:
    """Nama profile di preset dibersihkan saat tampil, sama seperti baris speed_profiles.

    Form Otorisasi mencocokkan `download_profile`/`upload_profile` preset ke `name` speed
    profile dari API; dua-duanya harus lewat pembersih yang sama atau preset lama (berisi
    `SMARTOLT-...`) berhenti cocok.
    """
    out = OnuPresetOut.model_validate(preset)
    return out.model_copy(update={
        "download_profile": clean_profile_name(out.download_profile),
        "upload_profile": clean_profile_name(out.upload_profile),
    })


async def list_presets(db: AsyncSession, user: User) -> list[OnuPresetOut]:
    return [_preset_out(p) for p in await repo.list_presets(db, owner_of(user))]


async def _validate_preset_refs(db: AsyncSession, body: OnuPresetCreate,
                                user: User) -> None:
    """Validasi referensi preset, dipakai create DAN update (DRY).

    Termasuk aturan baru: bila zone_id dan splitter_id keduanya diisi, splitter
    harus berada di zone itu (splitter.zone_id == zone_id). Sebelumnya preset
    bisa menyimpan pasangan zone/splitter yang tidak cocok, lalu otorisasi yang
    memakai preset itu gagal atau menempelkan ONU ke splitter di zone lain.
    """
    if await db.get(OnuType, body.onu_type_id) is None:
        raise NotFoundError(f"Tipe ONU {body.onu_type_id} tidak ditemukan")
    if body.zone_id is not None:
        await _zone_for_write(db, body.zone_id, user)
    splitter = None
    if body.splitter_id is not None:
        row = await repo.get_splitter_row(db, body.splitter_id, owner_of(user))
        if row is None:
            raise NotFoundError(f"Splitter {body.splitter_id} tidak ditemukan")
        splitter = row[0]
    if body.zone_id is not None and splitter is not None \
            and splitter.zone_id != body.zone_id:
        raise ValidationAppError(
            f"Splitter {splitter.name} berada di zone lain, bukan zone yang dipilih "
            "di preset ini")
    # Nama profile dan nomor VLAN divalidasi keberadaannya di katalog master
    # (preset tidak terikat satu OLT; pencocokan per-OLT tetap terjadi saat
    # preset dipakai, sesuai komentar skema). Nama dibandingkan setelah
    # dibersihkan, sama seperti tampilan — dulu disimpan mentah tanpa validasi,
    # jadi nama salah ketik / VLAN yang tidak ada gagal cocok diam-diam di
    # form otorisasi.
    scope = scope_olt_ids(user)
    for field, direction in (("download_profile", "download"), ("upload_profile", "upload")):
        value = getattr(body, field)
        if not value:
            continue
        cleaned = (clean_profile_name(value) or value).lower()
        stmt = select(SpeedProfile).where(SpeedProfile.direction == direction)
        if scope is not None:
            stmt = stmt.where(or_(SpeedProfile.olt_id.is_(None),
                                  SpeedProfile.olt_id.in_(scope)))
        found = any((clean_profile_name(p.name) or p.name).lower() == cleaned
                    for p in (await db.execute(stmt)).scalars().all())
        if not found:
            raise ValidationAppError(
                f"Profile {direction} '{value}' tidak ditemukan di speed profiles")
    if body.vlan is not None:
        stmt = select(Vlan).where(Vlan.vlan_id == body.vlan)
        if scope is not None:
            stmt = stmt.where(or_(Vlan.olt_id.is_(None), Vlan.olt_id.in_(scope)))
        if await db.scalar(stmt) is None:
            raise ValidationAppError(f"VLAN {body.vlan} tidak ditemukan di master VLAN")


async def create_preset(db: AsyncSession, body: OnuPresetCreate, user: User) -> OnuPresetOut:
    owner_id = _writer_owner(user)
    name = _clean_name(body.name) or body.name
    if await repo.preset_name_taken(db, owner_id, name):
        raise ConflictError(f"Preset '{name}' sudah ada")
    await _validate_preset_refs(db, body, user)
    preset = OnuPreset(owner_id=owner_id, **body.model_dump(), name=name)
    await _save(db, preset, action="onu_preset.create", entity="onu_preset", user=user,
                after=body.model_dump(mode="json"))
    return _preset_out(preset)


async def update_preset(db: AsyncSession, preset_id: int, body: OnuPresetCreate,
                        user: User) -> OnuPresetOut:
    """Edit preset penuh (tidak ada skema parsial di repo — router memakai
    OnuPresetCreate yang sama dengan create, jadi UI edit mengirim semua field).
    Scope sama dengan delete: Superadmin bebas, Admin hanya preset miliknya.
    """
    preset = await db.get(OnuPreset, preset_id)
    owner = owner_of(user)
    if preset is None or (owner is not None and preset.owner_id != owner):
        raise NotFoundError(f"Preset {preset_id} tidak ditemukan")
    name = _clean_name(body.name) or body.name
    taken = await db.scalar(
        select(OnuPreset.id).where(OnuPreset.owner_id == preset.owner_id,
                                   func.lower(OnuPreset.name) == name.lower(),
                                   OnuPreset.id != preset_id))
    if taken is not None:
        raise ConflictError(f"Preset '{name}' sudah ada")
    await _validate_preset_refs(db, body, user)
    for field, value in body.model_dump().items():
        setattr(preset, field, value)
    preset.name = name
    await _save(db, preset, action="onu_preset.update", entity="onu_preset", user=user,
                after=body.model_dump(mode="json"))
    return _preset_out(preset)


async def delete_preset(db: AsyncSession, preset_id: int, user: User) -> None:
    preset = await db.get(OnuPreset, preset_id)
    owner = owner_of(user)
    if preset is None or (owner is not None and preset.owner_id != owner):
        raise NotFoundError(f"Preset {preset_id} tidak ditemukan")
    if await repo.count_onus(db, Onu.preset_id == preset_id):
        raise ConflictError("Preset masih dipakai ONU, tidak bisa dihapus")
    try:
        await db.delete(preset)
        await log_activity(db, action="onu_preset.delete", entity_type="onu_preset",
                           entity_id=str(preset_id), success=True, user_id=user.id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Preset masih dipakai, tidak bisa dihapus") from exc
