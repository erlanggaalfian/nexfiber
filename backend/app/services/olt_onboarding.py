"""Rantai sinkron otomatis satu OLT (PRD 3.1 poin 7 + permintaan pemilik: "tambah OLT,
tunggu, semua data muncul tanpa klik").

Urutan tahap dipakai apa adanya dari job yang SUDAH ADA — tidak ada job_type baru
(nilai enum `job_type` di DB butuh migrasi Alembic, dan itu bukan milik file ini):

    test_connection -> sync_olt_metrics -> sync_speed_profiles -> sync_onu_status
                    -> sync_unconfigured -> (metadata ONU, dihitung dari DB)

Tahap berikutnya hanya diantre kalau tahap sebelumnya `success`; satu tahap `failed`
menghentikan rantai dan alasannya tersimpan supaya frontend bisa menampilkannya.
Retry/backoff tetap milik job queue (`job_repo.mark_failed` + `max_attempts`), jadi
rantai tidak pernah mengulang sendiri tanpa batas.

Progres disimpan di satu baris `settings` per OLT (`olt_sync:<id>`, JSONB) — tabel itu
sudah ada, jadi fitur ini TIDAK butuh migrasi.

Tahap terakhir (`onu_metadata`) murni baca DB: metadata zone/ODP/alamat/VLAN berasal dari
`onus.name`/`onus.description` yang sudah diadopsi `sync_olt_metrics` dan diparse
`onu_device_metadata` saat dibaca — tidak ada koneksi tambahan ke perangkat.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.exceptions import ConflictError
from app.models.job import Job
from app.models.olt import Olt
from app.models.onu import Onu
from app.models.setting import Setting

log = logging.getLogger("nexfiber.onboarding")

KEY_PREFIX = "olt_sync:"
# Rantai ikut di belakang job yang dipicu user (100), tapi di depan sync periodik (200).
CHAIN_PRIORITY = 150
ACTIVE_STATES = ("pending", "running")
# Field yang kalau berubah membuat data lama tidak bisa dipercaya lagi -> sinkron ulang.
RECONNECT_FIELDS = frozenset({
    "host", "cli_port", "cli_protocol", "cli_username", "cli_password",
    "cli_enable_password", "snmp_port", "snmp_community", "snmp_community_rw",
})

# (key, label, job_type) — job_type None = tahap yang dihitung dari DB, bukan job.
STAGES: tuple[tuple[str, str, str | None], ...] = (
    ("test_connection", "Cek koneksi", "test_connection"),
    ("olt_metrics", "Inventaris, optik & kesehatan", "sync_olt_metrics"),
    ("speed_profiles", "Profil kecepatan", "sync_speed_profiles"),
    ("onu_status", "Status ONU", "sync_onu_status"),
    ("onu_unconfigured", "ONU belum terdaftar", "sync_unconfigured"),
    ("onu_metadata", "Metadata ONU (zone/ODP/VLAN)", None),
)


def _count(stage_key: str, result: dict | None) -> int | None:
    """Angka yang pantas ditampilkan per tahap, diambil dari result job apa adanya."""
    if not result:
        return None
    if stage_key == "olt_metrics":
        return (result.get("onus_added") or 0) + (result.get("onus_updated") or 0)
    if stage_key == "onu_status":
        return (result.get("changed") or 0) + (result.get("unchanged_online") or 0)
    if stage_key == "onu_unconfigured":
        return result.get("found")
    if stage_key == "speed_profiles":
        for field in ("found", "added", "profiles"):
            if isinstance(result.get(field), int):
                return result[field]
    return None


def _blank(now: datetime, trigger: str, created_by: int | None = None) -> dict:
    return {
        "run_started_at": now.isoformat(),
        "trigger": trigger,
        "created_by": created_by,
        "state": "pending",
        "updated_at": now.isoformat(),
        "stages": [
            {"key": key, "label": label, "job_type": job_type, "status": "pending",
             "job_id": None, "started_at": None, "finished_at": None,
             "error": None, "count": None}
            for key, label, job_type in STAGES
        ],
    }


async def _load(db: AsyncSession, olt_id: int) -> dict | None:
    row = await db.get(Setting, f"{KEY_PREFIX}{olt_id}")
    return dict(row.value) if row else None


async def _save(db: AsyncSession, olt_id: int, record: dict) -> None:
    record["updated_at"] = datetime.now(UTC).isoformat()
    stmt = insert(Setting).values(
        key=f"{KEY_PREFIX}{olt_id}", value=record,
        description="Progres rantai sinkron otomatis OLT",
    )
    await db.execute(stmt.on_conflict_do_update(
        index_elements=[Setting.key],
        set_={"value": record, "updated_at": datetime.now(UTC)},
    ))


async def _existing_job_id(db: AsyncSession, olt_id: int, job_type: str) -> int | None:
    return await db.scalar(
        select(Job.id).where(Job.olt_id == olt_id, Job.job_type == job_type,
                             Job.status.in_(ACTIVE_STATES)).order_by(Job.id.desc()).limit(1)
    )


async def _enqueue_stage(db: AsyncSession, olt_id: int, stage: dict,
                         created_by: int | None) -> None:
    """Antre job satu tahap. Kalau job sejenis untuk OLT ini masih pending/running, pakai
    job itu dan jangan bikin kedua — itu yang membuat rantai idempoten saat dipanggil
    dobel. (`test_connection` dan `sync_speed_profiles` TIDAK tercakup partial unique
    index `uq_jobs_sync_pending_per_olt`, jadi pemeriksaannya harus di sini.)
    """
    from app.services import job_service

    existing = await _existing_job_id(db, olt_id, stage["job_type"])
    if existing is not None:
        stage["job_id"] = existing
    else:
        try:
            job = await job_service.enqueue(
                db, stage["job_type"], olt_id=olt_id, priority=CHAIN_PRIORITY,
                created_by=created_by,
            )
            stage["job_id"] = job.id
        except ConflictError:
            stage["job_id"] = await _existing_job_id(db, olt_id, stage["job_type"])
    stage["status"] = "running"
    stage["started_at"] = datetime.now(UTC).isoformat()


async def start_chain(db: AsyncSession, olt_id: int, *, trigger: str,
                      created_by: int | None = None) -> dict:
    """Mulai (atau lanjutkan) rantai untuk satu OLT. Idempoten: panggilan kedua saat
    rantai masih jalan tidak membuat job baru, hanya mengembalikan progres yang ada.
    Caller yang commit.
    """
    record = await _load(db, olt_id)
    if record and record.get("state") in ACTIVE_STATES:
        return record
    record = _blank(datetime.now(UTC), trigger, created_by)
    record["state"] = "running"
    await _enqueue_stage(db, olt_id, record["stages"][0], created_by)
    await _save(db, olt_id, record)
    return record


async def _metadata_count(db: AsyncSession, olt_id: int) -> int:
    """ONU yang punya teks metadata perangkat (name/description) — sumber zone/ODP/alamat."""
    return await db.scalar(
        select(func.count(Onu.id)).where(
            Onu.olt_id == olt_id, Onu.deleted_at.is_(None),
            or_(Onu.name.isnot(None), Onu.description.isnot(None)),
        )
    ) or 0


async def _advance_one(db: AsyncSession, olt_id: int, record: dict) -> bool:
    """Satu langkah maju. True kalau record berubah dan perlu disimpan."""
    for stage in record["stages"]:
        if stage["status"] in ("success", "skipped"):
            continue
        if stage["status"] == "failed":
            return False
        if stage["job_type"] is None:  # tahap metadata: cukup baca DB
            stage["count"] = await _metadata_count(db, olt_id)
            stage["status"] = "success"
            stage["finished_at"] = datetime.now(UTC).isoformat()
            continue
        if stage["job_id"] is None:
            await _enqueue_stage(db, olt_id, stage, record.get("created_by"))
            return True
        job = await db.get(Job, stage["job_id"])
        if job is None:  # job hilang (dihapus manual): anggap tahap gagal, jangan diam
            stage["status"], stage["error"] = "failed", "job tidak ditemukan"
            record["state"] = "failed"
            return True
        if job.status in ACTIVE_STATES:
            return False
        if job.status != "success":
            stage["status"] = "failed"
            stage["error"] = (job.error_message or job.status)[:300]
            stage["finished_at"] = (job.finished_at or datetime.now(UTC)).isoformat()
            record["state"] = "failed"
            return True
        stage["status"] = "success"
        stage["count"] = _count(stage["key"], job.result)
        stage["finished_at"] = (job.finished_at or datetime.now(UTC)).isoformat()
    record["state"] = "failed" if any(
        s["status"] == "failed" for s in record["stages"]) else "success"
    return True


async def advance_chain(db: AsyncSession, olt_id: int) -> dict | None:
    """Majukan rantai satu OLT sejauh mungkin dalam satu panggilan. Caller yang commit."""
    record = await _load(db, olt_id)
    if record is None or record["state"] not in ACTIVE_STATES:
        return record
    changed = False
    while await _advance_one(db, olt_id, record):
        changed = True
        if record["state"] not in ACTIVE_STATES:
            break
    if changed:
        await _save(db, olt_id, record)
    return record


async def advance_active_chains() -> None:
    """Dipanggil scheduler worker tiap beberapa detik: majukan semua rantai yang jalan."""
    async with SessionLocal() as db:
        keys = (await db.execute(
            select(Setting.key).where(Setting.key.like(f"{KEY_PREFIX}%"))
        )).scalars().all()
    for key in keys:
        olt_id = int(key.removeprefix(KEY_PREFIX))
        async with SessionLocal() as db:
            try:
                await advance_chain(db, olt_id)
                await db.commit()
            except Exception:  # satu OLT bermasalah tidak boleh menghentikan yang lain
                await db.rollback()
                log.exception("gagal memajukan rantai sinkron OLT %s", olt_id)


def status_payload(olt: Olt, record: dict | None) -> dict:
    """Bentuk jawaban GET /api/olts/{id}/sync-status (kontrak frontend oltSync.ts)."""
    if record is None:
        record = _blank(olt.created_at or datetime.now(UTC), "none")
        record["state"] = "pending"
        record["updated_at"] = None
    return {
        "olt_id": olt.id,
        "state": record["state"],
        "trigger": record.get("trigger"),
        "updated_at": record.get("updated_at"),
        "stages": [
            {"key": s["key"], "label": s["label"], "status": s["status"],
             "started_at": s["started_at"], "finished_at": s["finished_at"],
             "error": s["error"], "count": s["count"], "job_id": s["job_id"]}
            for s in record["stages"]
        ],
    }
