"""ONU operations. API side: cached reads from DB + enqueue jobs (one commit). Worker side:
OLT writes, each logged with raw_command/raw_output; ALLOW_WRITE_COMMANDS=false refuses all
of them (PRD X.4).
"""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
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
from app.core.rbac import scope_olt_ids
from app.core.security import encrypt_secret
from app.core.signal import BUCKETS, rx_bucket
from app.drivers.base import OltDriver
from app.drivers.types import AuthorizeRequest, DriverResult, ModifyRequest
from app.models.job import Job
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.setting import Setting
from app.models.speed_profile import SpeedProfile
from app.models.unconfigured_onu import UnconfiguredOnu
from app.models.user import User
from app.models.vlan import Vlan
from app.repositories import olt_repo, onu_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.onu import AuthorizeBody, OnuDetail, OnuLog, OnuRow, PendingOnu
from app.services import job_service

RX_DEFAULTS = {"warn": -25.0, "crit": -27.0}  # PRD 3.4; overridable via settings.rx_threshold
SIGNAL_RANGES = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
BULK_MAX = 200  # batas aksi massal tabel Configured; cukup besar untuk satu halaman penuh
CSV_MAX = 50_000  # batas baris export, menjaga memori API tetap terbatas

async def rx_thresholds(db: AsyncSession) -> dict[str, float]:
    row = await db.get(Setting, "rx_threshold")
    return {**RX_DEFAULTS, **(row.value if row else {})}

def _row(onu: Onu, olt_name: str, slot: int, port: int, profile_name: str | None,
         vlan_number: int | None = None, zone_name: str | None = None,
         splitter_name: str | None = None) -> dict:
    data = {c: getattr(onu, c) for c in OnuDetail.model_fields if hasattr(onu, c)}
    data["ip_address"] = str(onu.ip_address) if onu.ip_address else None
    return {**data, "olt_name": olt_name, "slot": slot, "port": port,
            "speed_profile_name": profile_name, "vlan_number": vlan_number,
            "zone_name": zone_name, "splitter_name": splitter_name}

async def search_onus(db: AsyncSession, user: User, *, q: str | None, olt_id: int | None,
                      pon_port_id: int | None, state: str | None, speed_profile_id: int | None,
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
        speed_profile_id=speed_profile_id, rx_warn_dbm=(await rx_thresholds(db))["warn"],
        sort=sort, page=page, size=size, signal=signal, status=status, vlan_id=vlan_id,
        zone_id=zone_id, splitter_id=splitter_id, onu_type=onu_type,
    )
    return [OnuRow(**_row(*r)) for r in rows], total

async def _get_row(db: AsyncSession, serial: str, user: User):
    row = await onu_repo.get_row_by_serial(db, serial, scope_olt_ids(user))
    if row is None:
        raise NotFoundError(f"ONU {serial} not found")
    return row

async def get_onu(db: AsyncSession, serial: str, user: User) -> OnuDetail:
    return OnuDetail(**_row(*await _get_row(db, serial, user)))

async def signal_history(db: AsyncSession, serial: str, range_: str, user: User) -> list:
    onu = (await _get_row(db, serial, user))[0]
    return await onu_repo.signal_history(db, onu.id, datetime.now(UTC) - SIGNAL_RANGES[range_])

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
    if body.speed_profile_id and await db.get(SpeedProfile, body.speed_profile_id) is None:
        raise NotFoundError(f"Speed profile {body.speed_profile_id} not found")
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
        if await db.get(SpeedProfile, payload["speed_profile_id"]) is None:
            raise NotFoundError(f"Speed profile {payload['speed_profile_id']} not found")
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
    ("speed_profile_name", "Paket"), ("vlan_number", "VLAN"), ("zone_name", "Zona"),
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
    profile = await db.get(SpeedProfile, onu.speed_profile_id) if onu.speed_profile_id else None
    req = AuthorizeRequest(
        slot=pon.slot, port=pon.port, onu_id=onu.onu_index, serial_number=onu.serial_number,
        auth_type=onu.auth_type, onu_type=onu.onu_type or "ALL-ONT", name=onu.name or "",
        description=onu.description, loid=onu.loid,
        upload_profile=(profile.srv_profile_id if profile else None) or onu.srv_profile_id,
        download_profile=(profile.line_profile_id if profile else None) or onu.line_profile_id,
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
    profile = await db.get(SpeedProfile, job.payload["speed_profile_id"])
    if profile is None:
        raise NotFoundError(f"Speed profile {job.payload['speed_profile_id']} not found")
    req = ModifyRequest(
        slot=pon.slot, port=pon.port, onu_id=onu.onu_index,
        line_profile_id=profile.line_profile_id, srv_profile_id=profile.srv_profile_id,
    )
    result = await driver.modify(req)
    await _record(db, job, onu, "onu.apply_speed_profile", result)
    onu.speed_profile_id = profile.id
    onu.line_profile_id = profile.line_profile_id or onu.line_profile_id
    onu.srv_profile_id = profile.srv_profile_id or onu.srv_profile_id
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
    for field in ("rx_power_dbm", "tx_power_dbm", "olt_rx_power_dbm", "temperature_c",
                  "voltage_v", "distance_m", "software_version", "hardware_version"):
        value = getattr(detail, field)
        if value is not None:
            setattr(onu, field, value)
    if detail.rx_power_dbm is not None:
        onu.last_sync_at = datetime.now(UTC)
    await log_activity(
        db, action="onu.refresh_detail", entity_type="onu", entity_id=str(onu.id), success=True,
        user_id=job.created_by, job_id=job.id, olt_id=onu.olt_id, onu_id=onu.id,
        raw_command=detail.raw_command, raw_output=detail.running_config,
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
