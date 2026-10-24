"""Kepemilikan OLT bersama (olt_access): owner utama + akses tambahan, lawan real DB.
Dilewati kalau Postgres mati, pola sama dengan tests/test_scope.py.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.olt import Olt, OltAccess
from app.models.user import User


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _user(tag: str, role: str, admin_id: int | None = None) -> User:
    return User(username=f"t_{tag}_{role}", full_name=tag, password_hash="x", role=role,
                admin_id=admin_id)


def _auth(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}


async def test_shared_olt_access() -> None:
    """A pemilik utama OLT X, B diberi akses tambahan, C tidak: B boleh, C 404."""
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        sup = _user(tag + "s", "superadmin")
        admin_a, admin_b, admin_c = (_user(tag + x, "admin") for x in "abc")
        db.add_all([sup, admin_a, admin_b, admin_c])
        await db.flush()
        user_b = _user(tag + "b", "user", admin_b.id)
        olt = Olt(name=f"t_{tag}", host="192.0.2.2", vendor="zte", model="C320",
                  cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                  owner_id=admin_a.id, pon_port_count=16,
                  cli_port=20000 + int(tag, 16) % 40000)
        db.add_all([user_b, olt])
        await db.commit()
    ids = [sup.id, admin_a.id, admin_b.id, admin_c.id, user_b.id]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # Sebelum dibagikan: hanya pemilik utama yang melihat.
            before_b = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_b))
            # Admin tidak boleh membagi OLT sendiri (hanya Superadmin).
            denied = await c.patch(f"/api/olts/{olt.id}", headers=_auth(admin_a),
                                   json={"access_user_ids": [admin_b.id]})
            shared = await c.patch(f"/api/olts/{olt.id}", headers=_auth(sup),
                                   json={"access_user_ids": [admin_b.id]})
            after_a = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_a))
            after_b = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_b))
            after_c = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_c))
            # User di bawah B ikut melihat OLT yang dibagikan ke Admin-nya.
            after_ub = await c.get(f"/api/olts/{olt.id}", headers=_auth(user_b))
            rows_b = await c.get("/api/olts/rows", headers=_auth(admin_b))
            rows_c = await c.get("/api/olts/rows", headers=_auth(admin_c))
            detail_b = await c.get(f"/api/olts/{olt.id}/detail", headers=_auth(admin_b))
            # B boleh mengelola (job ke OLT), C tidak.
            job_b = await c.post(f"/api/olts/{olt.id}/test", headers=_auth(admin_b))
            job_c = await c.post(f"/api/olts/{olt.id}/test", headers=_auth(admin_c))
            # Daftar akses dikirim utuh: kosong = akses dicabut lagi.
            await c.patch(f"/api/olts/{olt.id}", headers=_auth(sup),
                          json={"access_user_ids": []})
            revoked_b = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_b))

        print("B sebelum dibagikan:", before_b.status_code)
        print("A membagi (harus ditolak):", denied.status_code)
        print("Superadmin membagi:", shared.status_code)
        print("A/B/C setelah:", after_a.status_code, after_b.status_code, after_c.status_code)
        print("user di bawah B:", after_ub.status_code)
        print("job B/C:", job_b.status_code, job_c.status_code)
        print("B setelah dicabut:", revoked_b.status_code)

        assert before_b.status_code == 404
        assert denied.status_code == 422
        assert shared.status_code == 200
        assert after_a.status_code == 200  # owner utama tetap bisa (backward compatible)
        assert after_b.status_code == 200
        assert after_c.status_code == 404
        assert after_ub.status_code == 200
        assert olt.id in [o["id"] for o in rows_b.json()]
        assert olt.id not in [o["id"] for o in rows_c.json()]
        assert detail_b.json()["access_user_ids"] == [admin_b.id]
        assert job_b.status_code == 202
        assert job_c.status_code == 404
        assert revoked_b.status_code == 404
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OltAccess).where(OltAccess.olt_id == olt.id))
            await db.execute(text("DELETE FROM jobs WHERE olt_id = :i"), {"i": olt.id})
            await db.execute(text("DELETE FROM activity_logs WHERE olt_id = :i"), {"i": olt.id})
            await db.execute(delete(Olt).where(Olt.id == olt.id))
            await db.execute(delete(User).where(User.id == user_b.id))
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()
        await engine.dispose()
