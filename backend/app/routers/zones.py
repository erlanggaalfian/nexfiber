from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.master_data import ZoneCreate, ZoneOut, ZoneUpdate
from app.services import master_data_service as svc

router = APIRouter(prefix="/api/zones", tags=["zones"])
manager = require_roles(MANAGERS)  # User hanya baca (PRD 3.7)


@router.get("", response_model=list[ZoneOut])
async def list_zones(q: str | None = None, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return await svc.list_zones(db, user, q)


@router.post("", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
async def create_zone(body: ZoneCreate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(manager)):
    return await svc.create_zone(db, body, user)


@router.get("/{zone_id}", response_model=ZoneOut)
async def get_zone(zone_id: int, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return await svc.get_zone(db, zone_id, user)


@router.patch("/{zone_id}", response_model=ZoneOut)
async def update_zone(zone_id: int, body: ZoneUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(manager)):
    return await svc.update_zone(db, zone_id, body, user)


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(zone_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(manager)) -> None:
    await svc.delete_zone(db, zone_id, user)
