"""OLT CRUD + OLT-level jobs. Any contact with the OLT goes through the job queue (PRD 4.2),
except the pre-save connection check, which has no saved credentials to hand the worker.
"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.rbac import MANAGERS, SUPERADMIN, scope_olt_ids
from app.core.security import encrypt_secret
from app.drivers.transport.snmp import SnmpTransport
from app.models.olt import Olt
from app.models.user import User
from app.repositories import olt_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.olt import (
    OltCardOut,
    OltCreate,
    OltDetail,
    OltOut,
    OltRow,
    OltTestRequest,
    OltTestResult,
    OltUpdate,
    PonPortOut,
)
from app.services import job_service

SECRET_FIELDS = {
    "cli_password": "cli_password_enc",
    "cli_enable_password": "cli_enable_password_enc",
    "snmp_community": "snmp_community_enc",
    "snmp_community_rw": "snmp_community_rw_enc",
}

# sysDescr (NEXFIBER-SNMP-OID.md, verified on every vendor): cheapest proof SNMP answers.
OID_SYS_DESCR = "1.3.6.1.2.1.1.1"

async def get_olt(db: AsyncSession, olt_id: int, user: User) -> Olt:
    olt = await olt_repo.get_active(db, olt_id, scope_olt_ids(user))
    if olt is None:
        raise NotFoundError(f"OLT {olt_id} not found")
    return olt

async def list_olts(db: AsyncSession, user: User) -> list[Olt]:
    return await olt_repo.list_active(db, scope_olt_ids(user))

async def list_rows(db: AsyncSession, user: User, search: str | None = None) -> list[OltRow]:
    rows = await olt_repo.list_rows(db, scope_olt_ids(user), search)
    return [
        OltRow(**OltOut.model_validate(olt).model_dump(), owner_name=owner_name,
               onu_count=onu_count, onu_online=onu_online,
               cpu_pct=olt.cpu_pct, ram_pct=olt.ram_pct, temperature_c=olt.temperature_c)
        for olt, owner_name, onu_count, onu_online in rows
    ]

async def _owner_id(db: AsyncSession, owner_id: int | None, user: User) -> int:
    """Superadmin picks the owner; anyone else owns what it touches (PRD 3.7)."""
    if user.role != SUPERADMIN or owner_id is None:
        return user.id
    owner = await db.get(User, owner_id)
    if owner is None or owner.deleted_at is not None or owner.role not in MANAGERS:
        raise ValidationAppError("Pemilik OLT harus Admin atau Superadmin aktif")
    return owner.id

def _apply(olt: Olt, values: dict) -> None:
    for field, value in values.items():
        if field in SECRET_FIELDS:
            setattr(olt, SECRET_FIELDS[field], encrypt_secret(value) if value else None)
        elif field == "host":
            olt.host = str(value)
        else:
            setattr(olt, field, value)

async def _flush(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("An OLT with this host and CLI port already exists") from exc

async def _commit(db: AsyncSession, olt: Olt) -> Olt:
    await db.commit()
    await db.refresh(olt)
    return olt

async def create_olt(db: AsyncSession, body: OltCreate, user: User) -> Olt:
    olt = Olt(owner_id=await _owner_id(db, body.owner_id, user))
    _apply(olt, body.model_dump(exclude={"owner_id"}))
    db.add(olt)
    await _flush(db)
    await log_activity(db, action="olt.create", entity_type="olt", entity_id=str(olt.id),
                       success=True, user_id=user.id, olt_id=olt.id)
    return await _commit(db, olt)

async def update_olt(db: AsyncSession, olt_id: int, body: OltUpdate, user: User) -> Olt:
    olt = await get_olt(db, olt_id, user)
    values = body.model_dump(exclude_unset=True)
    if "owner_id" in values:
        values["owner_id"] = await _owner_id(db, values["owner_id"], user)
    # Empty secret = field left blank in the form = keep the stored credential (PRD 3.4.8).
    values = {k: v for k, v in values.items() if not (k in SECRET_FIELDS and not v)}
    _apply(olt, values)
    await _flush(db)
    await log_activity(db, action="olt.update", entity_type="olt", entity_id=str(olt.id),
                       success=True, user_id=user.id, olt_id=olt.id,
                       after=OltUpdate(**values).model_dump(
                           exclude_unset=True, exclude=set(SECRET_FIELDS), mode="json"))
    return await _commit(db, olt)

async def delete_olt(db: AsyncSession, olt_id: int, user: User, confirm_name: str | None) -> None:
    """Blocked while ONUs exist unless the OLT name is typed back (PRD 3.4.8)."""
    olt = await get_olt(db, olt_id, user)
    onu_count = await olt_repo.count_onus(db, olt_id)
    if onu_count and confirm_name != olt.name:
        raise ConflictError(f"OLT masih punya {onu_count} ONU; ketik nama OLT untuk konfirmasi")
    now = datetime.now(UTC)
    olt.deleted_at = now
    olt.is_active = False
    deleted = await olt_repo.soft_delete_onus(db, olt_id, now)
    await log_activity(db, action="olt.delete", entity_type="olt", entity_id=str(olt.id),
                       success=True, user_id=user.id, olt_id=olt.id,
                       after={"onus_soft_deleted": deleted})
    await db.commit()

async def test_connection(db: AsyncSession, body: OltTestRequest, user: User) -> OltTestResult:
    """SNMP sysDescr get against the values in the form; no row needed, nothing written."""
    snmp = SnmpTransport(str(body.host), body.snmp_community, body.snmp_port)
    try:
        rows = await snmp.bulkwalk(OID_SYS_DESCR)
    except AppError as exc:
        message = exc.message
    except Exception as exc:  # pysnmp surfaces socket/engine errors as plain exceptions
        message = f"SNMP gagal: {exc}"
    else:
        descr = str(rows[0][1]) if rows else ""
        await log_activity(db, action="olt.test_connection", entity_type="olt", success=True,
                           user_id=user.id, raw_command=f"snmpget {OID_SYS_DESCR}",
                           raw_output=descr[:500])
        await db.commit()
        return OltTestResult(success=True, message=descr[:200] or "SNMP menjawab")
    await log_activity(db, action="olt.test_connection", entity_type="olt", success=False,
                       user_id=user.id, raw_command=f"snmpget {OID_SYS_DESCR}",
                       raw_output=message[:500])
    await db.commit()
    return OltTestResult(success=False, message=message[:200])

async def enqueue_olt_job(db: AsyncSession, olt_id: int, job_type: str, user: User) -> int:
    await get_olt(db, olt_id, user)
    job = await job_service.enqueue(db, job_type, olt_id=olt_id, created_by=user.id)
    await db.commit()
    return job.id

async def list_pon_ports(db: AsyncSession, olt_id: int, user: User) -> list[PonPortOut]:
    olt = await get_olt(db, olt_id, user)
    return _pon_ports(olt, await olt_repo.list_pon_ports(db, olt_id))

def _pon_ports(olt: Olt, rows) -> list[PonPortOut]:
    return [
        PonPortOut(id=pon.id, slot=pon.slot, port=pon.port, ifindex=pon.ifindex,
                   oper_state=pon.oper_state, onu_count=count, capacity=olt.max_onu_per_port,
                   last_sync_at=pon.last_sync_at)
        for pon, count in rows
    ]

async def get_detail(db: AsyncSession, olt_id: int, user: User) -> OltDetail:
    """Semua yang dibutuhkan halaman Detail OLT dalam satu query set (PRD 3.4.7).

    Dibaca dari DB saja — nilai kesehatan ditulis job sync_olt_metrics tiap 15 menit,
    halaman tidak pernah menghubungi OLT sendiri.
    """
    olt = await get_olt(db, olt_id, user)
    by_status = await olt_repo.onu_count_by_status(db, olt_id)
    return OltDetail(
        **OltOut.model_validate(olt).model_dump(),
        owner_name=await olt_repo.owner_name(db, olt),
        onu_count=sum(by_status.values()),
        onu_by_status=by_status,
        cpu_pct=olt.cpu_pct,
        ram_pct=olt.ram_pct,
        temperature_c=olt.temperature_c,
        uptime_seconds=olt.uptime_seconds,
        software_version=olt.software_version,
        cards=[OltCardOut(**card) for card in (olt.cards or [])],
        pon_ports=_pon_ports(olt, await olt_repo.list_pon_ports(db, olt_id)),
        uplink_ports=list(olt.uplink_ports or []),
    )
