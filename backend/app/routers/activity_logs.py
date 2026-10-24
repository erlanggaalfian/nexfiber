from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.activity_log import LogCategory, LogPage
from app.services import activity_log_service

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=LogPage)
async def list_logs(
    q: str | None = None,
    olt_id: int | None = None,
    user_id: int | None = None,
    category: LogCategory | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await activity_log_service.search_logs(
        db, user, q=q, olt_id=olt_id, user_id=user_id, category=category,
        since=since, until=until, page=page, size=size,
    )
