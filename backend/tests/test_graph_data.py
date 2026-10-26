"""Settings Graph Data. Semua row bertanda UUID dan dibersihkan sendiri; tidak menyentuh
data graph dev yang sudah ada. Endpoint delete hanya dipanggil untuk row test itu.
"""
from datetime import UTC, date, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.activity_log import ActivityLog
from app.models.olt import Olt, PonPort
from app.models.onu import Onu, OnuSignalHistory, OnuTrafficHistory
from app.models.setting import Setting
from app.models.user import User
from app.schemas.graph_data import GraphRetention
from app.services import graph_data_service as svc


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _user(tag: str, role: str) -> User:
    return User(username=f"gd_{tag}_{role}", full_name=tag, password_hash="x", role=role)


async def _seed(tag: str):
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        admin, other = _user(tag, "admin"), _user(tag + "x", "admin")
        db.add_all([admin, other])
        await db.flush()
        owned = Olt(name=f"gd_{tag}", host="192.0.2.10", vendor="zte", model="C320",
                    cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                    owner_id=admin.id, pon_port_count=16, cli_port=10000 + int(tag, 16) % 50000)
        foreign = Olt(name=f"gd_{tag}_x", host="192.0.2.11", vendor="zte", model="C320",
                      cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                      owner_id=other.id, pon_port_count=16, cli_port=10001 + int(tag, 16) % 50000)
        db.add_all([owned, foreign])
        await db.flush()
        port_a = PonPort(olt_id=owned.id, slot=1, port=1)
        port_b = PonPort(olt_id=foreign.id, slot=1, port=1)
        db.add_all([port_a, port_b])
        await db.flush()
        onu_a = Onu(olt_id=owned.id, pon_port_id=port_a.id, onu_index=1,
                    serial_number=f"GD{tag}A", status="online")
        onu_b = Onu(olt_id=foreign.id, pon_port_id=port_b.id, onu_index=1,
                    serial_number=f"GD{tag}B", status="online")
        db.add_all([onu_a, onu_b])
        await db.flush()
        # 10 hari lalu masuk rentang endpoint; 100 hari lalu dipakai test purge.
        for onu in (onu_a, onu_b):
            db.add_all([
                OnuTrafficHistory(onu_id=onu.id, in_octets=1, out_octets=2,
                                  sampled_at=now - timedelta(days=10)),
                OnuSignalHistory(onu_id=onu.id, status="online", rx_power_dbm=-20,
                                 sampled_at=now - timedelta(days=10)),
            ])
        db.add(OnuTrafficHistory(onu_id=onu_a.id, in_octets=3, out_octets=4,
                                 sampled_at=now - timedelta(days=100)))
        await db.commit()
    return admin, other, owned, foreign, onu_a, onu_b


@pytest.mark.asyncio
async def test_graph_data_api_scope_range_validation_and_retention() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:6]
    admin, other, owned, foreign, onu_a, onu_b = await _seed(tag)
    old_setting = None
    async with SessionLocal() as db:
        row = await db.get(Setting, svc.SETTING_KEY)
        if row:
            old_setting = (dict(row.value), row.updated_by, row.description)
    auth = {"Authorization": f"Bearer {create_access_token(admin.id, admin.role)}"}
    today = datetime.now(svc.WIB).date()
    payload = {"kinds": ["traffic", "signal"],
               "date_from": (today - timedelta(days=11)).isoformat(),
               "date_to": (today - timedelta(days=9)).isoformat(), "olt_id": owned.id}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            default = await c.get("/api/settings/graph-data/retention", headers=auth)
            invalid_ret = await c.put("/api/settings/graph-data/retention", headers=auth,
                                      json={"traffic": 15, "signal": 90})
            valid_ret = await c.put("/api/settings/graph-data/retention", headers=auth,
                                    json={"traffic": 7, "signal": 180})
            preview = await c.post("/api/settings/graph-data/preview-delete", headers=auth,
                                   json=payload)
            outside = await c.post("/api/settings/graph-data/preview-delete", headers=auth,
                                   json={**payload, "olt_id": foreign.id})
            backwards = await c.post("/api/settings/graph-data/preview-delete", headers=auth,
                                     json={**payload, "date_from": today.isoformat(),
                                           "date_to": (today - timedelta(days=1)).isoformat()})
            future = await c.post("/api/settings/graph-data/preview-delete", headers=auth,
                                  json={**payload, "date_to": (today + timedelta(days=1)).isoformat()})
            empty = await c.post("/api/settings/graph-data/preview-delete", headers=auth,
                                 json={**payload, "kinds": []})
            removed = await c.post("/api/settings/graph-data/delete", headers=auth, json=payload)
        # GET pertama bisa memuat nilai pengguna lama; default diuji terpisah di bawah.
        assert default.status_code == 200
        assert invalid_ret.status_code == 422
        assert valid_ret.json() == {"traffic": 7, "signal": 180}
        assert preview.json() == {"deleted": {"traffic": 1, "signal": 1}, "total": 2}
        assert removed.json() == {"deleted": {"traffic": 1, "signal": 1}, "total": 2}
        assert outside.status_code == 404
        assert backwards.status_code == 422 and future.status_code == 422
        assert empty.status_code == 422
        async with SessionLocal() as db:
            # Row OLT lain tidak ikut terhapus; audit menyimpan siapa/rentang/jumlah.
            assert await db.scalar(select(OnuTrafficHistory.id).where(
                OnuTrafficHistory.onu_id == onu_b.id)) is not None
            audit = await db.scalar(select(ActivityLog).where(
                ActivityLog.user_id == admin.id,
                ActivityLog.action == "graph_data.delete").order_by(ActivityLog.created_at.desc()))
            assert audit and audit.after["total"] == 2
    finally:
        async with SessionLocal() as db:
            if old_setting:
                value, updated_by, description = old_setting
                row = await db.get(Setting, svc.SETTING_KEY)
                row.value, row.updated_by, row.description = value, updated_by, description
            else:
                await db.execute(delete(Setting).where(Setting.key == svc.SETTING_KEY))
            await db.execute(delete(ActivityLog).where(ActivityLog.user_id.in_([admin.id, other.id])))
            await db.execute(delete(OnuTrafficHistory).where(
                OnuTrafficHistory.onu_id.in_([onu_a.id, onu_b.id])))
            await db.execute(delete(OnuSignalHistory).where(
                OnuSignalHistory.onu_id.in_([onu_a.id, onu_b.id])))
            await db.execute(delete(Onu).where(Onu.id.in_([onu_a.id, onu_b.id])))
            await db.execute(delete(PonPort).where(PonPort.olt_id.in_([owned.id, foreign.id])))
            await db.execute(delete(Olt).where(Olt.id.in_([owned.id, foreign.id])))
            await db.execute(delete(User).where(User.id.in_([admin.id, other.id])))
            await db.commit()


