"""B3 master data (zones / onu_types / splitters) against the real DB. Creates and removes its
own rows; skipped when Postgres is unreachable.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _auth(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}


async def test_master_data_crud_and_scope() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        sup = User(username=f"md_{tag}_s", full_name="s", password_hash="x", role="superadmin")
        a = User(username=f"md_{tag}_a", full_name="a", password_hash="x", role="admin")
        b = User(username=f"md_{tag}_b", full_name="b", password_hash="x", role="admin")
        db.add_all([sup, a, b])
        await db.flush()
        viewer = User(username=f"md_{tag}_u", full_name="u", password_hash="x", role="user",
                      admin_id=a.id)
        db.add(viewer)
        await db.commit()
        for u in (sup, a, b, viewer):
            await db.refresh(u)
    ids = {}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            # onu_types: Superadmin writes, Admin read-only
            r = await c.post("/api/onu-types", headers=_auth(sup), json={
                "pon_type": "gpon", "name": f"ZTE-F60x-{tag}", "eth_ports": 4,
                "wifi_ssids": 2, "voip_ports": 1, "catv": False,
                "capability": "bridging_routing", "allow_custom_profiles": True})
            assert r.status_code == 201, r.text
            ids["type"] = r.json()["id"]
            assert r.json()["onu_count"] == 0
            forbidden = await c.post("/api/onu-types", headers=_auth(a), json={
                "name": f"nope-{tag}"})
            assert forbidden.status_code == 403, forbidden.text
            assert (await c.get("/api/onu-types", headers=_auth(a))).status_code == 200
            dup = await c.post("/api/onu-types", headers=_auth(sup),
                               json={"name": f"ZTE-F60x-{tag}"})
            assert dup.status_code == 409, dup.text

            # zones: owner-scoped
            rz = await c.post("/api/zones", headers=_auth(a),
                              json={"name": f"Zona-{tag}", "external_id": "Z1",
                                    "latitude": -6.2, "longitude": 106.8})
            assert rz.status_code == 201, rz.text
            ids["zone"] = rz.json()["id"]
            assert (await c.get(f"/api/zones/{ids['zone']}", headers=_auth(b))).status_code == 404
            seen = await c.get(f"/api/zones/{ids['zone']}", headers=_auth(viewer))
            assert seen.status_code == 200, seen.text
            assert (await c.post("/api/zones", headers=_auth(viewer),
                                 json={"name": "x"})).status_code == 403
            assert [z["id"] for z in (await c.get("/api/zones", headers=_auth(b))).json()] == []

            # splitters: parent chaining + ratio capacity + cross-owner block
            rs = await c.post("/api/splitters", headers=_auth(a), json={
                "name": f"ODC-{tag}", "type": "odc", "ratio": "1:8", "zone_id": ids["zone"]})
            assert rs.status_code == 201, rs.text
            ids["odc"] = rs.json()["id"]
            assert rs.json()["capacity"] == 8 and rs.json()["onus"] == []
            rc = await c.post("/api/splitters", headers=_auth(a), json={
                "name": f"ODP-{tag}", "type": "odp", "ratio": "1:16",
                "zone_id": ids["zone"], "parent_id": ids["odc"]})
            assert rc.status_code == 201, rc.text
            ids["odp"] = rc.json()["id"]
            assert rc.json()["parent_name"] == f"ODC-{tag}" and rc.json()["capacity"] == 16
            assert (await c.post("/api/splitters", headers=_auth(b), json={
                "name": "steal", "type": "odp", "ratio": "1:8",
                "zone_id": ids["zone"]})).status_code == 404
            bad = await c.post("/api/splitters", headers=_auth(a), json={
                "name": "bad", "type": "odp", "ratio": "1:7", "zone_id": ids["zone"]})
            assert bad.status_code == 422, bad.text

            # updates + delete guards
            up = await c.patch(f"/api/splitters/{ids['odp']}", headers=_auth(a),
                               json={"ratio": "1:32", "notes": "ganti ratio"})
            assert up.status_code == 200 and up.json()["capacity"] == 32, up.text
            blocked = await c.delete(f"/api/zones/{ids['zone']}", headers=_auth(a))
            assert blocked.status_code == 409, blocked.text
            blocked_parent = await c.delete(f"/api/splitters/{ids['odc']}", headers=_auth(a))
            assert blocked_parent.status_code == 409, blocked_parent.text
            zl = (await c.get("/api/zones", headers=_auth(a))).json()[0]
            assert zl["splitter_count"] == 2, zl

            assert (await c.delete(f"/api/splitters/{ids['odp']}",
                                   headers=_auth(a))).status_code == 204
            assert (await c.delete(f"/api/splitters/{ids['odc']}",
                                   headers=_auth(a))).status_code == 204
            assert (await c.delete(f"/api/zones/{ids['zone']}",
                                   headers=_auth(a))).status_code == 204
            assert (await c.delete(f"/api/onu-types/{ids['type']}",
                                   headers=_auth(sup))).status_code == 204
            ids.clear()
        print("B3 master data: onu-types / zones / splitters CRUD + scope OK")
    finally:
        async with SessionLocal() as db:
            for table, key in (("splitters", "odp"), ("splitters", "odc"),
                               ("zones", "zone"), ("onu_types", "type")):
                if key in ids:
                    await db.execute(text(f"DELETE FROM {table} WHERE id = :i"), {"i": ids[key]})
            await db.execute(text("DELETE FROM activity_logs WHERE user_id IN "
                                  "(SELECT id FROM users WHERE username LIKE :p)"),
                             {"p": f"md_{tag}_%"})
            await db.execute(text("DELETE FROM users WHERE username LIKE :p"),
                             {"p": f"md_{tag}_%"})
            await db.commit()
