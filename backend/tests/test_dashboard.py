"""/api/dashboard (PRD 3.4.2): scope OLT, bucket sinyal, recent activity. Real DB, skip jika
Postgres mati (pola sama test_scope.py/test_logs.py).
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
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.user import User


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_dashboard_scoped_signal_and_olts() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        admin_a = User(username=f"t_{tag}_a", full_name="a", password_hash="x", role="admin")
        admin_b = User(username=f"t_{tag}_b", full_name="b", password_hash="x", role="admin")
        db.add_all([admin_a, admin_b])
        await db.flush()
        olt_a = Olt(name=f"t_{tag}_olt_a", host="192.0.2.2", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=admin_a.id, pon_port_count=16, cli_port=22000 + int(tag, 16) % 9000)
        db.add(olt_a)
        await db.flush()
        port = PonPort(olt_id=olt_a.id, slot=1, port=1)
        db.add(port)
        await db.flush()
        db.add(Onu(olt_id=olt_a.id, pon_port_id=port.id, serial_number=f"T{tag}", status="online",
                    rx_power_dbm=-20.0))
        db.add(ActivityLog(created_at=datetime.now(UTC), action="onu.authorize",
                            entity_type="onu", success=True, olt_id=olt_a.id, user_id=admin_a.id))
        await db.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            headers_a = {"Authorization": f"Bearer {create_access_token(admin_a.id, admin_a.role)}"}
            headers_b = {"Authorization": f"Bearer {create_access_token(admin_b.id, admin_b.role)}"}
            r_a = await c.get("/api/dashboard", headers=headers_a)
            r_b = await c.get("/api/dashboard", headers=headers_b)
        assert r_a.status_code == 200
        body_a = r_a.json()
        assert body_a["onu_by_signal"]["good"] >= 1
        assert any(o["id"] == olt_a.id and o["onu_count"] == 1 and o["onu_online"] == 1
                   for o in body_a["olts"])
        assert any(row["action"] == "onu.authorize" for row in body_a["recent_activity"])
        body_b = r_b.json()
        assert all(o["id"] != olt_a.id for o in body_b["olts"])  # admin B tidak memiliki olt_a
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(ActivityLog).where(ActivityLog.olt_id == olt_a.id))
            await db.execute(delete(Onu).where(Onu.pon_port_id == port.id))
            await db.execute(delete(PonPort).where(PonPort.id == port.id))
            await db.execute(delete(Olt).where(Olt.id == olt_a.id))
            await db.execute(delete(User).where(User.id.in_([admin_a.id, admin_b.id])))
            await db.commit()
        await engine.dispose()
