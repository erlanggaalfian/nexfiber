"""Role creation (PRD 3.7) + activate/deactivate/soft-delete of users (PRD 3.4.9),
against the real DB like test_user_scope.py.

Covers: Superadmin creates a Superadmin peer, Admin creates an Admin peer,
deactivate -> activate -> delete round trip, and nobody deactivating/deleting itself.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.user import User


async def _db_up() -> bool:
    # Drop pooled connections first: they belong to an earlier test's event loop and would
    # raise "Event loop is closed" here, making this test skip for the wrong reason.
    await engine.dispose()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _auth(uid: int, role: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


async def test_role_creation_and_lifecycle() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    pw = "abcdefghijkl"
    async with SessionLocal() as db:
        # Two Superadmins exist up front so the "last Superadmin" guard never fires here.
        root = User(username=f"t_{tag}_root", full_name="Root", password_hash="x",
                    role="superadmin")
        root2 = User(username=f"t_{tag}_root2", full_name="Root2", password_hash="x",
                     role="superadmin")
        admin = User(username=f"t_{tag}_adm", full_name="Adm", password_hash="x", role="admin")
        db.add_all([root, root2, admin])
        await db.flush()
        plain = User(username=f"t_{tag}_u", full_name="U", password_hash="x", role="user",
                     admin_id=admin.id)
        db.add(plain)
        await db.commit()
        root_id, admin_id, plain_id = root.id, admin.id, plain.id

    try:
        root_h, a_h = _auth(root_id, "superadmin"), _auth(admin_id, "admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # (a) Superadmin creates another Superadmin.
            r_super = await c.post("/api/users", headers=root_h, json={
                "username": f"t_{tag}_s2", "full_name": "S2", "password": pw,
                "role": "superadmin"})
            # (b) Admin creates another Admin.
            r_admin = await c.post("/api/users", headers=a_h, json={
                "username": f"t_{tag}_a2", "full_name": "A2", "password": pw, "role": "admin"})
            new_admin_id = r_admin.json()["id"]

            # (c) deactivate -> activate -> soft-delete.
            r_off = await c.patch(f"/api/users/{new_admin_id}", headers=root_h,
                                  json={"is_active": False})
            r_on = await c.patch(f"/api/users/{new_admin_id}", headers=root_h,
                                 json={"is_active": True})
            r_del = await c.delete(f"/api/users/{new_admin_id}", headers=root_h)
            r_gone = await c.get(f"/api/users/{new_admin_id}", headers=root_h)

            # (d) nobody deactivates or deletes itself.
            r_self_off = await c.patch(f"/api/users/{root_id}", headers=root_h,
                                       json={"is_active": False})
            r_self_del = await c.delete(f"/api/users/{root_id}", headers=root_h)

            # role "user" is still shut out of every endpoint (PRD 3.7).
            r_user_del = await c.delete(f"/api/users/{admin_id}", headers=_auth(plain_id, "user"))

        print("superadmin creates superadmin:", r_super.status_code, r_super.json()["role"])
        print("admin creates admin:         ", r_admin.status_code, r_admin.json()["role"])
        print("deactivate / activate:       ", r_off.json()["is_active"], r_on.json()["is_active"])
        print("delete -> get:               ", r_del.status_code, r_gone.status_code)
        print("self deactivate / delete:    ", r_self_off.status_code, r_self_del.status_code)
        print("role=user delete:            ", r_user_del.status_code)

        assert r_super.status_code == 201 and r_super.json()["role"] == "superadmin"
        assert r_admin.status_code == 201 and r_admin.json()["role"] == "admin"
        assert r_off.status_code == 200 and r_off.json()["is_active"] is False
        assert r_on.status_code == 200 and r_on.json()["is_active"] is True
        assert r_del.status_code == 204
        assert r_gone.status_code == 404  # soft-deleted rows are invisible
        assert r_self_off.status_code == 422
        assert r_self_del.status_code == 422
        assert r_user_del.status_code == 403

        async with SessionLocal() as db:
            row = await db.get(User, new_admin_id)
            assert row is not None and row.deleted_at is not None  # soft, not hard delete
            assert row.is_active is False
            fresh_root = await db.get(User, root_id)
            assert fresh_root.is_active is True  # self-deactivation really was blocked
            print("row kept with deleted_at set:", row.deleted_at is not None)
    finally:
        async with SessionLocal() as db:
            mine = select(User.id).where(User.username.like(f"t_{tag}%"))
            await db.execute(delete(ActivityLog).where(ActivityLog.user_id.in_(mine)))
            await db.execute(delete(User).where(User.username.like(f"t_{tag}%")))
            await db.commit()
        await engine.dispose()
