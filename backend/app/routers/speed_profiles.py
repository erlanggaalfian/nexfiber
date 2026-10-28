"""Speed Profile endpoints (PRD 3.4.12). User boleh lihat, Admin/Superadmin boleh ubah."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.olt import JobAccepted
from app.schemas.speed_profile import SpeedProfileCreate, SpeedProfileRow, SpeedProfileUpdate
from app.services import speed_profile_service as svc

router = APIRouter(prefix="/api/speed-profiles", tags=["speed-profiles"])
manager = require_roles(MANAGERS)
ACCEPTED = {"response_model": JobAccepted, "status_code": status.HTTP_202_ACCEPTED}


@router.get("", response_model=list[SpeedProfileRow])
async def list_profiles(olt_id: int | None = None, include_inactive: bool = False,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    # include_inactive hanya untuk halaman Settings (mengaktifkan kembali profile
    # nonaktif); dropdown otorisasi tetap memanggil tanpa flag ini (aktif saja).
    return await svc.list_profiles(db, olt_id, user, include_inactive=include_inactive)


@router.post("", response_model=SpeedProfileRow, status_code=status.HTTP_201_CREATED)
async def create_profile(body: SpeedProfileCreate, db: AsyncSession = Depends(get_db),
                         user: User = Depends(manager)):
    return await svc.create_profile(db, body, user)


@router.patch("/{profile_id}", response_model=SpeedProfileRow)
async def update_profile(profile_id: int, body: SpeedProfileUpdate,
                         db: AsyncSession = Depends(get_db), user: User = Depends(manager)):
    return await svc.update_profile(db, profile_id, body, user)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(manager)) -> None:
    await svc.delete_profile(db, profile_id, user)


@router.post("/{profile_id}/push", **ACCEPTED)
async def push_profile(profile_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(manager)):
    return JobAccepted(job_id=await svc.enqueue_push(db, profile_id, user))


@router.post("/sync", **ACCEPTED)
async def sync_profiles(olt_id: int, db: AsyncSession = Depends(get_db),
                        user: User = Depends(manager)):
    return JobAccepted(job_id=await svc.enqueue_sync(db, olt_id, user))
