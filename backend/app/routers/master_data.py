from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api", tags=["master-data"])

# GET /api/vlans pindah ke routers/vlans.py dan GET /api/speed-profiles ke
# routers/speed_profiles.py (Fase B4) — satu definisi per endpoint, jangan dua.

@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    return await dashboard_service.summary(db, user)
