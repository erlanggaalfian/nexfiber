"""Checklist OLT per user (GET/PUT /api/users/{id}/olt-access): arah balik olt_access.
Tabel dan aturannya sama dengan tests/test_olt_access.py — hanya sisi query dibalik.
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


async def test_user_olt_access_checklist() -> None:
    """Superadmin mencentang OLT untuk Admin B; B langsung melihat OLT itu, Admin lain 422."""
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        sup = _user(tag + "s", "superadmin")
        admin_a, admin_b = (_user(tag + x, "admin") for x in "ab")
        db.add_all([sup, admin_a, admin_b])
        await db.flush()
        child = _user(tag + "c", "user", admin_a.id)
        db.add(child)
        olt = Olt(name=f"t_{tag}", host="192.0.2.3", vendor="zte", model="C320",
                  cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                  owner_id=admin_a.id, pon_port_count=16,
                  cli_port=20000 + int(tag, 16) % 40000)
        db.add(olt)
        await db.commit()
    ids = [sup.id, admin_a.id, admin_b.id, child.id]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            empty = await c.get(f"/api/users/{admin_b.id}/olt-access", headers=_auth(sup))
            # Admin tidak boleh mengatur akses OLT, hanya Superadmin (PRD 3.7). Targetnya
            # User di bawah Admin itu sendiri, jadi yang diuji penolakan peran (422), bukan
            # visibilitas baris (baris manager lain memang sudah 404 untuk Admin).
            denied = await c.put(f"/api/users/{child.id}/olt-access", headers=_auth(admin_a),
                                 json={"olt_ids": [olt.id]})
            saved = await c.put(f"/api/users/{admin_b.id}/olt-access", headers=_auth(sup),
                                json={"olt_ids": [olt.id]})
            after = await c.get(f"/api/users/{admin_b.id}/olt-access", headers=_auth(sup))
            sees = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_b))
            # Pemilik utama tidak perlu baris akses sendiri: centangnya diabaikan.
            owner_self = await c.put(f"/api/users/{admin_a.id}/olt-access", headers=_auth(sup),
                                     json={"olt_ids": [olt.id]})
            # Daftar dikirim utuh: kosong = akses dicabut.
            await c.put(f"/api/users/{admin_b.id}/olt-access", headers=_auth(sup),
                        json={"olt_ids": []})
            revoked = await c.get(f"/api/olts/{olt.id}", headers=_auth(admin_b))

        print("kosong:", empty.json(), "| admin PUT:", denied.status_code)
        print("disimpan:", saved.json(), "| dibaca:", after.json())
        print("B lihat OLT:", sees.status_code, "| setelah dicabut:", revoked.status_code)

        assert empty.json()["olt_ids"] == []
        assert denied.status_code == 422
        assert saved.json()["olt_ids"] == [olt.id]
        assert after.json()["olt_ids"] == [olt.id]
        assert sees.status_code == 200
        assert owner_self.json()["olt_ids"] == []
        assert revoked.status_code == 404
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(OltAccess).where(OltAccess.olt_id == olt.id))
            await db.execute(text("DELETE FROM activity_logs WHERE olt_id = :i"), {"i": olt.id})
            await db.execute(text("DELETE FROM activity_logs WHERE user_id = ANY(:i)"),
                             {"i": ids})
            await db.execute(delete(Olt).where(Olt.id == olt.id))
            await db.execute(delete(User).where(User.id == child.id))
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()
        await engine.dispose()
