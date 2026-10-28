"""ONU operations. API side: cached reads from DB + enqueue jobs (one commit). Worker side:
OLT writes, each logged with raw_command/raw_output; ALLOW_WRITE_COMMANDS=false refuses all
of them (PRD X.4).
"""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AppError,
    CommandRejectedError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.profile_name import clean_profile_name
from app.core.rbac import MANAGERS, scope_olt_ids
from app.core.security import decrypt_secret, encrypt_secret
from app.core.signal import BUCKETS, rx_bucket
from app.drivers.base import OltDriver
from app.drivers.onu_report import parse_management_ip, parse_pppoe, parse_wan_vlan, wan_vlan_not_management
from app.drivers.types import AuthorizeRequest, DriverResult, ModifyRequest
from app.models.job import Job
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.setting import Setting
from app.models.speed_profile import SpeedProfile
from app.models.unconfigured_onu import UnconfiguredOnu
from app.models.user import User
from app.models.vlan import Vlan
from app.repositories import job_repo, olt_repo, onu_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.onu import (
    DEFAULT_ONU_MODE,
    DEFAULT_WAN_MODE,
    AuthorizeBody,
    OnuDetail,
    OnuInfoBody,
    OnuLog,
    OnuRow,
    OnuServiceVlan,
    PendingOnu,
)
from app.services import job_service, master_data_service
from app.services.onu_device_metadata import classify_service_vlans

RX_DEFAULTS = {"warn": -25.0, "crit": -27.0}  # PRD 3.4; overridable via settings.rx_threshold
SIGNAL_RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
BULK_MAX = 200  # batas aksi massal tabel Configured; cukup besar untuk satu halaman penuh
CSV_MAX = 50_000  # batas baris export, menjaga memori API tetap terbatas

async def rx_thresholds(db: AsyncSession) -> dict[str, float]:
    row = await db.get(Setting, "rx_threshold")
    return {**RX_DEFAULTS, **(row.value if row else {})}

def _row(onu: Onu, olt_name: str, slot: int, port: int, download_profile_name: str | None,
         upload_profile_name: str | None = None, vlan_number: int | None = None,
         zone_name: str | None = None, splitter_name: str | None = None,
         preset_name: str | None = None, registered_by_name: str | None = None) -> dict:
    data = {c: getattr(onu, c) for c in OnuDetail.model_fields if hasattr(onu, c)}
    data["ip_address"] = str(onu.ip_address) if onu.ip_address else None
    data["wan_ip_address"] = str(onu.wan_ip_address) if onu.wan_ip_address else None
    return {**data, "olt_name": olt_name, "slot": slot, "port": port,
            "download_profile_name": clean_profile_name(download_profile_name),
            "upload_profile_name": clean_profile_name(upload_profile_name),
            "vlan_number": vlan_number,
            "zone_name": zone_name, "splitter_name": splitter_name,
            "preset_name": preset_name, "registered_by_name": registered_by_name}

async def search_onus(db: AsyncSession, user: User, *, q: str | None, olt_id: int | None,
                      pon_port_id: int | None, state: str | None,
                      download_speed_profile_id: int | None = None,
                      upload_speed_profile_id: int | None = None,
                      sort: str, page: int, size: int | None,
                      signal: list[str] | None = None, status: list[str] | None = None,
                      vlan_id: int | None = None, zone_id: int | None = None,
                      splitter_id: int | None = None,
                      onu_type: str | None = None) -> tuple[list[OnuRow], int]:
    if sort.lstrip("-") not in onu_repo.SORT_COLUMNS:
        raise ValidationAppError(f"Unknown sort '{sort}'")
    for bucket in signal or []:
        if bucket not in BUCKETS:
            raise ValidationAppError(f"Unknown rx bucket '{bucket}'")
    rows, total = await onu_repo.search(
        db, scope_olt_ids(user), q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
        download_speed_profile_id=download_speed_profile_id,
        upload_speed_profile_id=upload_speed_profile_id,
        rx_warn_dbm=(await rx_thresholds(db))["warn"],
        sort=sort, page=page, size=size, signal=signal, status=status, vlan_id=vlan_id,
        zone_id=zone_id, splitter_id=splitter_id, onu_type=onu_type,
    )
    return [OnuRow(**_row(*r)) for r in rows], total

async def _get_row(db: AsyncSession, serial: str, user: User):
    row = await onu_repo.get_row_by_serial(db, serial, scope_olt_ids(user))
    if row is None:
        raise NotFoundError(f"ONU {serial} not found")
    return row

