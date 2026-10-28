"""Job enqueue/status (PRD 4.5.A: callers never know the queue implementation, only call
enqueue()). enqueue() does NOT commit â€” it must ride the caller's transaction so "create ONU
+ enqueue provisioning job" is one atomic commit, per the PRD's core argument for choosing
a DB-table queue over Celery+Redis.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.rbac import MANAGERS, Scope, scope_olt_ids, scoped
from app.core.security import decode_sse_token, password_token_claim
from app.models.job import Job
from app.models.user import User
from app.repositories import job_repo
from app.schemas.job import JobOut

# Job level OLT yang rawan menumpuk dari klik berulang: satu job aktif per OLT
# sudah cukup; job kedua dengan payload lebih lama tidak boleh mengantre dan
# menang atas job yang lebih baru. Cek ini ada di enqueue pusat supaya semua
# jalur (API, VLAN, speed profile) tertutup tanpa mengubah file-file itu.
OLT_LEVEL_SINGLE_ACTIVE = {
    "set_vlan_ports", "set_port_config", "push_speed_profile",
    "sync_speed_profiles", "test_connection", "backup_olt_config",
}

# Hasil job yang memuat kredensial pelanggan dan hanya boleh dibaca manager:
# refresh_onu_detail mengembalikan running_config utuh, diagnostik running
# mengembalikan output running-config utuh. Pembaca non-manager tetap boleh
# melihat status job dan field lain, tapi bukan isi sensitifnya.
_SENSITIVE_JOB_TYPES = {"refresh_onu_detail", "read_onu_running_config"}


def redact_job(job: Job, viewer: User | None) -> JobOut:
    """JobOut dengan hasil sensitif disensor untuk non-manager.

    Dipakai di get/list/stream supaya gate role tidak hanya ada saat enqueue
    (diagnostik running) tapi juga saat MEMBACA hasil — sebelumnya user biasa
    cukup menebak job_id job manager untuk membaca running-config.
    """
    out = JobOut.model_validate(job)
    if viewer is not None and viewer.role in MANAGERS:
        return out
    if job.job_type in _SENSITIVE_JOB_TYPES and out.result:
        result = dict(out.result)
        result.pop("running_config", None)
        if job.job_type == "read_onu_running_config":
            result["output"] = None
        out = out.model_copy(update={"result": result})
    return out


async def enqueue(
    db: AsyncSession,
    job_type: str,
    *,
    olt_id: int | None = None,
    onu_id: int | None = None,
    payload: dict | None = None,
    priority: int = 100,
    created_by: int | None = None,
    max_attempts: int = 3,
) -> Job:
    """Insert a pending job. Does not commit â€” caller's transaction decides.

    For sync_* job types the partial unique index (uq_jobs_sync_pending_per_olt) is the only
    anti-pileup check (PRD 4.4: "scheduler tidak membuat job baru bila job sejenis ... masih
    pending/running") — we don't duplicate that check here, we just surface the resulting
    unique violation as a ConflictError so the scheduler can skip it quietly. Index kedua
    (uq_jobs_active_per_onu) melakukan hal sama untuk job per ONU, jadi dua proses yang
    menekan tombol sama bersamaan tetap menghasilkan tepat satu job.
    """
    if job_type in OLT_LEVEL_SINGLE_ACTIVE and olt_id is not None:
        # Cek eksplisit sebelum INSERT: index partial hanya menutupi sync_* dan
        # job per ONU, sedangkan tipe-tipe ini sebelumnya bisa menumpuk tanpa batas.
        if await job_repo.exists_active_for_olt(db, olt_id, job_type):
            raise ConflictError(f"Job {job_type} untuk OLT ini masih pending/running")
    job = Job(
        job_type=job_type,
        olt_id=olt_id,
        onu_id=onu_id,
        payload=payload or {},
        priority=priority,
        created_by=created_by,
        max_attempts=max_attempts,
        run_after=datetime.now(UTC),
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Rollback SEBELUM raise: tanpa ini sesi pemanggil "teracuni"
        # (PendingRollbackError pada query berikutnya) dan pemanggil yang
        # menangkap ConflictError lalu melanjutkan transaksi akan meledak
        # di tempat yang tidak berhubungan. Objek job yang gagal dibuang
        # dari sesi supaya tidak ikut ter-flush lagi.
        await db.rollback()
        db.expunge(job)
        raise ConflictError(
            f"Job {job_type} untuk target ini masih pending/running"
        ) from exc
    return job

async def get_job(db: AsyncSession, job_id: int, scope: Scope,
                  viewer: User | None = None) -> Job:
    job = await db.scalar(scoped(select(Job).where(Job.id == job_id), Job.olt_id, scope))
    if job is None:
        raise NotFoundError("Job not found")
    return job

async def list_jobs(
    db: AsyncSession,
    scope: Scope,
    *,
    status: str | None = None,
    olt_id: int | None = None,
    onu_id: int | None = None,
    limit: int = 50,
) -> list[Job]:
    stmt = scoped(select(Job).order_by(Job.id.desc()).limit(limit), Job.olt_id, scope)
    if status:
        stmt = stmt.where(Job.status == status)
    if olt_id:
        stmt = stmt.where(Job.olt_id == olt_id)
    if onu_id:
        stmt = stmt.where(Job.onu_id == onu_id)
    return list((await db.execute(stmt)).scalars().all())

async def cancel_job(db: AsyncSession, job_id: int, scope: Scope,
                     viewer: User | None = None) -> Job:
    job = await get_job(db, job_id, scope)
    # Pembuat job, atau manager/superadmin. Job sistem (created_by IS NULL)
    # HANYA boleh dibatalkan manager: sebelumnya siapa saja dalam scope bisa
    # membatalkan job sistem (scheduler/sinkronisasi), karena created_by None
    # lolos dari cek "bukan pembuat".
    if viewer is not None and viewer.role not in MANAGERS \
            and (job.created_by is None or job.created_by != viewer.id):
        raise ForbiddenError("Hanya pembuat job atau manager yang bisa membatalkannya")
    if job.status not in ("pending",):
        raise ConflictError(f"Cannot cancel a job in status '{job.status}'")
    job.status = "cancelled"
    job.finished_at = datetime.now(UTC)
    await db.commit()
    return job


STREAM_INTERVAL_S = 1.0
# updated_at = now() = transaction START, so a row can commit with a timestamp already behind
# the cursor. Re-read this window each tick and dedupe. Matches the worker's STALE_AFTER:
# a job running longer than that is requeued anyway.
STREAM_OVERLAP = timedelta(minutes=15)

async def _changed_since(since: datetime, scope: Scope) -> list[Job]:
    # Fresh short session per tick: a stream must not hold one transaction open for hours.
    async with SessionLocal() as db:
        stmt = select(Job).where(Job.updated_at > since).order_by(Job.updated_at).limit(500)
        stmt = scoped(stmt, Job.olt_id, scope)
        return list((await db.execute(stmt)).scalars().all())


async def _stream_viewer(user_id: int) -> User | None:
    """Validasi ulang pemilik token SSE secara berkala (fallback tanpa token).

    Dipakai bila stream dipanggil tanpa token mentah: user dibaca ulang dari
    DB; bila sudah tidak aktif/terhapus, stream berhenti. Bila token mentah
    tersedia, _revalidate_stream_token dipakai sebagai gantinya (lebih ketat).
    Sisa risiko yang TIDAK tertutup di sini: token tetap dikirim lewat query
    string URL (masuk access log/proxy) — itu keterbatasan EventSource yang
    tidak bisa mengirim header Authorization, dan butuh token SSE khusus
    berumur pendek untuk benar-benar menutupnya.
    """
    async with SessionLocal() as db:
        return await db.get(User, user_id)


async def _revalidate_stream_token(token: str) -> tuple[User | None, Scope]:
    """Validasi penuh token SSE: decode token SSE (typ=sse, termasuk exp),
    user dari DB, klaim ph.

    Mengembalikan (user_segara, scope_segara) atau (None, scope_lama) bila
    validasi gagal — pemanggil harus menghentikan stream. Scope dihitung ulang
    dari user segar, supaya perubahan kepemilikan/akses OLT di tengah koneksi
    langsung berlaku, bukan scope saat koneksi dibuka. Sengaja TIDAK memeriksa
    "terpakai": token ini sudah ditandai terpakai saat koneksi dibuka, dan
    pemeriksaan itu hanya berlaku di gerbang pembuka koneksi (jobs.py) —
    kalau diperiksa di sini, stream yang sedang berjalan akan berhenti sendiri.
    Token akses biasa ditolak di sini (decode_sse_token memeriksa typ).
    """
    try:
        payload = decode_sse_token(token)
        user_id = int(payload["sub"])
    except Exception:
        return None, None
    async with SessionLocal() as db:
        user = await db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None, None
    ph = payload.get("ph")
    if ph is not None and ph != password_token_claim(user.password_hash):
        return None, None
    return user, scope_olt_ids(user)


async def stream_job_events(scope: Scope, viewer: User | None = None,
                            token: str | None = None) -> AsyncIterator[str]:
    """SSE frames for every job whose row changed (PRD 4.5.C). DB polling, no LISTEN/NOTIFY."""
    started = datetime.now(UTC)
    sent: dict[tuple[int, datetime], datetime] = {}
    ticks = 0
    while True:
        ticks += 1
        if viewer is not None and ticks % 60 == 1 and ticks > 1:
            if token:
                fresh, fresh_scope = await _revalidate_stream_token(token)
                if fresh is None:
                    return
                viewer, scope = fresh, fresh_scope
            else:
                fresh = await _stream_viewer(viewer.id)
                if fresh is None or not fresh.is_active or fresh.deleted_at is not None:
                    return
                viewer = fresh
        cutoff = datetime.now(UTC) - STREAM_OVERLAP
        new = False
        for job in await _changed_since(max(started, cutoff), scope):
            if (job.id, job.updated_at) in sent:
                continue
            sent[(job.id, job.updated_at)] = job.updated_at
            new = True
            yield f"event: job\ndata: {redact_job(job, viewer).model_dump_json()}\n\n"
        sent = {k: t for k, t in sent.items() if t > cutoff}
        if not new:
            yield ": ping\n\n"
        await asyncio.sleep(STREAM_INTERVAL_S)
