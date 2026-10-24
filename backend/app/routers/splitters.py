from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.master_data import SplitterCreate, SplitterDetail, SplitterOut, SplitterUpdate
from app.services import master_data_service as svc

router = APIRouter(prefix="/api/splitters", tags=["splitters"])
manager = require_roles(MANAGERS)  # User hanya baca (PRD 3.7)


@router.get("", response_model=list[SplitterOut])
async def list_splitters(q: str | None = None, zone_id: int | None = None,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    return await svc.list_splitters(db, user, q, zone_id)


@router.post("", response_model=SplitterDetail, status_code=status.HTTP_201_CREATED)
async def create_splitter(body: SplitterCreate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(manager)):
    return await svc.create_splitter(db, body, user)


@router.get("/{splitter_id}", response_model=SplitterDetail)
async def get_splitter(splitter_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return await svc.get_splitter(db, splitter_id, user)


@router.patch("/{splitter_id}", response_model=SplitterDetail)
async def update_splitter(splitter_id: int, body: SplitterUpdate,
                          db: AsyncSession = Depends(get_db), user: User = Depends(manager)):
    return await svc.update_splitter(db, splitter_id, body, user)


@router.delete("/{splitter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_splitter(splitter_id: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(manager)) -> None:
    await svc.delete_splitter(db, splitter_id, user)
