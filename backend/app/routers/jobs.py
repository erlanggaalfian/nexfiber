from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.rbac import scope_olt_ids
from app.core.security import SSE_TOKEN_SECONDS, create_sse_token, decode_sse_token, password_token_claim
from app.models.user import User
from app.schemas.job import JobOut
from app.services import auth_service, job_service

router = APIRouter(tags=["jobs"])


class SseTokenResponse(BaseModel):
    token: str
    expires_in: int

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

@router.post("/api/stream/jobs/token", response_model=SseTokenResponse)
async def issue_sse_token(user: User = Depends(get_current_user)) -> SseTokenResponse:
    """Terbitkan token SSE sekali pakai untuk satu koneksi EventSource.

    Dipanggil dengan token akses di header Authorization (bukan query string),
    lalu frontend memakai token ini di URL EventSource. Berlaku
    SSE_TOKEN_SECONDS detik; saat koneksi pertama dibuka, jti-nya ditandai
    terpakai, sehingga token yang sama tidak bisa dipakai membuka koneksi
    kedua — frontend WAJIB meminta token baru tiap (re)koneksi, bukan memakai
    ulang token lama saat EventSource reconnect otomatis.
    """
    return SseTokenResponse(
        token=create_sse_token(user.id, user.role, user.password_hash),
        expires_in=SSE_TOKEN_SECONDS)


@router.get("/api/stream/jobs")
async def stream_jobs(token: str = Query(""),
                      db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Stream SSE HANYA menerima token SSE sekali pakai (bukan token akses).

    Token akses 8 jam tidak lagi boleh lewat query string URL: ia masuk access
    log/proxy dan bertahan lama bila bocor. Di sini token SSE divalidasi
    (typ=sse, exp, klaim ph vs password_hash, user aktif) dan ditolak bila
    jti-nya sudah terpakai; lalu jti ditandai terpakai SEBELUM stream dimulai.
    Exp HANYA gerbang di sini: validasi ulang di dalam stream (tiap 60 detik)
    memeriksa ph/user/scope lagi, tapi TIDAK memeriksa exp maupun "terpakai" —
    kalau tidak, stream yang sedang berjalan akan membunuh dirinya sendiri
    (tiap 120 detik karena exp). Koneksi kedua dengan token yang sama tetap
    ditolak di gerbang ini.
    """
    try:
        payload = decode_sse_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token SSE tidak valid") from exc
    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak ditemukan atau nonaktif")
    ph = payload.get("ph")
    if ph is not None and ph != password_token_claim(user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token sudah tidak berlaku (password diubah)")
    jti, exp = payload.get("jti"), payload.get("exp")
    if not isinstance(jti, str) or not isinstance(exp, (int, float)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token SSE tidak valid")
    if await auth_service.is_token_jti_recorded(db, auth_service.CONSUMED_SSE_TOKENS_KEY, jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token SSE sudah terpakai")
    await auth_service.record_token_jti(db, auth_service.CONSUMED_SSE_TOKENS_KEY, jti, exp)
    await db.commit()
    # Token mentah diteruskan supaya stream_job_events bisa memvalidasi penuh
    # (decode + exp + klaim ph) dan menghitung ulang scope tiap 60 detik.
    # Tanpa ini, stream hanya mengandalkan user awal yang sudah didecode sekali.
    return StreamingResponse(
        job_service.stream_job_events(scope_olt_ids(user), viewer=user, token=token),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
