from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, get_user_from_query_token
from app.models.user import User
from app.schemas.job import JobOut
from app.services import job_service

router = APIRouter(tags=["jobs"])

@router.get("/api/jobs", response_model=list[JobOut])
async def list_jobs(status: str | None = None, olt_id: int | None = None,
                    onu_id: int | None = None, limit: int = Query(50, ge=1, le=200),
                    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await job_service.list_jobs(db, status=status, olt_id=olt_id, onu_id=onu_id,
                                       limit=limit)

@router.get("/api/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return await job_service.get_job(db, job_id)

@router.post("/api/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: int, db: AsyncSession = Depends(get_db),
                     _: User = Depends(get_current_user)):
    return await job_service.cancel_job(db, job_id)

@router.get("/api/stream/jobs")
async def stream_jobs(_: User = Depends(get_user_from_query_token)) -> StreamingResponse:
    return StreamingResponse(
        job_service.stream_job_events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
