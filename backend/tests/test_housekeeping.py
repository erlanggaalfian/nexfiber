"""Housekeeping terjadwal (housekeeping_service) — TANPA perangkat.

Yang dijaga: purge HANYA baris melewati retensi; job pending/running tidak
pernah dihapus; job yang masih dirujuk activity_log tidak dihapus (FK);
backup terbaru tiap OLT tidak pernah dihapus; purge mencatat satu baris
ringkasan di activity log. Tes DB mengikuti pola test_graph_data: skip bila
Postgres tidak terjangkau.
"""

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.core.db import SessionLocal, engine
from app.models.activity_log import ActivityLog
from app.models.job import Job
from app.models.olt import Olt, OltConfigBackup
from app.models.user import User
from app.services import housekeeping_service as hk


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def test_retention_constants_documented():
    # 365 = PRD (Logs + raw_command 1 tahun). 180/90 = PROVISIONAL (PRD diam,
    # butuh konfirmasi pemilik) — tes ini mengunci angka supaya tidak berubah
    # diam-diam tanpa mengubah dokumen di housekeeping_service.
    assert hk.ACTIVITY_LOG_RETENTION_DAYS == 365
    assert hk.JOB_RETENTION_DAYS == 180
    assert hk.BACKUP_RETENTION_DAYS == 90


@pytest.mark.asyncio
async def test_purge_all_only_expired_unreferenced_non_latest() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:6]
    now = datetime.now(UTC)
    old_log = now - timedelta(days=400)
    old_job = now - timedelta(days=200)
    old_backup = now - timedelta(days=100)
    recent = now - timedelta(days=10)
    async with SessionLocal() as db:
        user = User(username=f"hk_{tag}", full_name=tag, password_hash="x", role="admin")
        db.add(user)
        await db.flush()
        olt_a = Olt(name=f"hk_{tag}_a", host="192.0.2.20", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=user.id, pon_port_count=16,
                    cli_port=20000 + int(tag, 16) % 40000)
        olt_b = Olt(name=f"hk_{tag}_b", host="192.0.2.21", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=user.id, pon_port_count=16,
                    cli_port=20001 + int(tag, 16) % 40000)
        db.add_all([olt_a, olt_b])
        await db.flush()
        log_old = ActivityLog(created_at=old_log, action="hk.old", entity_type="test",
                              success=True, user_id=user.id, olt_id=olt_a.id)
        log_recent = ActivityLog(created_at=recent, action="hk.recent", entity_type="test",
                                 success=True, user_id=user.id, olt_id=olt_a.id)
        job_old = Job(job_type="sync_onu_status", status="success", olt_id=olt_a.id,
                      run_after=old_job, finished_at=old_job)
        job_old_ref = Job(job_type="sync_onu_status", status="failed", olt_id=olt_a.id,
                          run_after=old_job, finished_at=old_job)
        job_pending = Job(job_type="sync_onu_status", status="pending", olt_id=olt_a.id,
                          run_after=old_job)
        db.add_all([log_old, log_recent, job_old, job_old_ref, job_pending])
        await db.flush()
        # Log recent merujuk job_old_ref: job itu harus SELAMAT meski terminal + tua.
        log_recent.job_id = job_old_ref.id
        backup_old = OltConfigBackup(olt_id=olt_a.id, config_text="old",
                                     checksum="a" * 64, size_bytes=3, taken_at=old_backup)
        backup_new = OltConfigBackup(olt_id=olt_a.id, config_text="new",
                                     checksum="b" * 64, size_bytes=3, taken_at=recent)
        backup_only = OltConfigBackup(olt_id=olt_b.id, config_text="only",
                                      checksum="c" * 64, size_bytes=4, taken_at=old_backup)
        db.add_all([backup_old, backup_new, backup_only])
        await db.commit()
        ids = {"user": user.id, "olts": [olt_a.id, olt_b.id],
               "logs": [log_old.id, log_recent.id],
               "jobs": [job_old.id, job_old_ref.id, job_pending.id],
               "backups": [backup_old.id, backup_new.id, backup_only.id]}
    try:
        async with SessionLocal() as db:
            purged = await hk.purge_all(db, now)
            assert purged == {"activity_logs": 1, "jobs": 1, "backups": 1}
            remaining_logs = (await db.execute(select(ActivityLog.id).where(
                ActivityLog.id.in_(ids["logs"])))).scalars().all()
            assert remaining_logs == [ids["logs"][1]]  # hanya log recent
            remaining_jobs = (await db.execute(select(Job.id).where(
                Job.id.in_(ids["jobs"])))).scalars().all()
            assert set(remaining_jobs) == {ids["jobs"][1], ids["jobs"][2]}
            remaining_backups = (await db.execute(select(OltConfigBackup.id).where(
                OltConfigBackup.id.in_(ids["backups"])))).scalars().all()
            assert set(remaining_backups) == {ids["backups"][1], ids["backups"][2]}
            summary = await db.scalar(select(ActivityLog).where(
                ActivityLog.action == "housekeeping.purge").order_by(
                ActivityLog.created_at.desc()))
            assert summary is not None and summary.after["purged"] == purged
            ids["summary"] = summary.id
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OltConfigBackup).where(
                OltConfigBackup.id.in_(ids["backups"])))
            await db.execute(delete(ActivityLog).where(ActivityLog.id.in_(
                ids["logs"] + ([ids["summary"]] if "summary" in ids else []))))
            await db.execute(delete(Job).where(Job.id.in_(ids["jobs"])))
            await db.execute(delete(Olt).where(Olt.id.in_(ids["olts"])))
            await db.execute(delete(User).where(User.id == ids["user"]))
            await db.commit()
