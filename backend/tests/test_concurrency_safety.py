"""Bukti anti-tabrakan saat banyak proses/worker jalan bersamaan (PRD 4.5.A).

Semua tes di sini memakai DUA sesi DB yang berjalan bersamaan (bukan mock) di Postgres
nyata, karena yang diuji justru perilaku kunci/index di database:

1. claim job: dua worker klaim bersamaan -> tidak pernah dapat job yang sama (SKIP LOCKED).
2. enqueue ganda: dua proses enqueue job sejenis -> tepat satu menang, sisanya ConflictError
   (partial unique index per OLT dan per ONU).
3. upsert ONU sama dari dua proses -> satu baris, bukan dua (ON CONFLICT DO NOTHING).
4. kunci CLI per OLT: OLT sama = berurutan, OLT berbeda = boleh bersamaan.
5. reaper: job 'running' dari worker yang mati dikembalikan; yang percobaannya habis
   ditutup 'failed' supaya tidak berputar selamanya.

Tidak ada perintah apa pun yang dikirim ke perangkat: driver tidak dipakai di sini.
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.core.db import SessionLocal, engine, olt_cli_lock
from app.core.exceptions import ConflictError
from app.models.job import Job
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.user import User
from app.repositories import job_repo
from app.services import job_service


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _fixture(tag: str) -> tuple[int, int, int, int]:
    """Dua OLT + satu PON + satu ONU, semuanya milik user tes. Dikembalikan sebagai id."""
    async with SessionLocal() as db:
        user = User(username=f"c_{tag}", full_name="c", password_hash="x", role="admin")
        db.add(user)
        await db.flush()
        olts = [
            Olt(name=f"c_{tag}_{i}", host=f"192.0.2.{10 + i}", vendor="zte", model="C320",
                cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                owner_id=user.id, pon_port_count=8,
                cli_port=23000 + (int(tag, 16) % 9000) + i)
            for i in (0, 1)
        ]
        db.add_all(olts)
        await db.flush()
        pon = PonPort(olt_id=olts[0].id, slot=1, port=1)
        db.add(pon)
        await db.flush()
        onu = Onu(olt_id=olts[0].id, pon_port_id=pon.id, onu_index=1,
                  serial_number=f"C{tag}", status="unknown", config_state="success")
        db.add(onu)
        await db.commit()
        return olts[0].id, olts[1].id, onu.id, user.id


async def _cleanup(olt_a: int, olt_b: int, user_id: int) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Job).where(Job.olt_id.in_([olt_a, olt_b])))
        await db.execute(delete(Onu).where(Onu.olt_id.in_([olt_a, olt_b])))
        await db.execute(delete(PonPort).where(PonPort.olt_id.in_([olt_a, olt_b])))
        await db.execute(delete(Olt).where(Olt.id.in_([olt_a, olt_b])))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def test_two_workers_never_claim_the_same_job() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_a, olt_b, onu_id, user_id = await _fixture(tag)
    try:
        async with SessionLocal() as db:
            ours = []
            for i in range(6):
                job = Job(job_type="read_onu_status", status="pending", olt_id=olt_a,
                          payload={"n": i}, run_after=datetime.now(UTC))
                db.add(job)
                ours.append(job)
            await db.commit()
            mine = {j.id for j in ours}

        async def worker(name: str) -> list[int]:
            got: list[int] = []
            async with SessionLocal() as db:
                for _ in range(12):
                    job = await job_repo.claim_next(db, name)
                    await db.commit()
                    if job is None:
                        break
                    got.append(job.id)
                    await asyncio.sleep(0)  # beri kesempatan worker lain menyela
            return got

        a, b = await asyncio.gather(worker("w-a"), worker("w-b"))
        assert set(a) & set(b) == set(), "dua worker mengklaim job yang sama"
        # Antrean bisa berisi job tes lain; yang dihitung hanya job milik tes ini,
        # dan job orang lain yang kebetulan terklaim dikembalikan ke pending.
        foreign = [i for i in a + b if i not in mine]
        if foreign:
            async with SessionLocal() as db:
                await db.execute(update(Job).where(Job.id.in_(foreign)).values(
                    status="pending", locked_at=None, locked_by=None, started_at=None,
                    attempts=0))
                await db.commit()
        claimed_mine = [i for i in a + b if i in mine]
        assert sorted(claimed_mine) == sorted(mine)  # semua diklaim, tepat sekali
    finally:
        await _cleanup(olt_a, olt_b, user_id)
        await engine.dispose()


async def test_two_concurrent_enqueues_leave_exactly_one_job() -> None:
    """Satu untuk job sync per OLT, satu untuk job per ONU — keduanya dijaga index."""
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_a, olt_b, onu_id, user_id = await _fixture(tag)
    try:
        async def enqueue(job_type: str, **kw) -> bool:
            async with SessionLocal() as db:
                try:
                    await job_service.enqueue(db, job_type, **kw)
                    await db.commit()
                    return True
                except ConflictError:
                    await db.rollback()
                    return False

        for job_type, kwargs, count_filter in (
            ("sync_onu_status", {"olt_id": olt_a}, Job.olt_id == olt_a),
            ("read_onu_status", {"olt_id": olt_a, "onu_id": onu_id}, Job.onu_id == onu_id),
        ):
            wins = await asyncio.gather(*[enqueue(job_type, **kwargs) for _ in range(4)])
            assert sum(wins) == 1, f"{job_type}: {sum(wins)} enqueue menang, harus 1"
            async with SessionLocal() as db:
                rows = await db.scalar(select(func.count()).select_from(Job).where(
                    Job.job_type == job_type, count_filter,
                    Job.status.in_(("pending", "running")),
                ))
            assert rows == 1, f"{job_type}: {rows} job aktif, harus 1"
    finally:
        await _cleanup(olt_a, olt_b, user_id)
        await engine.dispose()


async def test_concurrent_onu_upsert_makes_one_row() -> None:
    """Dua proses sync mengadopsi ONU yang sama: satu baris, tanpa IntegrityError."""
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_a, olt_b, onu_id, user_id = await _fixture(tag)
    serial = f"DUP{tag}"
    try:
        async with SessionLocal() as db:
            pon_id = await db.scalar(select(PonPort.id).where(PonPort.olt_id == olt_a))

        async def adopt() -> int:
            async with SessionLocal() as db:
                stmt = insert(Onu).values(
                    olt_id=olt_a, pon_port_id=pon_id, onu_index=77, serial_number=serial,
                    auth_type="sn", status="online", config_state="success",
                    admin_state="enabled", registered_at=datetime.now(UTC),
                )
                res = await db.execute(stmt.on_conflict_do_nothing())
                await db.commit()
                return res.rowcount or 0

        inserted = await asyncio.gather(*[adopt() for _ in range(5)])
        assert sum(inserted) == 1, f"{sum(inserted)} insert berhasil, harus 1"
        async with SessionLocal() as db:
            rows = await db.scalar(select(func.count()).select_from(Onu).where(
                Onu.olt_id == olt_a, Onu.serial_number == serial, Onu.deleted_at.is_(None)
            ))
        assert rows == 1
    finally:
        await _cleanup(olt_a, olt_b, user_id)
        await engine.dispose()


async def test_cli_lock_serializes_same_olt_but_not_different_olts() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_a, olt_b, onu_id, user_id = await _fixture(tag)
    try:
        # OLT sama: pemegang pertama menolak yang kedua (tidak menunggu, tidak deadlock).
        async with olt_cli_lock(olt_a) as first:
            assert first is True
            async with olt_cli_lock(olt_a) as second:
                assert second is False, "dua sesi CLI ke OLT yang sama lolos bersamaan"
            # OLT berbeda tetap boleh jalan bersamaan.
            async with olt_cli_lock(olt_b) as other:
                assert other is True
        # Setelah blok selesai kunci harus lepas (koneksi kembali ke pool).
        async with olt_cli_lock(olt_a) as again:
            assert again is True
    finally:
        await _cleanup(olt_a, olt_b, user_id)
        await engine.dispose()


async def test_reaper_requeues_dead_worker_job_and_closes_exhausted() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_a, olt_b, onu_id, user_id = await _fixture(tag)
    old = datetime.now(UTC) - timedelta(hours=2)
    try:
        async with SessionLocal() as db:
            retryable = Job(job_type="backup_olt_config", status="running", olt_id=olt_a,
                            run_after=old, locked_at=old, locked_by="worker-mati",
                            started_at=old, attempts=1, max_attempts=3)
            exhausted = Job(job_type="test_connection", status="running", olt_id=olt_b,
                            run_after=old, locked_at=old, locked_by="worker-mati",
                            started_at=old, attempts=3, max_attempts=3)
            fresh = Job(job_type="read_onu_software", status="running", olt_id=olt_a,
                        run_after=datetime.now(UTC), locked_at=datetime.now(UTC),
                        locked_by="worker-hidup", started_at=datetime.now(UTC), attempts=1)
            db.add_all([retryable, exhausted, fresh])
            await db.commit()
            ids = (retryable.id, exhausted.id, fresh.id)

        async with SessionLocal() as db:
            released = await job_repo.release_stale_locks(db, timedelta(minutes=15))
        assert released == 2  # job segar tidak disentuh

        async with SessionLocal() as db:
            rows = {j.id: j for j in (await db.execute(
                select(Job).where(Job.id.in_(ids))
            )).scalars()}
        assert rows[ids[0]].status == "pending" and rows[ids[0]].locked_by is None
        assert rows[ids[1]].status == "failed" and rows[ids[1]].finished_at is not None
        assert rows[ids[2]].status == "running"  # masih dikerjakan worker hidup
    finally:
        await _cleanup(olt_a, olt_b, user_id)
        await engine.dispose()


async def test_requeue_unpenalized_does_not_burn_attempts() -> None:
    """Menunggu sesi CLI OLT bukan kegagalan: percobaan tidak boleh berkurang."""
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_a, olt_b, onu_id, user_id = await _fixture(tag)
    try:
        async with SessionLocal() as db:
            job = Job(job_type="backup_olt_config", status="pending", olt_id=olt_a,
                      run_after=datetime.now(UTC))
            db.add(job)
            await db.commit()
            job_id = job.id

        for _ in range(5):  # lima kali kalah antre
            async with SessionLocal() as db:
                claimed = await job_repo.claim_next(db, "w")
                await db.commit()
                assert claimed is not None and claimed.id == job_id
                await job_repo.requeue_unpenalized(db, claimed, timedelta(0), "antre")

        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
        assert job.status == "pending"
        assert job.attempts == 0, f"attempts={job.attempts}; antre tidak boleh dihitung gagal"
    finally:
        await _cleanup(olt_a, olt_b, user_id)
        await engine.dispose()
