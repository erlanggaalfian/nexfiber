"""/api/logs (PRD 3.4.15): scope OLT + filter kategori, against the real DB. Skipped when
Postgres is unreachable (same pattern as test_scope.py).
"""
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.olt import Olt
from app.models.user import User
from app.schemas.activity_log import actions_for_category, category_of


def test_category_of_known_actions():
    assert category_of("onu.authorize") == "authorize"
    assert category_of("onu.reboot") == "reboot"
    assert category_of("olt.create") == "olt"
    assert category_of("vlan.create") == "service"
    assert "onu.authorize" in actions_for_category("authorize")
    assert "olt.create" not in actions_for_category("authorize")


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_logs_scoped_by_olt_and_category() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        admin_a = User(username=f"t_{tag}_a", full_name="a", password_hash="x", role="admin")
        admin_b = User(username=f"t_{tag}_b", full_name="b", password_hash="x", role="admin")
        db.add_all([admin_a, admin_b])
        await db.flush()
        olt_a = Olt(name=f"t_{tag}_olt_a", host="192.0.2.1", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=admin_a.id, pon_port_count=16, cli_port=21000 + int(tag, 16) % 9000)
        db.add(olt_a)
        await db.flush()
        db.add_all([
            ActivityLog(created_at=datetime.now(UTC), action="onu.authorize", entity_type="onu",
                        success=True, olt_id=olt_a.id, user_id=admin_a.id),
            ActivityLog(created_at=datetime.now(UTC), action="olt.create", entity_type="olt",
                        success=True, olt_id=olt_a.id, user_id=admin_a.id),
        ])
        await db.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            headers_a = {"Authorization": f"Bearer {create_access_token(admin_a.id, admin_a.role)}"}
            headers_b = {"Authorization": f"Bearer {create_access_token(admin_b.id, admin_b.role)}"}
            r_a = await c.get("/api/logs", params={"olt_id": olt_a.id}, headers=headers_a)
            r_b = await c.get("/api/logs", params={"olt_id": olt_a.id}, headers=headers_b)
            r_cat = await c.get("/api/logs", params={"olt_id": olt_a.id, "category": "authorize"},
                                headers=headers_a)
        assert r_a.status_code == 200
        assert r_a.json()["total"] >= 2
        assert r_b.status_code == 200
        assert r_b.json()["total"] == 0  # admin B tidak memiliki olt_a
        assert r_cat.status_code == 200
        assert all(row["category"] == "authorize" for row in r_cat.json()["items"])
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(ActivityLog).where(ActivityLog.olt_id == olt_a.id))
            await db.execute(delete(Olt).where(Olt.id == olt_a.id))
            await db.execute(delete(User).where(User.id.in_([admin_a.id, admin_b.id])))
            await db.commit()
        await engine.dispose()
