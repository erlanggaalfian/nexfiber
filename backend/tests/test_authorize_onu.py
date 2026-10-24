"""Fase C1: Form Otorisasi + preset ONU.

Dua lapis:
  * unit murni untuk build_authorize_commands (urutan CLI, tanpa device);
  * integrasi HTTP terhadap DB nyata untuk /api/onu-presets dan guard /api/onus/authorize.
Tidak ada perintah yang dikirim ke OLT mana pun di sini: authorize hanya diuji sampai
titik validasi (serial tidak ada di unconfigured_onus -> 404), job tidak pernah dibuat.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.drivers.types import AuthorizeRequest
from app.drivers.zte_c320 import build_authorize_commands
from app.main import app
from app.models.user import User


def test_build_authorize_commands_follows_cli_reference_order():
    cmds = build_authorize_commands(AuthorizeRequest(
        slot=3, port=6, onu_id=59, serial_number="ZTEGD3A146F9", auth_type="sn",
        onu_type="ALL-ONT", name="budi", description="Jl Mawar",
        upload_profile="PAKET20_UP", download_profile="PAKET20_DN", vlan_id=100,
    ))
    assert cmds == [
        "interface gpon-olt_1/3/6",
        "onu 59 type ALL-ONT sn ZTEGD3A146F9",
        "exit",
        "interface gpon-onu_1/3/6:59",
        "name budi",
        "description Jl Mawar",
        "tcont 1 profile PAKET20_UP",
        "gemport 1 tcont 1",
        "gemport 1 traffic-limit downstream PAKET20_DN",
        "service-port 1 vport 1 user-vlan 100 vlan 100",
        "exit",
    ]


def test_build_authorize_commands_skips_optional_blocks():
    cmds = build_authorize_commands(AuthorizeRequest(
        slot=1, port=1, onu_id=7, serial_number="ZTEG00000001", auth_type="sn",
    ))
    # Tanpa profile/VLAN: hanya registrasi SN, tidak ada tcont/gemport/service-port menggantung.
    assert cmds == [
        "interface gpon-olt_1/1/1",
        "onu 7 type ALL-ONT sn ZTEG00000001",
        "exit",
        "interface gpon-onu_1/1/1:7",
        "exit",
    ]
    assert not any(c.startswith(("tcont", "gemport", "service-port")) for c in cmds)


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _auth(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}


async def test_onu_presets_and_authorize_guards() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        admin = User(username=f"c1_{tag}_a", full_name="a", password_hash="x", role="admin")
        other = User(username=f"c1_{tag}_b", full_name="b", password_hash="x", role="admin")
        db.add_all([admin, other])
        await db.flush()
        viewer = User(username=f"c1_{tag}_u", full_name="u", password_hash="x", role="user",
                      admin_id=admin.id)
        db.add(viewer)
        await db.commit()
        for u in (admin, other, viewer):
            await db.refresh(u)
    ids: dict[str, int] = {}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            rt = await c.post("/api/onu-types", headers=_auth(admin), json={"name": f"T-{tag}"})
            assert rt.status_code == 403, rt.text  # katalog global: Admin tidak boleh menulis

            async with SessionLocal() as db:
                row = await db.execute(text(
                    "INSERT INTO onu_types (name, pon_type, eth_ports, wifi_ssids, voip_ports, "
                    "catv, capability, allow_custom_profiles, is_active, created_at, updated_at) "
                    "VALUES (:n,'gpon',4,2,1,false,'bridging_routing',true,true,now(),now()) "
                    "RETURNING id"), {"n": f"T-{tag}"})
                ids["type"] = row.scalar_one()
                await db.commit()

            rp = await c.post("/api/onu-presets", headers=_auth(admin), json={
                "name": f"Preset-{tag}", "onu_type_id": ids["type"], "vlan": 100,
                "download_profile": "PAKET20", "upload_profile": "PAKET20",
                "onu_mode": "routing", "wan_mode": "pppoe"})
            assert rp.status_code == 201, rp.text
            ids["preset"] = rp.json()["id"]
            assert rp.json()["owner_id"] == admin.id and rp.json()["vlan"] == 100

            dup = await c.post("/api/onu-presets", headers=_auth(admin), json={
                "name": f"Preset-{tag}", "onu_type_id": ids["type"]})
            assert dup.status_code == 409, dup.text

            bad_type = await c.post("/api/onu-presets", headers=_auth(admin), json={
                "name": f"Preset-{tag}-x", "onu_type_id": 10**9})
            assert bad_type.status_code == 404, bad_type.text

            # scope: owner lain tidak melihat preset ini, User hanya baca.
            assert [p["id"] for p in (await c.get("/api/onu-presets",
                                                  headers=_auth(other))).json()] == []
            mine = await c.get("/api/onu-presets", headers=_auth(viewer))
            assert ids["preset"] in [p["id"] for p in mine.json()], mine.text
            assert (await c.post("/api/onu-presets", headers=_auth(viewer),
                                 json={"name": "x", "onu_type_id": ids["type"]})).status_code == 403
            assert (await c.delete(f"/api/onu-presets/{ids['preset']}",
                                   headers=_auth(other))).status_code == 404

            # authorize: OLT tidak dikenal -> 404, tidak ada job dan tidak ada ONU dibuat.
            ra = await c.post("/api/onus/authorize", headers=_auth(admin), json={
                "olt_id": 10**9, "serial_number": "ZTEG00000001",
                "customer_id": f"cid-{tag}", "customer_name": "Budi"})
            assert ra.status_code == 404, ra.text

            # PPPoE tanpa username ditolak sebelum menyentuh OLT.
            rv = await c.post("/api/onus/authorize", headers=_auth(admin), json={
                "olt_id": 10**9, "serial_number": "ZTEG00000001",
                "customer_id": f"cid-{tag}", "customer_name": "Budi", "wan_mode": "pppoe"})
            assert rv.status_code in (400, 404, 422), rv.text

            assert (await c.get("/api/onus/pending", headers=_auth(admin))).status_code == 200
            assert (await c.get(f"/api/onus/customer-id-taken?customer_id=cid-{tag}",
                                headers=_auth(admin))).json() == {"taken": False}

            assert (await c.delete(f"/api/onu-presets/{ids['preset']}",
                                   headers=_auth(admin))).status_code == 204
            ids.pop("preset")
        print(f"C1: preset CRUD + scope OK, authorize guards OK (tag {tag})")
    finally:
        async with SessionLocal() as db:
            if "preset" in ids:
                await db.execute(text("DELETE FROM onu_presets WHERE id = :i"),
                                 {"i": ids["preset"]})
            if "type" in ids:
                await db.execute(text("DELETE FROM onu_types WHERE id = :i"), {"i": ids["type"]})
            await db.execute(text("DELETE FROM activity_logs WHERE user_id IN "
                                  "(SELECT id FROM users WHERE username LIKE :p)"),
                             {"p": f"c1_{tag}_%"})
            await db.execute(text("DELETE FROM users WHERE username LIKE :p"),
                             {"p": f"c1_{tag}_%"})
            await db.commit()
        await engine.dispose()
