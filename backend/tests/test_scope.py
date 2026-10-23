"""PRD 3.7 scope against the real DB (DATABASE_URL / NEXFIBER_CONFIG). Creates and removes
its own rows; skipped when Postgres is unreachable.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.olt import Olt
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

async def test_scope_and_setup() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        admin_a, admin_b = _user(tag + "a", "admin"), _user(tag + "b", "admin")
        db.add_all([admin_a, admin_b])
        await db.flush()
        user_a = _user(tag + "a", "user", admin_a.id)
        olt_b = Olt(name=f"t_{tag}", host="192.0.2.1", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=admin_b.id, pon_port_count=16, cli_port=20000 + int(tag, 16) % 40000)
        db.add_all([user_a, olt_b])
        await db.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            def auth(u: User) -> dict:
                return {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}

            r_user = await c.get(f"/api/olts/{olt_b.id}", headers=auth(user_a))
            r_admin = await c.get(f"/api/olts/{olt_b.id}", headers=auth(admin_a))
            r_owner = await c.get(f"/api/olts/{olt_b.id}", headers=auth(admin_b))
            r_list = await c.get("/api/olts", headers=auth(user_a))
            r_setup_get = await c.get("/api/auth/setup")
            r_setup = await c.post("/api/auth/setup", json={
                "username": f"t_{tag}_x", "full_name": "x",
                "password": "abcdefghijkl", "password_confirm": "abcdefghijkl"})
        print("user A  -> OLT B:", r_user.status_code, r_user.json())
        print("admin A -> OLT B:", r_admin.status_code)
        print("admin B -> OLT B:", r_owner.status_code)
        print("user A  list ids:", [o["id"] for o in r_list.json()])
        print("GET  /setup:", r_setup_get.status_code, r_setup_get.json())
        print("POST /setup:", r_setup.status_code, r_setup.json())
        assert r_user.status_code == 404
        assert r_admin.status_code == 404
        assert r_owner.status_code == 200
        assert olt_b.id not in [o["id"] for o in r_list.json()]
        assert r_setup_get.json() == {"needed": False}
        assert r_setup.status_code == 404
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Olt).where(Olt.id == olt_b.id))
            await db.execute(delete(User).where(User.id == user_a.id))
            await db.execute(delete(User).where(User.id.in_([admin_a.id, admin_b.id])))
            await db.commit()
        await engine.dispose()
