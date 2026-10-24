from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.core.rbac import scope_olt_ids, scoped
from app.models.job import Job
from app.models.setting import Setting
from app.models.user import User
from app.repositories import olt_repo
from app.routers import (
    activity_logs,
    auth,
    jobs,
    master_data,
    olts,
    onu_actions,
    onu_by_id,
    onu_presets,
    onu_traffic,
    onu_types,
    onus,
    speed_profiles,
    splitters,
    users,
    vlans,
    zones,
)

WORKER_ALIVE = timedelta(minutes=2)

app = FastAPI(title="Nexfiber API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/api/system/status")
async def system_status(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """PRD 3.3 header indicator + popover. Worker alive = heartbeat < 2 min (c12)."""
    hb = await db.get(Setting, "worker_heartbeat")
    last = hb.updated_at if hb else None
    scope = scope_olt_ids(user)
    queued = scoped(select(func.count(Job.id)).where(Job.status == "pending"), Job.olt_id, scope)
    return {
        "worker_alive": last is not None and datetime.now(UTC) - last < WORKER_ALIVE,
        "worker_heartbeat_at": last,
        "jobs_pending": await db.scalar(queued),
        "last_poll_at": await olt_repo.last_sync_at(db, scope),
    }


# onu_actions sebelum onus: path /{onu_id}/... tidak boleh ketelan /{serial} di onus.py.
for module in (auth, olts, onu_by_id, onu_actions, onu_traffic, onus, jobs, master_data,
               users, zones,
               onu_types, splitters, vlans, speed_profiles, onu_presets, activity_logs):
    app.include_router(module.router)

# ponytail: sajikan frontend build dari API sendiri, satu port saja, no nginx/caddy.
# skipped: CDN/edge caching terpisah, add kalau trafik butuh itu.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