async def _service_vlans(db: AsyncSession, onu: Onu) -> list[OnuServiceVlan] | None:
    """`onus.service_vlan_ids` (nomor VLAN perangkat) + nama/tipe dari master VLAN.

    `None` diteruskan apa adanya: "belum pernah disinkron" bukan "tidak punya VLAN".
    Pencocokan master dibatasi OLT ONU ini plus VLAN global (`olt_id IS NULL`) —
    nomor VLAN sama di OLT berbeda adalah VLAN berbeda.
    """
    numbers = onu.service_vlan_ids
    if numbers is None:
        return None
    rows = (await db.execute(select(Vlan).where(
        or_(Vlan.olt_id == onu.olt_id, Vlan.olt_id.is_(None))
    ))).scalars()
    master = {v.vlan_id: (v.name, v.type) for v in rows}
    return [
        OnuServiceVlan(vlan_id=v.vlan_id, name=v.name, is_management=v.is_management,
                       in_master=v.in_master)
        for v in classify_service_vlans([int(n) for n in numbers], master)
    ]

def _apply_mode_defaults(detail: OnuDetail) -> None:
    """Isi mode efektif + penanda sumber. Kolom DB kosong = tidak terbaca di CLI, maka
    pakai default pemilik (Routing / Setup via ONU webpage) HANYA di respons; DB tetap
    kosong supaya default tidak pernah tersamar sebagai hasil baca perangkat.
    """
    if detail.onu_mode in (None, ""):
        detail.onu_mode, detail.onu_mode_source = DEFAULT_ONU_MODE, "default"
    if detail.wan_mode in (None, ""):
        detail.wan_mode, detail.wan_mode_source = DEFAULT_WAN_MODE, "default"


async def get_onu(db: AsyncSession, serial: str, user: User) -> OnuDetail:
    row = await _get_row(db, serial, user)
    detail = OnuDetail(**_row(*row))
    detail.service_vlans = await _service_vlans(db, row[0])
    detail.mgmt_vlan = next((v.vlan_id for v in detail.service_vlans or [] if v.is_management), None)
    _apply_mode_defaults(detail)
    # Password PPPoE = kredensial pelanggan: sama seperti running-config, manager saja.
    if row[0].pppoe_password_enc and user.role in MANAGERS:
        detail.pppoe_password = decrypt_secret(row[0].pppoe_password_enc)
    return detail

async def signal_history(db: AsyncSession, serial: str, range_: str, user: User) -> list:
    onu = (await _get_row(db, serial, user))[0]
    return await onu_repo.signal_history(db, onu.id, datetime.now(UTC) - SIGNAL_RANGES[range_])

