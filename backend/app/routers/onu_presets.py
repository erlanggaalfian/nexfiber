from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.master_data import OnuPresetCreate, OnuPresetOut
from app.services import master_data_service as svc

router = APIRouter(prefix="/api/onu-presets", tags=["onu-presets"])
manager = require_roles(MANAGERS)  # User hanya baca (PRD 3.7)


@router.get("", response_model=list[OnuPresetOut])
async def list_presets(db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return await svc.list_presets(db, user)


@router.post("", response_model=OnuPresetOut, status_code=status.HTTP_201_CREATED)
async def create_preset(body: OnuPresetCreate, db: AsyncSession = Depends(get_db),
                        user: User = Depends(manager)):
    return await svc.create_preset(db, body, user)


@router.patch("/{preset_id}", response_model=OnuPresetOut)
async def update_preset(preset_id: int, body: OnuPresetCreate,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(manager)):
    # Tidak ada skema parsial di repo: edit mengirim OnuPresetCreate penuh,
    # sama seperti create (UI edit mengisi semua field dari baris lama).
    return await svc.update_preset(db, preset_id, body, user)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(preset_id: int, db: AsyncSession = Depends(get_db),
                        user: User = Depends(manager)) -> None:
    await svc.delete_preset(db, preset_id, user)
