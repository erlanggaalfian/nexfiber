from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import SUPERADMIN
from app.models.user import User
from app.schemas.master_data import OnuTypeCreate, OnuTypeOut, OnuTypeUpdate
from app.services import master_data_service as svc

router = APIRouter(prefix="/api/onu-types", tags=["onu-types"])
superadmin = require_roles({SUPERADMIN})  # katalog global: tulis hanya Superadmin (PRD 3.7)


@router.get("", response_model=list[OnuTypeOut])
async def list_onu_types(q: str | None = None, active_only: bool = False,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    return await svc.list_onu_types(db, q, active_only)


@router.post("", response_model=OnuTypeOut, status_code=status.HTTP_201_CREATED)
async def create_onu_type(body: OnuTypeCreate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(superadmin)):
    return await svc.create_onu_type(db, body, user)


@router.get("/{type_id}", response_model=OnuTypeOut)
async def get_onu_type(type_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return await svc.get_onu_type(db, type_id)


@router.patch("/{type_id}", response_model=OnuTypeOut)
async def update_onu_type(type_id: int, body: OnuTypeUpdate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(superadmin)):
    return await svc.update_onu_type(db, type_id, body, user)


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_onu_type(type_id: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(superadmin)) -> None:
    await svc.delete_onu_type(db, type_id, user)