@pytest.mark.asyncio
async def test_purge_per_kind_retention_and_zero_disabled() -> None:
    """Traffic 30 hari dibersihkan, signal 0 tetap ada; batch function yang sama dipakai API."""
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:6]
    admin, other, owned, foreign, onu_a, onu_b = await _seed(tag)
    old_setting = None
    async with SessionLocal() as db:
        row = await db.get(Setting, svc.SETTING_KEY)
        if row:
            old_setting = (dict(row.value), row.updated_by, row.description)
        await svc.set_retention(db, GraphRetention(traffic=30, signal=0), admin)
        await db.commit()
    try:
        async with SessionLocal() as db:
            purged = await svc.purge_expired(db, datetime.now(UTC))
            assert purged["traffic"] == 1
            assert purged["signal"] == 0
            # Sampel traffic 10 hari masih ada, yang 100 hari hilang.
            times = (await db.execute(select(OnuTrafficHistory.sampled_at).where(
                OnuTrafficHistory.onu_id == onu_a.id))).scalars().all()
            assert len(times) == 1 and times[0] > datetime.now(UTC) - timedelta(days=30)
            assert await db.scalar(select(OnuSignalHistory.id).where(
                OnuSignalHistory.onu_id == onu_a.id)) is not None
    finally:
        async with SessionLocal() as db:
            if old_setting:
                value, updated_by, description = old_setting
                row = await db.get(Setting, svc.SETTING_KEY)
                row.value, row.updated_by, row.description = value, updated_by, description
            else:
                await db.execute(delete(Setting).where(Setting.key == svc.SETTING_KEY))
            await db.execute(delete(ActivityLog).where(ActivityLog.user_id.in_([admin.id, other.id])))
            await db.execute(delete(OnuTrafficHistory).where(OnuTrafficHistory.onu_id.in_([onu_a.id, onu_b.id])))
            await db.execute(delete(OnuSignalHistory).where(OnuSignalHistory.onu_id.in_([onu_a.id, onu_b.id])))
            await db.execute(delete(Onu).where(Onu.id.in_([onu_a.id, onu_b.id])))
            await db.execute(delete(PonPort).where(PonPort.olt_id.in_([owned.id, foreign.id])))
            await db.execute(delete(Olt).where(Olt.id.in_([owned.id, foreign.id])))
            await db.execute(delete(User).where(User.id.in_([admin.id, other.id])))
            await db.commit()


def test_default_retention_and_wib_inclusive_window():
    assert svc.DEFAULT_RETENTION == {"traffic": 30, "signal": 90}
    start, end = svc._window(date(2026, 1, 1), date(2026, 1, 2))
    assert start.isoformat() == "2026-01-01T00:00:00+07:00"
    assert end.isoformat() == "2026-01-03T00:00:00+07:00"
