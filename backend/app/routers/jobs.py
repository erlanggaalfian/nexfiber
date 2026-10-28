from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, get_user_from_query_token
from app.core.rbac import scope_olt_ids
from app.models.user import User
from app.schemas.job import JobOut
from app.services import job_service

router = APIRouter(tags=["jobs"])

@router.get("/api/jobs", response_model=list[JobOut])
async def list_jobs(status: str | None = None, olt_id: int | None = None,
                    onu_id: int | None = None, limit: int = Query(50, ge=1, le=200),
                    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    jobs = await job_service.list_jobs(db, scope_olt_ids(user), status=status, olt_id=olt_id,
                                       onu_id=onu_id, limit=limit)
    return [job_service.redact_job(job, user) for job in jobs]

@router.get("/api/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    job = await job_service.get_job(db, job_id, scope_olt_ids(user), viewer=user)
    return job_service.redact_job(job, user)

@router.post("/api/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    job = await job_service.cancel_job(db, job_id, scope_olt_ids(user), viewer=user)
    return job_service.redact_job(job, user)

@router.get("/api/stream/jobs")
async def stream_jobs(user: User = Depends(get_user_from_query_token),
                      token: str = Query("")) -> StreamingResponse:
    # Token mentah diteruskan supaya stream_job_events bisa memvalidasi penuh
    # (decode + exp + klaim ph) dan menghitung ulang scope tiap 60 detik.
    # Tanpa ini, stream hanya mengandalkan user awal yang sudah didecode sekali.
    return StreamingResponse(
        job_service.stream_job_events(scope_olt_ids(user), viewer=user,
                                      token=token or None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
