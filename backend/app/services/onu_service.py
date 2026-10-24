"""ONU operations. API side: cached reads from DB + enqueue jobs (one commit). Worker side:
OLT writes, each logged with raw_command/raw_output; ALLOW_WRITE_COMMANDS=false refuses all
of them (PRD X.4).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    CommandRejectedError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.core.rbac import scope_olt_ids
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

async def rx_thresholds(db: AsyncSession) -> dict[str, float]:
    row = await db.get(Setting, "rx_threshold")
    return {**RX_DEFAULTS, **(row.value if row else {})}

def _row(onu: Onu, olt_name: str, slot: int, port: int, profile_name: str | None) -> dict:
    data = {c: getattr(onu, c) for c in OnuDetail.model_fields if hasattr(onu, c)}
    data["ip_address"] = str(onu.ip_address) if onu.ip_address else None
    return {**data, "olt_name": olt_name, "slot": slot, "port": port,
            "speed_profile_name": profile_name}

async def search_onus(db: AsyncSession, user: User, *, q: str | None, olt_id: int | None,
                      pon_port_id: int | None, state: str | None, speed_profile_id: int | None,
                      sort: str, page: int, size: int) -> tuple[list[OnuRow], int]:
    if sort.lstrip("-") not in onu_repo.SORT_COLUMNS:
        raise ValidationAppError(f"Unknown sort '{sort}'")
    rows, total = await onu_repo.search(
        db, scope_olt_ids(user), q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
        speed_profile_id=speed_profile_id, rx_warn_dbm=(await rx_thresholds(db))["warn"],
        sort=sort, page=page, size=size,
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
    return pending

async def create_and_enqueue_authorize(db: AsyncSession, body: AuthorizeBody, user: User) -> int:
    """ONU row + authorize job in one commit (PRD 4.5.A atomicity argument)."""
    ensure_writes_allowed()
    pending = await _check_authorize(db, body, user)
    onu = Onu(
        **body.model_dump(exclude={"onu_type"}),
        pon_port_id=pending.pon_port_id, onu_type=body.onu_type or pending.onu_type,
        auth_type="sn", status="unknown", config_state="configuring", admin_state="enabled",
    )
    db.add(onu)
    await db.flush()
    job = await job_service.enqueue(db, "authorize_onu", olt_id=onu.olt_id, onu_id=onu.id,
                                    created_by=user.id)
    await db.commit()
    return job.id

async def enqueue_onu_job(db: AsyncSession, serial: str, job_type: str, user: User,
                          payload: dict | None = None) -> int:
    ensure_writes_allowed()
    onu = (await _get_row(db, serial, user))[0]
    if onu.onu_index is None or onu.config_state != "success":
        raise ConflictError(f"ONU {serial} is not provisioned yet")
    if job_type == "apply_speed_profile" and await db.get(
        SpeedProfile, payload["speed_profile_id"]
    ) is None:
        raise NotFoundError(f"Speed profile {payload['speed_profile_id']} not found")
    job = await job_service.enqueue(db, job_type, olt_id=onu.olt_id, onu_id=onu.id,
                                    payload=payload, created_by=user.id)
    await db.commit()
    return job.id

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
    req = AuthorizeRequest(
        slot=pon.slot, port=pon.port, onu_id=onu.onu_index, serial_number=onu.serial_number,
        auth_type=onu.auth_type, onu_type=onu.onu_type or "ALL-ONT", name=onu.name or "",
        loid=onu.loid, line_profile_id=onu.line_profile_id, srv_profile_id=onu.srv_profile_id,
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