async def update_info(db: AsyncSession, serial: str, body: OnuInfoBody, user: User) -> OnuDetail:
    """Simpan data pelanggan/lokasi ONU. Tidak menyentuh OLT (kolom DB saja), jadi tidak
    lewat job dan tidak terpengaruh ALLOW_WRITE_COMMANDS. Tetap dicatat ke activity_logs.
    """
    onu = (await _get_row(db, serial, user))[0]
    values = body.model_dump(exclude_unset=True)
    if "customer_id" in values and values["customer_id"] and \
            values["customer_id"] != onu.customer_id and \
            await onu_repo.exists_customer_id(db, values["customer_id"]):
        raise ConflictError(f"Customer ID {values['customer_id']} sudah dipakai ONU lain")
    # Zone/splitter dicek lewat master_data_service: aturan scope pemilik hanya ditulis di sana.
    if values.get("zone_id") is not None:
        await master_data_service.get_zone(db, values["zone_id"], user)
    if values.get("splitter_id") is not None:
        await master_data_service.get_splitter(db, values["splitter_id"], user)
    for field, value in values.items():
        setattr(onu, field, value)
    await log_activity(db, action="onu.update_info", entity_type="onu", entity_id=str(onu.id),
                       success=True, user_id=user.id, olt_id=onu.olt_id, onu_id=onu.id,
                       after=body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    return await get_onu(db, onu.serial_number, user)

async def onu_logs(db: AsyncSession, serial: str, limit: int, user: User) -> list[OnuLog]:
    onu = (await _get_row(db, serial, user))[0]
    return [
        OnuLog(id=log.id, created_at=log.created_at, username=username, action=log.action,
               success=log.success, job_id=log.job_id, raw_command=log.raw_command,
               raw_output=log.raw_output)
        for log, username in await onu_repo.logs(db, onu.id, limit)
    ]

async def list_pending(db: AsyncSession, olt_id: int | None, user: User) -> list[PendingOnu]:
    return [
        PendingOnu(id=u.id, olt_id=u.olt_id, olt_name=name, pon_port_id=u.pon_port_id,
                   slot=slot, port=port, serial_number=u.serial_number, onu_type=u.onu_type,
                   first_seen_at=u.first_seen_at, last_seen_at=u.last_seen_at)
        for u, name, slot, port in await onu_repo.list_pending(db, olt_id, scope_olt_ids(user))
    ]

async def customer_id_taken(db: AsyncSession, customer_id: str) -> bool:
    return await onu_repo.exists_customer_id(db, customer_id)

async def _check_authorize(db: AsyncSession, body: AuthorizeBody, user: User) -> UnconfiguredOnu:
    olt = await olt_repo.get_active(db, body.olt_id, scope_olt_ids(user))
    if olt is None:
        raise NotFoundError(f"OLT {body.olt_id} not found")
    pending = await onu_repo.get_pending(db, body.olt_id, body.serial_number)
    if pending is None:
        raise NotFoundError(f"{body.serial_number} is not in the unconfigured list of this OLT")
    if await onu_repo.exists_serial(db, body.olt_id, body.serial_number):
        raise ConflictError(f"ONU {body.serial_number} is already registered")
    if await onu_repo.exists_customer_id(db, body.customer_id):
        raise ConflictError(f"Customer ID {body.customer_id} is already used")
    if body.onu_index is not None:
        if body.onu_index > olt.max_onu_per_port:
            raise ValidationAppError(f"ONU ID must be 1..{olt.max_onu_per_port}")
        if await onu_repo.exists_index(db, pending.pon_port_id, body.onu_index):
            raise ConflictError(f"ONU ID {body.onu_index} is already used on this PON")
    if body.vlan_id and await db.get(Vlan, body.vlan_id) is None:
        raise NotFoundError(f"VLAN {body.vlan_id} not found")
    if body.download_speed_profile_id and \
            await db.get(SpeedProfile, body.download_speed_profile_id) is None:
        raise NotFoundError(f"Speed profile {body.download_speed_profile_id} not found")
    if body.upload_speed_profile_id and \
            await db.get(SpeedProfile, body.upload_speed_profile_id) is None:
        raise NotFoundError(f"Speed profile {body.upload_speed_profile_id} not found")
    if body.wan_mode == "pppoe" and not body.pppoe_username:
        raise ValidationAppError("Mode WAN PPPoE butuh username PPPoE")
    return pending

async def create_and_enqueue_authorize(db: AsyncSession, body: AuthorizeBody, user: User) -> int:
    """ONU row + authorize job in one commit (PRD 4.5.A atomicity argument)."""
    ensure_writes_allowed()
    pending = await _check_authorize(db, body, user)
    # PPPoE password tidak pernah disimpan polos (PRD 3.4.4): kolom *_enc saja.
    values = body.model_dump(exclude={"onu_type", "pppoe_password"})
    onu = Onu(
        **values,
        pon_port_id=pending.pon_port_id, onu_type=body.onu_type or pending.onu_type,
        auth_type="sn", status="unknown", config_state="configuring", admin_state="enabled",
        pppoe_password_enc=(encrypt_secret(body.pppoe_password)
                            if body.pppoe_password else None),
    )
    db.add(onu)
    await db.flush()
    job = await job_service.enqueue(db, "authorize_onu", olt_id=onu.olt_id, onu_id=onu.id,
                                    created_by=user.id)
    await db.commit()
    return job.id

async def _validate_job_payload(db: AsyncSession, onu: Onu, job_type: str,
                                payload: dict | None) -> None:
    """Validasi di sisi API supaya kesalahan input ketahuan sebelum jadi job gagal."""
    payload = payload or {}
    if job_type == "apply_speed_profile":
        for key in ("download_speed_profile_id", "upload_speed_profile_id"):
            pid = payload.get(key)
            if pid and await db.get(SpeedProfile, pid) is None:
                raise NotFoundError(f"Speed profile {pid} not found")
        if not payload.get("download_speed_profile_id") and not payload.get("upload_speed_profile_id"):
            raise ValidationAppError("Pilih minimal satu profile (download/upload)")
    elif job_type == "set_onu_vlan":
        vlan = await db.get(Vlan, payload["vlan_id"])
        if vlan is None:
            raise NotFoundError(f"VLAN {payload['vlan_id']} not found")
        if vlan.id == onu.vlan_id:
            raise ConflictError("VLAN ONU sudah sama dengan yang dipilih")
    elif job_type == "replace_onu":
        serial = payload["serial_number"]
        if serial == onu.serial_number:
            raise ConflictError("Serial number baru sama dengan yang sekarang")
        if await onu_repo.exists_serial(db, onu.olt_id, serial):
            raise ConflictError(f"ONU {serial} sudah terdaftar di OLT ini")

async def enqueue_onu_job(db: AsyncSession, serial: str, job_type: str, user: User,
                          payload: dict | None = None) -> int:
    ensure_writes_allowed()
    onu = (await _get_row(db, serial, user))[0]
    if onu.onu_index is None or onu.config_state != "success":
        raise ConflictError(f"ONU {serial} is not provisioned yet")
    await _validate_job_payload(db, onu, job_type, payload)
    job = await job_service.enqueue(db, job_type, olt_id=onu.olt_id, onu_id=onu.id,
                                    payload=payload, created_by=user.id)
    await db.commit()
    return job.id

async def enqueue_bulk(db: AsyncSession, serials: list[str], job_type: str, user: User,
                       payload: dict | None = None) -> list[dict]:
    """Bulk action tabel Configured: satu job per ONU (PRD 3.4.5).

    Tidak atomik lintas ONU dengan sengaja — satu ONU bermasalah tidak boleh membatalkan
    sisanya. Hasil per-serial dikembalikan supaya UI bisa menampilkan yang gagal,
    tanpa optimistic update (AGENTS.md).
    """
    ensure_writes_allowed()
    if not serials:
        raise ValidationAppError("Tidak ada ONU dipilih")
    if len(serials) > BULK_MAX:
        raise ValidationAppError(f"Maksimal {BULK_MAX} ONU per aksi massal")
    results: list[dict] = []
    for serial in dict.fromkeys(serials):  # dedupe, urutan tetap
        try:
            onu = (await _get_row(db, serial, user))[0]
            if onu.onu_index is None or onu.config_state != "success":
                raise ConflictError(f"ONU {serial} is not provisioned yet")
            await _validate_job_payload(db, onu, job_type, payload)
        except AppError as exc:
            # Gagal validasi = belum ada tulisan apa pun, jadi TIDAK perlu rollback.
            # Rollback di sini membuat objek ONU di identity map kedaluwarsa dan
            # iterasi berikutnya meledak (MissingGreenlet).
            results.append({"serial_number": serial, "job_id": None, "error": exc.message})
            continue
        try:
            job = await job_service.enqueue(db, job_type, olt_id=onu.olt_id, onu_id=onu.id,
                                            payload=payload, created_by=user.id)
            await db.commit()
            results.append({"serial_number": serial, "job_id": job.id, "error": None})
        except AppError as exc:
            await db.rollback()
            db.expunge_all()  # buang objek kedaluwarsa supaya serial berikutnya tetap bisa dibaca
            results.append({"serial_number": serial, "job_id": None, "error": exc.message})
    return results

CSV_COLUMNS = [
    ("serial_number", "Serial Number"), ("name", "Nama"), ("customer_id", "ID Pelanggan"),
    ("customer_name", "Pelanggan"), ("olt_name", "OLT"), ("pon", "PON"),
    ("onu_index", "ONU ID"), ("onu_type", "Tipe"), ("status", "Status"),
    ("admin_state", "Admin"), ("rx_power_dbm", "RX ONU (dBm)"),
    ("olt_rx_power_dbm", "RX OLT (dBm)"), ("signal", "Sinyal"),
    ("download_profile_name", "Paket Download"), ("upload_profile_name", "Paket Upload"),
    ("vlan_number", "VLAN"), ("zone_name", "Zona"),
    ("splitter_name", "Splitter"), ("last_seen_at", "Terakhir Online"),
    ("last_down_reason", "Alasan Down"),
]

def csv_rows(rows: list[OnuRow]) -> Iterator[list[str]]:
    """Baris CSV export (header dulu). Kolom 'Sinyal' pakai rx_bucket() — satu definisi
    bucket untuk seluruh aplikasi (DECISIONS.md), jangan bandingkan dBm di sini.
    """
    yield [label for _, label in CSV_COLUMNS]
    for row in rows:
        values = {
            **row.model_dump(),
            "pon": f"{row.slot}/{row.port}",
            "signal": rx_bucket(row.rx_power_dbm),
        }
        yield ["" if values[key] is None else str(values[key]) for key, _ in CSV_COLUMNS]

def csv_bytes(rows: list[OnuRow]) -> bytes:
    """UTF-8 BOM supaya Excel di Windows tidak merusak karakter non-ASCII."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerows(csv_rows(rows))
    return buffer.getvalue().encode("utf-8-sig")

def ensure_writes_allowed() -> None:
    if not settings.allow_write_commands:
        raise ForbiddenError("ALLOW_WRITE_COMMANDS=false: write commands to the OLT are disabled")

async def _load(db: AsyncSession, job: Job) -> tuple[Onu, PonPort]:
    onu = await db.get(Onu, job.onu_id) if job.onu_id else None
    if onu is None or onu.deleted_at is not None:
        raise NotFoundError(f"ONU {job.onu_id} not found")
    return onu, await db.get(PonPort, onu.pon_port_id)

async def _record(db: AsyncSession, job: Job, onu: Onu, action: str, result: DriverResult) -> None:
    """Log the raw exchange and commit it before raising, so a rejected command is still
    in activity_logs after the worker rolls back.
    """
    await log_activity(
        db, action=action, entity_type="onu", entity_id=str(onu.id), success=result.success,
        user_id=job.created_by, job_id=job.id, olt_id=onu.olt_id, onu_id=onu.id,
        raw_command=result.raw_command, raw_output=result.raw_output,
    )
    if not result.success:
        if action == "onu.authorize":
            onu.config_state = "failed"
        await db.commit()
        raise CommandRejectedError(result.message or "OLT rejected command")

def _result(result: DriverResult) -> dict:
    return {"raw_command": result.raw_command}

def pick_free_onu_index(used: list[int], max_index: int) -> int | None:
    taken = set(used)
    return next((i for i in range(1, max_index + 1) if i not in taken), None)

async def authorize_onu(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    if onu.onu_index is None:
        # Read live from the OLT inside the job: DB can lag, and one-job-at-a-time per OLT
        # avoids two concurrent authorizations picking the same ID.
        olt = await db.get(Olt, onu.olt_id)
        used = await driver.list_onu_ids(pon.slot, pon.port)
        onu.onu_index = pick_free_onu_index(used, olt.max_onu_per_port)
        if onu.onu_index is None:
            onu.config_state = "failed"
            await db.commit()
            raise CommandRejectedError(f"PON {pon.slot}/{pon.port} full")
    # vlan_id di tabel onus = FK ke baris vlans; device butuh nomor VLAN-nya.
    vlan = await db.get(Vlan, onu.vlan_id) if onu.vlan_id else None
    dn_profile = await db.get(SpeedProfile, onu.download_speed_profile_id) \
        if onu.download_speed_profile_id else None
    up_profile = await db.get(SpeedProfile, onu.upload_speed_profile_id) \
        if onu.upload_speed_profile_id else None
    req = AuthorizeRequest(
        slot=pon.slot, port=pon.port, onu_id=onu.onu_index, serial_number=onu.serial_number,
        auth_type=onu.auth_type, onu_type=onu.onu_type or "ALL-ONT", name=onu.name or "",
        description=onu.description, loid=onu.loid,
        upload_profile=(up_profile.device_profile_id if up_profile else None) or onu.srv_profile_id,
        download_profile=(dn_profile.device_profile_id if dn_profile else None) or onu.line_profile_id,
        vlan_id=vlan.vlan_id if vlan else None,
    )
    result = await driver.authorize(req)
    await _record(db, job, onu, "onu.authorize", result)
    onu.config_state = "success"
    onu.registered_at = datetime.now(UTC)
    onu.registered_by = job.created_by
    await db.execute(delete(UnconfiguredOnu).where(
        UnconfiguredOnu.olt_id == onu.olt_id, UnconfiguredOnu.serial_number == onu.serial_number
    ))
    return _result(result)

async def delete_onu(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    result = await driver.delete(pon.slot, pon.port, onu.onu_index)
    await _record(db, job, onu, "onu.delete", result)
    onu.deleted_at = datetime.now(UTC)
    return _result(result)

async def reboot_onu(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    result = await driver.reboot(pon.slot, pon.port, onu.onu_index)
    await _record(db, job, onu, "onu.reboot", result)
    return _result(result)

async def set_state(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    enabled = bool(job.payload["enabled"])
    result = await driver.set_state(pon.slot, pon.port, onu.onu_index, enabled)
    await _record(db, job, onu, "onu.set_state", result)
    onu.admin_state = "enabled" if enabled else "disabled"
    return _result(result)

async def apply_speed_profile(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    dn_id, up_id = job.payload.get("download_speed_profile_id"), job.payload.get("upload_speed_profile_id")
    dn_profile = await db.get(SpeedProfile, dn_id) if dn_id else None
    up_profile = await db.get(SpeedProfile, up_id) if up_id else None
    if dn_id and dn_profile is None:
        raise NotFoundError(f"Speed profile {dn_id} not found")
    if up_id and up_profile is None:
        raise NotFoundError(f"Speed profile {up_id} not found")
    req = ModifyRequest(
        slot=pon.slot, port=pon.port, onu_id=onu.onu_index,
        line_profile_id=dn_profile.device_profile_id if dn_profile else None,
        srv_profile_id=up_profile.device_profile_id if up_profile else None,
    )
    result = await driver.modify(req)
    await _record(db, job, onu, "onu.apply_speed_profile", result)
    if dn_profile:
        onu.download_speed_profile_id = dn_profile.id
        onu.line_profile_id = dn_profile.device_profile_id or onu.line_profile_id
    if up_profile:
        onu.upload_speed_profile_id = up_profile.id
        onu.srv_profile_id = up_profile.device_profile_id or onu.srv_profile_id
    return _result(result)

# --- Aksi Detail ONU (PRD 3.4.6) ---------------------------------------------------

async def refresh_onu_detail(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    """Baca live ONU (RX/TX/jarak/versi/running-config) dan simpan ke baris onus.

    Read-only ke OLT, jadi tidak lewat ensure_writes_allowed(). Hasil running-config
    tidak disimpan ke DB (bisa panjang dan berubah terus) — dikembalikan di job.result
    supaya UI tab "Running config" menampilkannya apa adanya.
    """
    onu, pon = await _load(db, job)
    detail = await driver.fetch_onu_detail(pon.slot, pon.port, onu.onu_index)
    # ONU tidak online tidak punya nilai optik: kolomnya DIKOSONGKAN apa adanya (termasuk
    # None), jangan biarkan angka lama hidup di baris ONU — itu yang membuat UI menampilkan
    # "Rx -30 dBm" palsu untuk ONU dying-gasp/LOS. Angka terakhir tetap ada di
    # onu_signal_history. phase_state kosong = parser gagal, bukan bukti ONU mati, jadi
    # nilai lama dipertahankan (sama seperti versi software/hardware).
    phase = (detail.phase_state or "").strip().lower()
    offline = phase != "" and phase not in ("working", "online")
    for field in ("rx_power_dbm", "tx_power_dbm", "olt_rx_power_dbm", "temperature_c",
                  "voltage_v", "bias_current_ma"):
        value = getattr(detail, field, None)
        if value is not None or offline:
            setattr(onu, field, value)
    for field in ("distance_m", "software_version", "hardware_version"):
        value = getattr(detail, field)
        if value is not None:
            setattr(onu, field, value)
    if detail.rx_power_dbm is not None:
        onu.last_sync_at = datetime.now(UTC)
    await log_activity(
        db, action="onu.refresh_detail", entity_type="onu", entity_id=str(onu.id), success=True,
        user_id=job.created_by, job_id=job.id, olt_id=onu.olt_id, onu_id=onu.id,
        raw_command=detail.raw_command,
        # raw_output SENGAJA tidak diisi: `show running-config interface …` memuat
        # kredensial pelanggan (PPPoE/ACS/WiFi/SNMP ONU) dan activity_logs ikut ke backup.
        # Isinya tetap sampai ke UI lewat job.result, yang retensinya terbatas.
    )
    return {
        "raw_command": detail.raw_command,
        "running_config": detail.running_config,
        "phase_state": detail.phase_state,
        "online_duration_s": detail.online_duration_s,
        "software_version": detail.software_version,
        "software_version_standby": detail.software_version_standby,
        "hardware_version": detail.hardware_version,
        "rx_power_dbm": detail.rx_power_dbm,
        "tx_power_dbm": detail.tx_power_dbm,
        "olt_rx_power_dbm": detail.olt_rx_power_dbm,
        "temperature_c": detail.temperature_c,
        "voltage_v": detail.voltage_v,
        "distance_m": detail.distance_m,
    }

async def resync_onu(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    """"Resync config": kirim ulang konfigurasi dari DB ke OLT (idempoten).

    Dipakai kalau config di OLT hilang/berbeda dari DB. Pakai ulang authorize_onu karena
    perintah ZTE `onu <id> type ... sn ...` + profile + service-port memang idempoten;
    menulis ulang alur yang sama di sini akan menduplikasi logika (dilarang di AGENTS.md).
    """
    return await authorize_onu(db, job, driver)

async def set_onu_vlan(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    # UNVERIFIED: uji di ONU test — urutan perintah ubah VLAN belum pernah dijalankan
    # dari Nexfiber ke perangkat nyata.
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    vlan = await db.get(Vlan, job.payload["vlan_id"])
    if vlan is None:
        raise NotFoundError(f"VLAN {job.payload['vlan_id']} not found")
    old = await db.get(Vlan, onu.vlan_id) if onu.vlan_id else None
    result = await driver.set_onu_vlan(pon.slot, pon.port, onu.onu_index,
                                       old.vlan_id if old else None, vlan.vlan_id)
    await _record(db, job, onu, "onu.set_vlan", result)
    onu.vlan_id = vlan.id
    return _result(result)

async def replace_onu(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    """Ganti SN: hapus ONU lama di OLT lalu authorize SN baru di ONU ID yang sama.

    # UNVERIFIED: uji di ONU test — urutan delete+authorize ini belum dijalankan ke
    # perangkat nyata. Baris DB (pelanggan, paket, VLAN) tetap, hanya serial_number ganti,
    # sehingga riwayat sinyal dan log pelanggan tidak terputus (PRD 3.4.6).
    """
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    new_serial = job.payload["serial_number"]
    if await onu_repo.exists_serial(db, onu.olt_id, new_serial):
        raise ConflictError(f"ONU {new_serial} sudah terdaftar di OLT ini")
    delete_result = await driver.delete(pon.slot, pon.port, onu.onu_index)
    await _record(db, job, onu, "onu.replace.delete", delete_result)
    onu.serial_number = new_serial
    onu.onu_type = job.payload.get("onu_type") or onu.onu_type
    onu.mac_address = None  # perangkat baru: MAC/versi lama tidak berlaku lagi
    onu.software_version = None
    onu.hardware_version = None
    onu.config_state = "configuring"
    await db.flush()
    authorize_result = await authorize_onu(db, job, driver)
    await db.execute(delete(UnconfiguredOnu).where(
        UnconfiguredOnu.olt_id == onu.olt_id, UnconfiguredOnu.serial_number == new_serial
    ))
    return {"raw_command": f"{delete_result.raw_command} ; {authorize_result['raw_command']}"}

async def restore_factory(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    # UNVERIFIED: uji di ONU test — tidak ada transkrip CLI restore-factory ZTE di repo,
    # perintahnya disusun mengikuti pola pon-onu-mng. JANGAN dijalankan ke OLT produksi
    # sebelum diverifikasi di ONU test.
    ensure_writes_allowed()
    onu, pon = await _load(db, job)
    result = await driver.restore_factory(pon.slot, pon.port, onu.onu_index)
    await _record(db, job, onu, "onu.restore_factory", result)
    return _result(result)

# --- Diagnostik Detail ONU: Status / Running config / Info SW -----------------------
# Read-only ke OLT (tidak lewat ensure_writes_allowed) tapi tetap lewat job karena setiap
# aksi yang menyentuh OLT = job (AGENTS.md) dan satu sesi CLI per OLT dijaga worker.

DIAGNOSTIC_JOBS = {
    "status": "read_onu_status",
    "running": "read_onu_running_config",
    "software": "read_onu_software",
}
# Hanya view "running" yang memuat kredensial pelanggan (PPPoE/ACS/WiFi/SNMP ONU) —
# dibatasi role manager pada OLT dalam scope-nya. Dua view lain tidak memuat kredensial.
MANAGER_ONLY_VIEWS = {"running"}


async def enqueue_diagnostic(db: AsyncSession, serial: str, view: str, user: User) -> int:
    """POST /api/onus/{serial}/diagnostics — satu job per view, debounce per ONU.

    RBAC dicek DI SINI (bukan hanya di router) supaya aturannya ikut ke semua pemanggil:
    scope OLT lewat _get_row (di luar scope = 404), lalu role untuk view sensitif (403).
    """
    if view not in DIAGNOSTIC_JOBS:
        raise ValidationAppError(f"View diagnostik '{view}' tidak dikenal")
    onu = (await _get_row(db, serial, user))[0]
    if view in MANAGER_ONLY_VIEWS and user.role not in MANAGERS:
        raise ForbiddenError("Peran Anda tidak boleh membuka running-config ONU")
    if onu.onu_index is None or onu.config_state != "success":
        raise ConflictError(f"ONU {serial} is not provisioned yet")
    job_type = DIAGNOSTIC_JOBS[view]
    if await job_repo.exists_active_for_onu(db, onu.id, job_type):
        raise ConflictError("Permintaan sejenis untuk ONU ini masih diproses")
    # max_attempts=1: pembacaan ini dipicu manual dan read-only, jadi retry otomatis tidak
    # berguna — penggunanya ada di depan layar dan bisa klik lagi. Dengan 3 percobaan
    # (backoff 30s + 60s) satu klik yang gagal menahan tombol ~90 detik dan sepanjang itu
    # klik berikutnya dijawab 409 "Pembacaan untuk ONU ini masih berjalan" (terukur: job
    # 6082/6085, 91 detik antre, 3 percobaan). Kegagalan nyata lebih baik tampil langsung.
    job = await job_service.enqueue(db, job_type, olt_id=onu.olt_id, onu_id=onu.id,
                                    payload={"view": view}, created_by=user.id,
                                    max_attempts=1)
    await db.commit()
    return job.id


async def _run_diagnostic(db: AsyncSession, job: Job, driver: OltDriver, view: str) -> dict:
    onu, pon = await _load(db, job)
    fetch = {
        "status": driver.fetch_onu_status_report,
        "running": driver.fetch_onu_running_config,
        "software": driver.fetch_onu_software_report,
    }[view]
    report = await fetch(pon.slot, pon.port, onu.onu_index)
    # Jejak akses dicatat (siapa membuka apa, kapan) TANPA isi output: running-config
    # memuat kredensial pelanggan dan activity_logs ikut ke backup.
    await log_activity(
        db, action=f"onu.read_{view}", entity_type="onu", entity_id=str(onu.id), success=True,
        user_id=job.created_by, job_id=job.id, olt_id=onu.olt_id, onu_id=onu.id,
        raw_command=report.raw_command,
        after={"lines": report.output.count("\n") + 1 if report.output else 0},
    )
    if view == "running":
        management = set((await db.execute(select(Vlan.vlan_id).where(
            Vlan.type == "management", or_(Vlan.olt_id == onu.olt_id, Vlan.olt_id.is_(None))
        ))).scalars())
        _sync_wan_from_running(onu, report.output, management)
    return {"view": report.view, "output": report.output, "raw_command": report.raw_command}


def _sync_wan_from_running(onu: Onu, output: str, management: set[int]) -> None:
    """Sinkronkan kolom WAN ONU dari running-config yang baru dibaca (DB jadi cache terbaru).

    Dua hal yang diambil: VLAN WAN (`flow 1 ... vlan N`) dan PPPoE. Masing-masing hanya
    menulis bila perangkat memang melaporkannya; yang tidak ada dibiarkan apa adanya
    (bukan di-NULL-kan, bukan ditebak). Aturan: WAN = VLAN yang BUKAN ditandai management.
    """
    found = parse_pppoe(output)
    vlan = wan_vlan_not_management(parse_wan_vlan(output), parse_management_ip(output), management)
    if vlan is not None:
        onu.wan_vlan = vlan
    if found is None:
        return
    user, password = found
    onu.wan_mode, onu.onu_mode, onu.pppoe_username = "pppoe", "routing", user[:100]
    if password:
        onu.pppoe_password_enc = encrypt_secret(password)


async def read_onu_status(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    return await _run_diagnostic(db, job, driver, "status")


async def read_onu_running_config(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    """Output utuh tanpa penyamaran, hanya untuk role manager (dicek saat enqueue).

    Dicek ulang di sisi job supaya job yang dibuat lewat jalur lain tetap tunduk.
    """
    creator = await db.get(User, job.created_by) if job.created_by else None
    if creator is None or creator.role not in MANAGERS:
        raise ForbiddenError("Peran pembuat job tidak boleh membuka running-config ONU")
    return await _run_diagnostic(db, job, driver, "running")


async def read_onu_software(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    return await _run_diagnostic(db, job, driver, "software")
