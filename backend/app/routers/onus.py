from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.olt import JobAccepted
from app.schemas.onu import (
    AuthorizeBody,
    OnuDetail,
    OnuLog,
    OnuPage,
    PendingOnu,
    SignalPoint,
    SpeedProfileBody,
    StateBody,
)
from app.services import onu_service

router = APIRouter(prefix="/api/onus", tags=["onus"])
ACCEPTED = {"response_model": JobAccepted, "status_code": status.HTTP_202_ACCEPTED}

@router.get("", response_model=OnuPage)
async def list_onus(
    q: str | None = None,
    olt_id: int | None = None,
    pon_port_id: int | None = None,
    state: Literal["online", "down", "rx_warn", "not_configured"] | None = None,
    speed_profile_id: int | None = None,
    sort: str = "serial",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await onu_service.search_onus(
        db, user, q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
        speed_profile_id=speed_profile_id, sort=sort, page=page, size=size,
    )
    return OnuPage(items=items, total=total, page=page, size=size)

@router.get("/pending", response_model=list[PendingOnu])
async def list_pending(olt_id: int | None = None, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return await onu_service.list_pending(db, olt_id, user)

@router.get("/customer-id-taken")
async def customer_id_taken(customer_id: str, db: AsyncSession = Depends(get_db),
                            _: User = Depends(get_current_user)) -> dict:
    return {"taken": await onu_service.customer_id_taken(db, customer_id)}

@router.post("/authorize", **ACCEPTED)
async def authorize(body: AuthorizeBody, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return JobAccepted(job_id=await onu_service.create_and_enqueue_authorize(db, body, user))

@router.get("/{serial}", response_model=OnuDetail)
async def get_onu(serial: str, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return await onu_service.get_onu(db, serial, user)

@router.get("/{serial}/signal", response_model=list[SignalPoint])
async def signal(serial: str, range: Literal["24h", "7d", "30d"] = "24h",
                 db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await onu_service.signal_history(db, serial, range, user)

@router.get("/{serial}/logs", response_model=list[OnuLog])
async def logs(serial: str, limit: int = Query(100, ge=1, le=500),
               db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await onu_service.onu_logs(db, serial, limit, user)

@router.post("/{serial}/reboot", **ACCEPTED)
async def reboot(serial: str, db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(db, serial, "reboot_onu", user))

@router.post("/{serial}/state", **ACCEPTED)
async def set_state(serial: str, body: StateBody, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    job_id = await onu_service.enqueue_onu_job(db, serial, "set_state", user, body.model_dump())
    return JobAccepted(job_id=job_id)

@router.post("/{serial}/speed-profile", **ACCEPTED)
async def speed_profile(serial: str, body: SpeedProfileBody, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    job_id = await onu_service.enqueue_onu_job(
        db, serial, "apply_speed_profile", user, body.model_dump()
    )
    return JobAccepted(job_id=job_id)

@router.delete("/{serial}", **ACCEPTED)
async def delete(serial: str, db: AsyncSession = Depends(get_db),
                 user: User = Depends(require_roles(MANAGERS))):
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(db, serial, "delete_onu", user))
