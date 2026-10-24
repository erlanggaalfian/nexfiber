"""Rantai onboarding OLT (app/services/olt_onboarding.py) terhadap DB nyata — pola sama
test_olt_management.py.

Yang dibuktikan:
1. OLT baru lewat POST /api/olts langsung punya rantai ter-antre, tahap pertama
   `test_connection`, urutan tahap sesuai STAGES;
2. tahap berikutnya hanya diantre setelah tahap sebelumnya sukses (urutan benar);
3. satu tahap gagal menghentikan rantai (tidak ada job tahap berikutnya);
4. panggilan dobel (`POST /api/olts/{id}/sync-all` dua kali, atau create + sync-all)
   tidak membuat job ganda;
5. GET /api/olts/{id}/sync-status memberi bentuk yang dipakai frontend.

Job yang diantre tes ini SELALU digeser `run_after` ke masa depan dalam transaksi yang
sama sebelum commit, supaya worker nyata tidak pernah mengklaimnya dan tes tidak pernah
menghubungi perangkat.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text, update

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.job import Job
from app.models.olt import Olt
from app.models.setting import Setting
from app.models.user import User
from app.services import olt_onboarding

EXPECTED_KEYS = ["test_connection", "olt_metrics", "speed_profiles", "onu_status",
                 "onu_unconfigured", "onu_metadata"]
EXPECTED_JOB_TYPES = ["test_connection", "sync_olt_metrics", "sync_speed_profiles",
                      "sync_onu_status", "sync_unconfigured"]


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _auth(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}


def _body(tag: str, port: int) -> dict:
    return {"name": f"t_{tag}", "host": "192.0.2.11", "cli_username": "oper",
            "cli_password": "x", "snmp_community": "x", "cli_port": port,
            "pon_port_count": 8}


async def _park_jobs(olt_id: int) -> None:
    """Geser semua job OLT ini jauh ke depan: worker nyata tidak akan mengklaimnya."""
    async with SessionLocal() as db:
        await db.execute(update(Job).where(Job.olt_id == olt_id)
                         .values(run_after=datetime.now(UTC) + timedelta(days=1)))
        await db.commit()


async def _jobs(olt_id: int) -> list[tuple[int, str, str]]:
    async with SessionLocal() as db:
        rows = await db.execute(select(Job.id, Job.job_type, Job.status)
                                .where(Job.olt_id == olt_id).order_by(Job.id))
        return [tuple(r) for r in rows]


async def _finish(job_id: int, status: str, error: str | None = None) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        job.status = status
        job.error_message = error
        job.finished_at = datetime.now(UTC)
        await db.commit()


async def _advance(olt_id: int) -> dict:
    async with SessionLocal() as db:
        record = await olt_onboarding.advance_chain(db, olt_id)
        await db.commit()
    await _park_jobs(olt_id)
    return record


async def test_olt_onboarding_chain() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    port = 20000 + int(tag, 16) % 40000
    async with SessionLocal() as db:
        root = User(username=f"t_{tag}_sa", full_name="T onboarding", password_hash="x",
                    role="superadmin")
        db.add(root)
        await db.commit()
    olt_id = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r_create = await c.post("/api/olts", json=_body(tag, port), headers=_auth(root))
            olt_id = r_create.json()["id"]
            await _park_jobs(olt_id)

            r_status = await c.get(f"/api/olts/{olt_id}/sync-status", headers=_auth(root))
            await _park_jobs(olt_id)
            first = await _jobs(olt_id)

            # (4) dobel panggil: create sudah memulai rantai, sync-all dua kali lagi.
            r_all1 = await c.post(f"/api/olts/{olt_id}/sync-all", headers=_auth(root))
            await _park_jobs(olt_id)
            r_all2 = await c.post(f"/api/olts/{olt_id}/sync-all", headers=_auth(root))
            await _park_jobs(olt_id)
            after_double = await _jobs(olt_id)

        body = r_status.json()
        print("create          :", r_create.status_code)
        print("sync-status     :", r_status.status_code, body["state"],
              [(s["key"], s["status"]) for s in body["stages"]])
        print("jobs setelah create:", first)
        print("jobs setelah 2x sync-all:", after_double)

        assert r_create.status_code == 201
        # (1) rantai langsung ada, tahap pertama test_connection, urutan sesuai STAGES.
        assert r_status.status_code == 200
        assert [s["key"] for s in body["stages"]] == EXPECTED_KEYS
        assert body["state"] == "running"
        assert body["stages"][0]["status"] == "running"
        assert [s["status"] for s in body["stages"][1:]] == ["pending"] * 5
        assert [j[1] for j in first] == ["test_connection"]
        # (4) tidak ada job ganda.
        assert r_all1.status_code == r_all2.status_code == 202
        assert after_double == first

        # (2) urutan maju satu per satu, hanya setelah tahap sebelumnya sukses.
        seen_types = ["test_connection"]
        for step in range(1, 5):
            await _finish((await _jobs(olt_id))[-1][0], "success")
            record = await _advance(olt_id)
            jobs = await _jobs(olt_id)
            seen_types.append(jobs[-1][1])
            print(f"tahap {step} selesai -> antre:", jobs[-1][1],
                  "| state:", record["state"])
            assert len(jobs) == step + 1
            assert record["stages"][step]["status"] == "running"
        assert seen_types == EXPECTED_JOB_TYPES

        # Tahap terakhir (metadata ONU) dihitung dari DB, tanpa job tambahan.
        await _finish((await _jobs(olt_id))[-1][0], "success")
        record = await _advance(olt_id)
        print("rantai selesai  :", record["state"],
              [(s["key"], s["status"], s["count"]) for s in record["stages"]])
        assert record["state"] == "success"
        assert all(s["status"] == "success" for s in record["stages"])
        assert record["stages"][-1]["count"] == 0  # OLT tes tidak punya ONU
        assert len(await _jobs(olt_id)) == 5

        # (3) tahap gagal menghentikan rantai: mulai lagi, gagalkan test_connection.
        async with SessionLocal() as db:
            await db.execute(delete(Setting).where(
                Setting.key == f"{olt_onboarding.KEY_PREFIX}{olt_id}"))
            await db.commit()
        async with SessionLocal() as db:
            await olt_onboarding.start_chain(db, olt_id, trigger="manual")
            await db.commit()
        await _park_jobs(olt_id)
        jobs = await _jobs(olt_id)
        await _finish(jobs[-1][0], "failed", "CLI: timeout | SNMP: timeout")
        record = await _advance(olt_id)
        after_fail = await _jobs(olt_id)
        print("test_connection gagal -> state:", record["state"],
              "| error:", record["stages"][0]["error"], "| jobs:", len(after_fail))
        assert record["state"] == "failed"
        assert record["stages"][0]["status"] == "failed"
        assert "timeout" in record["stages"][0]["error"]
        assert [s["status"] for s in record["stages"][1:]] == ["pending"] * 5
        assert len(after_fail) == len(jobs)  # tidak ada tahap lanjutan yang diantre
        # advance berulang tidak menghidupkan rantai yang sudah gagal.
        await _advance(olt_id)
        assert len(await _jobs(olt_id)) == len(jobs)
    finally:
        async with SessionLocal() as db:
            if olt_id:
                await db.execute(delete(Setting).where(
                    Setting.key == f"{olt_onboarding.KEY_PREFIX}{olt_id}"))
                await db.execute(delete(ActivityLog).where(ActivityLog.olt_id == olt_id))
                await db.execute(delete(Job).where(Job.olt_id == olt_id))
                await db.execute(delete(Olt).where(Olt.id == olt_id))
            await db.execute(delete(ActivityLog).where(ActivityLog.user_id == root.id))
            await db.execute(delete(User).where(User.id == root.id))
            await db.commit()
        await engine.dispose()
