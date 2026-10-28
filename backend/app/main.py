from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
    graph_data,
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


@app.exception_handler(PydanticValidationError)
@app.exception_handler(ValueError)
@app.exception_handler(KeyError)
@app.exception_handler(TypeError)
async def input_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Sebelumnya satu-satunya handler adalah AppError, sehingga kesalahan input
    # yang lolos validasi router (mis. body aksi ONU berupa dict bebas, field
    # hilang, tipe salah, atau Pydantic ValidationError dari validasi di service)
    # menjadi 500. Kesalahan-kesalahan ini adalah input/keadaan yang salah dari
    # pemanggil, jadi dipetakan ke 422 dengan pesan yang bisa dibaca — tanpa
    # membocorkan traceback. Ini sengaja TIDAK menangkap bug internal lain
    # (AttributeError, dll.) yang tetap harus 500 dan terlihat di log server.
    return JSONResponse(status_code=422, content={"detail": str(exc) or "Input tidak valid"})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Race/duplikat/FK yang tidak tertangkap guard aplikasi: 409, bukan 500.
    # Pesan sengaja generik supaya detail constraint DB tidak bocor ke klien.
    return JSONResponse(status_code=409, content={"detail": "Data bertentangan dengan data yang sudah ada"})


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
               onu_types, splitters, vlans, speed_profiles, onu_presets, activity_logs,
               graph_data):
    app.include_router(module.router)


@app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def api_not_found(full_path: str) -> JSONResponse:
    # Didaftarkan SETELAH semua router API dan SEBELUM catch-all SPA di bawah:
    # path /api/ yang tidak dikenal sebelumnya jatuh ke SPA dan dibalas 200 +
    # HTML, sehingga klien API yang salah ketik endpoint mengira sukses.
    # Route ini hanya tercapai bila tidak ada router yang cocok.
    return JSONResponse(status_code=404, content={"detail": "Not found"})

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
        # no-cache = browser WAJIB revalidasi tiap muat (ETag 304 kalau sama).
        # Tanpa ini browser menyimpan index.html secara heuristik dan tab SPA
        # lama terus menjalankan bundel basi setelah deploy (bug tabel ghost
        # yang terlihat lagi padahal sudah di-fix, laporan 2026-10-29).
        return FileResponse(FRONTEND_DIST / "index.html",
                            headers={"Cache-Control": "no-cache"})
