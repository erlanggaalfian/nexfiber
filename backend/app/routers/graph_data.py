from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.graph_data import (
    GraphDeleteRequest,
    GraphDeleteResult,
    GraphRetention,
    GraphStat,
)
from app.services import graph_data_service as svc

router = APIRouter(prefix="/api/settings/graph-data", tags=["graph-data"])
manager = require_roles(MANAGERS)  # User tidak boleh menghapus histori (PRD 3.7)


@router.get("/stats", response_model=list[GraphStat])
async def stats(db: AsyncSession = Depends(get_db), user: User = Depends(manager)):
    return await svc.stats(db, user)


@router.get("/retention", response_model=GraphRetention)
async def get_retention(db: AsyncSession = Depends(get_db), user: User = Depends(manager)):
    return await svc.get_retention(db)


@router.put("/retention", response_model=GraphRetention)
async def put_retention(body: GraphRetention, db: AsyncSession = Depends(get_db),
                        user: User = Depends(manager)):
    result = await svc.set_retention(db, body, user)
    await db.commit()
    return result


@router.post("/preview-delete", response_model=GraphDeleteResult)
async def preview_delete(body: GraphDeleteRequest, db: AsyncSession = Depends(get_db),
                         user: User = Depends(manager)):
    return await svc.preview_delete(db, body, user)


@router.post("/delete", response_model=GraphDeleteResult)
async def delete_range(body: GraphDeleteRequest, db: AsyncSession = Depends(get_db),
                       user: User = Depends(manager)):
    result = await svc.delete_range(db, body, user)
    await db.commit()
    return result
