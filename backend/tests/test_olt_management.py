"""PRD 3.4.8 OLT Management against the real DB (same pattern as test_scope.py):
role "user" gets 403, Superadmin assigns the owner, Admin always owns its own OLT,
secrets never leave the API, blank password on edit keeps the stored one, delete is
blocked while ONUs exist unless the name is typed back.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token, decrypt_secret
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.olt import Olt
from app.models.user import User

SECRET_KEYS = ("cli_password", "snmp_community", "snmp_community_rw", "cli_password_enc",
               "snmp_community_enc", "snmp_community_rw_enc", "cli_enable_password")


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

def _user(tag: str, role: str, admin_id: int | None = None) -> User:
    return User(username=f"t_{tag}_{role}", full_name=f"T {tag} {role}", password_hash="x",
                role=role, admin_id=admin_id)

def _auth(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}

def _body(tag: str, port: int, **over) -> dict:
    body = {"name": f"t_{tag}", "host": "192.0.2.10", "cli_username": "oper",
            "cli_password": "s3cret-cli", "snmp_community": "ro-community",
            "snmp_community_rw": "rw-community", "cli_port": port, "pon_port_count": 8}
    return body | over


async def test_olt_management() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    port = 20000 + int(tag, 16) % 40000
    async with SessionLocal() as db:
        root, admin_a = _user(tag, "superadmin"), _user(tag + "a", "admin")
        db.add_all([root, admin_a])
        await db.flush()
        operator = _user(tag + "a", "user", admin_a.id)
        db.add(operator)
        await db.commit()
    created: list[int] = []
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # Role "user" is locked out of the whole page.
            r_403 = await c.get("/api/olts/rows", headers=_auth(operator))
            r_403_post = await c.post("/api/olts", json=_body(tag, port),
                                      headers=_auth(operator))

            # Superadmin assigns the owner.
            r_create = await c.post("/api/olts", json=_body(tag, port, owner_id=admin_a.id),
                                    headers=_auth(root))
            olt_id = r_create.json()["id"]
            created.append(olt_id)

            # Admin creating an OLT always owns it, even when it asks for someone else.
            r_admin_create = await c.post(
                "/api/olts", json=_body(tag + "b", port + 1, name=f"t_{tag}b", owner_id=root.id),
                headers=_auth(admin_a))
            created.append(r_admin_create.json()["id"])

            r_rows = await c.get(f"/api/olts/rows?search=t_{tag}", headers=_auth(root))
            # Blank password on edit = keep the stored credential.
            r_patch = await c.patch(f"/api/olts/{olt_id}",
                                    json={"name": f"t_{tag}-ren", "cli_password": ""},
                                    headers=_auth(root))
            r_del_bad = await c.delete(f"/api/olts/{olt_id}?confirm_name=wrong",
                                       headers=_auth(root))
            r_del = await c.delete(f"/api/olts/{olt_id}", headers=_auth(root))

        print("user  -> GET  /api/olts/rows:", r_403.status_code, r_403.json())
        print("user  -> POST /api/olts     :", r_403_post.status_code)
        print("root  -> POST /api/olts     :", r_create.status_code,
              {k: r_create.json()[k] for k in ("id", "name", "host", "owner_id", "status")})
        print("admin -> POST /api/olts     : owner_id",
              r_admin_create.json()["owner_id"], "(admin_a =", admin_a.id, ")")
        print("root  -> GET  /api/olts/rows:", r_rows.status_code,
              [(r["name"], r["owner_name"], r["onu_count"]) for r in r_rows.json()])
        print("root  -> PATCH name+blank pw:", r_patch.status_code, r_patch.json()["name"])
        print("root  -> DELETE (no ONU)    :", r_del_bad.status_code, r_del.status_code)

        assert r_403.status_code == 403
        assert r_403_post.status_code == 403
        assert r_create.status_code == 201
        assert r_create.json()["owner_id"] == admin_a.id
        assert r_admin_create.json()["owner_id"] == admin_a.id
        assert not any(k in r_create.json() for k in SECRET_KEYS)
        assert [r["id"] for r in r_rows.json()] == created
        assert r_rows.json()[0]["owner_name"] == admin_a.full_name
        assert r_rows.json()[0]["onu_count"] == 0
        assert r_patch.status_code == 200
        # No ONUs -> confirm_name is irrelevant, both calls are allowed to proceed.
        assert r_del_bad.status_code == 204
        assert r_del.status_code == 404  # already soft-deleted

        async with SessionLocal() as db:
            row = await db.get(Olt, olt_id)
            print("stored secrets decrypt:", decrypt_secret(row.cli_password_enc),
                  decrypt_secret(row.snmp_community_rw_enc))
            assert decrypt_secret(row.cli_password_enc) == "s3cret-cli"
            assert decrypt_secret(row.snmp_community_enc) == "ro-community"
            assert decrypt_secret(row.snmp_community_rw_enc) == "rw-community"
            assert row.deleted_at is not None and row.is_active is False
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(ActivityLog).where(ActivityLog.olt_id.in_(created)))
            await db.execute(delete(ActivityLog).where(ActivityLog.user_id.in_(
                [root.id, admin_a.id, operator.id])))
            await db.execute(delete(Olt).where(Olt.id.in_(created)))
            await db.execute(delete(User).where(User.id == operator.id))
            await db.execute(delete(User).where(User.id.in_([root.id, admin_a.id])))
            await db.commit()
        await engine.dispose()
