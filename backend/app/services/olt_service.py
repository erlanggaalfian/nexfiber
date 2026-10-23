"""OLT CRUD + OLT-level jobs. Any contact with the OLT goes through the job queue (PRD 4.2)."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.rbac import MANAGERS, SUPERADMIN, scope_olt_ids
from app.core.security import encrypt_secret
from app.models.olt import Olt
from app.models.user import User
from app.repositories import olt_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.olt import OltCreate, OltUpdate, PonPortOut
from app.services import job_service

SECRET_FIELDS = {
    "cli_password": "cli_password_enc",
    "cli_enable_password": "cli_enable_password_enc",
    "snmp_community": "snmp_community_enc",
    "snmp_community_rw": "snmp_community_rw_enc",
}

async def get_olt(db: AsyncSession, olt_id: int, user: User) -> Olt:
    olt = await olt_repo.get_active(db, olt_id, scope_olt_ids(user))
    if olt is None:
        raise NotFoundError(f"OLT {olt_id} not found")
    return olt

async def list_olts(db: AsyncSession, user: User) -> list[Olt]:
    return await olt_repo.list_active(db, scope_olt_ids(user))

async def _owner_id(db: AsyncSession, body: OltCreate, user: User) -> int:
    if user.role != SUPERADMIN or body.owner_id is None:
        return user.id
    owner = await db.get(User, body.owner_id)
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
    olt = Olt(owner_id=await _owner_id(db, body, user))
    _apply(olt, body.model_dump(exclude={"owner_id"}))
    db.add(olt)
    await _flush(db)
    await log_activity(db, action="olt.create", entity_type="olt", entity_id=str(olt.id),
                       success=True, user_id=user.id, olt_id=olt.id)
    return await _commit(db, olt)

async def update_olt(db: AsyncSession, olt_id: int, body: OltUpdate, user: User) -> Olt:
    olt = await get_olt(db, olt_id, user)
    _apply(olt, body.model_dump(exclude_unset=True))
    await _flush(db)
    await log_activity(db, action="olt.update", entity_type="olt", entity_id=str(olt.id),
                       success=True, user_id=user.id, olt_id=olt.id,
                       after=body.model_dump(exclude_unset=True, exclude=set(SECRET_FIELDS),
                                             mode="json"))
    return await _commit(db, olt)

async def delete_olt(db: AsyncSession, olt_id: int, user: User) -> None:
    olt = await get_olt(db, olt_id, user)
    olt.deleted_at = datetime.now(UTC)
    olt.is_active = False
    await log_activity(db, action="olt.delete", entity_type="olt", entity_id=str(olt.id),
                       success=True, user_id=user.id, olt_id=olt.id)
    await db.commit()

async def enqueue_olt_job(db: AsyncSession, olt_id: int, job_type: str, user: User) -> int:
    await get_olt(db, olt_id, user)
    job = await job_service.enqueue(db, job_type, olt_id=olt_id, created_by=user.id)
    await db.commit()
    return job.id

async def list_pon_ports(db: AsyncSession, olt_id: int, user: User) -> list[PonPortOut]:
    olt = await get_olt(db, olt_id, user)
    return [
        PonPortOut(id=pon.id, slot=pon.slot, port=pon.port, ifindex=pon.ifindex,
                   oper_state=pon.oper_state, onu_count=count, capacity=olt.max_onu_per_port,
                   last_sync_at=pon.last_sync_at)
        for pon, count in await olt_repo.list_pon_ports(db, olt_id)
    ]
