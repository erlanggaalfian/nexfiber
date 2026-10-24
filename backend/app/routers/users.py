from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.repositories import olt_repo
from app.schemas.user import OltAccessIds, TempPassword, UserCreate, UserOut, UserUpdate
from app.services import olt_service, user_service

router = APIRouter(prefix="/api/users", tags=["users"])
# Role "user" never reaches this page (PRD 3.7): the gate answers 403 on every endpoint.
manager = require_roles(MANAGERS)

@router.get("", response_model=list[UserOut])
async def list_users(role: str | None = Query(None, pattern="^(superadmin|admin|user)$"),
                     db: AsyncSession = Depends(get_db), actor: User = Depends(manager)):
    return await user_service.list_users(db, actor, role)

@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db),
                      actor: User = Depends(manager)):
    return await user_service.create_user(db, body, actor)

@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db),
                   actor: User = Depends(manager)):
    return await user_service.get_user(db, user_id, actor)

@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db),
                      actor: User = Depends(manager)):
    return await user_service.update_user(db, user_id, body, actor)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db),
                      actor: User = Depends(manager)) -> None:
    """Soft-delete; activate/deactivate goes through PATCH {"is_active": true|false}."""
    await user_service.delete_user(db, user_id, actor)

@router.get("/{user_id}/olt-access", response_model=OltAccessIds)
async def get_olt_access(user_id: int, db: AsyncSession = Depends(get_db),
                         actor: User = Depends(manager)):
    """OLT yang dibagikan ke user ini (olt_access), untuk checklist User Management."""
    await user_service.get_user(db, user_id, actor)
    return OltAccessIds(olt_ids=await olt_repo.access_olt_ids(db, user_id))

@router.put("/{user_id}/olt-access", response_model=OltAccessIds)
async def set_olt_access(user_id: int, body: OltAccessIds, db: AsyncSession = Depends(get_db),
                         actor: User = Depends(manager)):
    """Superadmin-only (dicek di olt_service, aturan sama dengan akses bersama per OLT)."""
    await user_service.get_user(db, user_id, actor)
    return OltAccessIds(olt_ids=await olt_service.set_user_access(db, user_id, body.olt_ids, actor))

@router.post("/{user_id}/reset-password", response_model=TempPassword)
async def reset_password(user_id: int, db: AsyncSession = Depends(get_db),
                         actor: User = Depends(manager)):
    return TempPassword(password=await user_service.reset_password(db, user_id, actor))
