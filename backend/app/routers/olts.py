from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.olt import JobAccepted, OltCreate, OltOut, OltUpdate, PonPortOut
from app.services import olt_service

router = APIRouter(prefix="/api/olts", tags=["olts"])
admin = require_roles(MANAGERS)

@router.get("", response_model=list[OltOut])
async def list_olts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await olt_service.list_olts(db, user)

@router.post("", response_model=OltOut, status_code=status.HTTP_201_CREATED)
async def create_olt(body: OltCreate, db: AsyncSession = Depends(get_db),
                     user: User = Depends(admin)):
    return await olt_service.create_olt(db, body, user)

@router.get("/{olt_id}", response_model=OltOut)
async def get_olt(olt_id: int, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return await olt_service.get_olt(db, olt_id, user)

@router.patch("/{olt_id}", response_model=OltOut)
async def update_olt(olt_id: int, body: OltUpdate, db: AsyncSession = Depends(get_db),
                     user: User = Depends(admin)):
    return await olt_service.update_olt(db, olt_id, body, user)

@router.delete("/{olt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_olt(olt_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(admin)) -> None:
    await olt_service.delete_olt(db, olt_id, user)

@router.get("/{olt_id}/pon-ports", response_model=list[PonPortOut])
async def list_pon_ports(olt_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    return await olt_service.list_pon_ports(db, olt_id, user)

@router.post("/{olt_id}/test", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def test_connection(olt_id: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(admin)):
    job_id = await olt_service.enqueue_olt_job(db, olt_id, "test_connection", user)
    return JobAccepted(job_id=job_id)

@router.post("/{olt_id}/backup", response_model=JobAccepted,
             status_code=status.HTTP_202_ACCEPTED)
async def backup_config(olt_id: int, db: AsyncSession = Depends(get_db),
                        user: User = Depends(admin)):
    job_id = await olt_service.enqueue_olt_job(db, olt_id, "backup_olt_config", user)
    return JobAccepted(job_id=job_id)
