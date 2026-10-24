"""PRD 3.4.9/3.7 User Management scope against the real DB (same pattern as test_scope.py).
Superadmin sees everyone, Admin only its own Users, role "user" gets 403.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token, verify_password
from app.main import app
from app.models.activity_log import ActivityLog
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

async def test_user_management_scope() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        root = _user(tag, "superadmin")
        admin_a, admin_b = _user(tag + "a", "admin"), _user(tag + "b", "admin")
        db.add_all([root, admin_a, admin_b])
        await db.flush()
        user_a, user_b = _user(tag + "a", "user", admin_a.id), _user(tag + "b", "user", admin_b.id)
        olt_b = Olt(name=f"t_{tag}", host="192.0.2.2", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=admin_b.id, pon_port_count=16,
                    cli_port=20000 + int(tag, 16) % 40000)
        db.add_all([user_a, user_b, olt_b])
        await db.commit()
        ids = [root.id, admin_a.id, admin_b.id, user_a.id, user_b.id]
        root_id, admin_a_id, admin_b_id, user_a_id, user_b_id = ids
    try:
        def auth(uid: int, role: str) -> dict:
            return {"Authorization": f"Bearer {create_access_token(uid, role)}"}

        root_h = auth(root_id, "superadmin")
        a_h = auth(admin_a_id, "admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r_root = await c.get("/api/users", headers=root_h)
            r_admin_a = await c.get("/api/users", headers=a_h)
            r_user = await c.get("/api/users", headers=auth(user_a_id, "user"))
            r_cross = await c.get(f"/api/users/{user_b_id}", headers=a_h)
            r_filter = await c.get("/api/users?role=admin", headers=root_h)
            # Admin may only create Users, under itself.
            r_new = await c.post("/api/users", headers=a_h, json={
                "username": f"t_{tag}_new", "full_name": "New", "password": "abcdefghijkl",
                "role": "user"})
            r_new_admin = await c.post("/api/users", headers=a_h, json={
                "username": f"t_{tag}_bad", "full_name": "Bad", "password": "abcdefghijkl",
                "role": "admin"})
            r_reset = await c.post(f"/api/users/{user_a_id}/reset-password", headers=a_h)
            r_role = await c.patch(f"/api/users/{user_a_id}", headers=a_h, json={"role": "admin"})
            # Admin B still owns an OLT -> deactivation blocked.
            r_block = await c.patch(f"/api/users/{admin_b_id}", headers=root_h,
                                    json={"is_active": False})
            r_ok_off = await c.patch(f"/api/users/{admin_a_id}", headers=root_h,
                                     json={"is_active": False})

        root_ids = {u["id"] for u in r_root.json()}
        a_ids = {u["id"] for u in r_admin_a.json()}
        print("superadmin list sees:", sorted(root_ids & set(ids)))
        print("admin A list sees:   ", sorted(a_ids))
        print("role=user list:      ", r_user.status_code, r_user.json())
        print("admin A -> user B:   ", r_cross.status_code)
        print("?role=admin roles:   ", {u["role"] for u in r_filter.json()})
        print("admin A creates user:", r_new.status_code, r_new.json().get("admin_id"), "==",
              admin_a_id)
        print("admin A creates admin:", r_new_admin.status_code, r_new_admin.json())
        print("reset-password:      ", r_reset.status_code, len(r_reset.json()["password"]),
              "chars (not echoed)")
        print("admin A changes role:", r_role.status_code, r_role.json())
        print("deactivate admin w/ OLT:", r_block.status_code, r_block.json())
        print("deactivate admin w/o OLT:", r_ok_off.status_code, r_ok_off.json()["is_active"])

        assert {root_id, admin_a_id, admin_b_id, user_a_id, user_b_id} <= root_ids
        assert a_ids == {user_a_id}  # list was taken before the create below
        assert r_user.status_code == 403
        assert r_cross.status_code == 404
        assert {u["role"] for u in r_filter.json()} == {"admin"}
        assert r_new.status_code == 201 and r_new.json()["admin_id"] == admin_a_id
        assert r_new_admin.status_code == 422
        assert r_role.status_code == 422
        assert r_block.status_code == 422
        assert r_ok_off.status_code == 200 and r_ok_off.json()["is_active"] is False

        async with SessionLocal() as db:
            fresh = await db.get(User, user_a_id)
            assert fresh.must_change_password is True
            assert verify_password(r_reset.json()["password"], fresh.password_hash)
            print("temp password hash verified, must_change_password:",
                  fresh.must_change_password)
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Olt).where(Olt.name == f"t_{tag}"))
            mine = select(User.id).where(User.username.like(f"t_{tag}%"))
            await db.execute(delete(ActivityLog).where(ActivityLog.user_id.in_(mine)))
            await db.execute(delete(User).where(User.username.like(f"t_{tag}%")))
            await db.commit()
        await engine.dispose()
