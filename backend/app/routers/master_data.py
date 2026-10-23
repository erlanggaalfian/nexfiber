from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.onu import SpeedProfileOut, VlanOut
from app.services import dashboard_service, onu_service

router = APIRouter(prefix="/api", tags=["master-data"])

@router.get("/vlans", response_model=list[VlanOut])
async def list_vlans(olt_id: int | None = None, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return await onu_service.list_vlans(db, olt_id, user)

@router.get("/speed-profiles", response_model=list[SpeedProfileOut])
async def list_speed_profiles(olt_id: int | None = None, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    return await onu_service.list_speed_profiles(db, olt_id, user)

@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    return await dashboard_service.summary(db, user)
