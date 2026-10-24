"""Regresi: URL Detail ONU memakai **id internal**, bukan serial number.

Dua lapis yang dipaku di sini:

1. **Frontend (teks sumber)** — rute tetap satu halaman `/onu/:id` dan setiap pembuat
   tautan (`<Link to>`/`navigate`) mengirim `o.id` / `job.onu_id`, bukan `serial_number`.
   Tidak ada runner JS di repo ini (pola sama dengan `test_onu_detail_layout.py`);
   kompilasi tipe tetap dijaga `tsc -b` di build frontend.
2. **Backend (DB nyata)** — `GET /api/onus/by-id/{onu_id}` mengembalikan `OnuDetail` yang
   identik dengan `GET /api/onus/{serial}`, dan **scope OLT tetap berlaku**: id ONU milik
   Admin lain = 404, id yang tidak ada = 404. Dilewati kalau Postgres mati
   (pola `tests/test_scope.py`).

API operasional (job, info, signal, logs, traffic) sengaja TETAP berkunci serial: halaman
detail memakai `serial_number` dari respons by-id, jadi tidak ada kontrak yang berubah
untuk track lain.
"""

import re
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from app.core.db import SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.user import User

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


# --- lapis 1: rute & pembuat tautan di frontend -------------------------------

def test_route_is_single_detail_page_keyed_by_id():
    main = (FRONTEND / "main.tsx").read_text(encoding="utf-8")
    onu_routes = re.findall(r'<Route path="(/onu/[^"]*)"', main)
    assert onu_routes == ["/onu/:id"], onu_routes


@pytest.mark.parametrize("page", ["pages/Configured.tsx", "pages/OltDetail.tsx",
                                  "pages/AuthorizeOnu.tsx"])
def test_links_never_put_serial_in_url(page: str):
    """Tiap `/onu/${...}` harus memakai id (`.id` / `onu_id` / `onuId`)."""
    src = (FRONTEND / page).read_text(encoding="utf-8")
    refs = re.findall(r"/onu/\$\{([^}]+)\}", src)
    assert refs, f"{page} tidak lagi membuat tautan Detail ONU?"
    for ref in refs:
        assert "serial" not in ref.lower(), f"{page}: /onu/${{{ref}}} masih memakai serial"
        assert re.search(r"\b(id|onu_id|onuId)\b", ref), f"{page}: /onu/${{{ref}}} bukan id"


def test_no_serial_url_left_anywhere_in_src():
    hits = []
    for path in FRONTEND.rglob("*.tsx"):
        for ref in re.findall(r"/onu/\$\{([^}]+)\}", path.read_text(encoding="utf-8")):
            if "serial" in ref.lower():
                hits.append(f"{path.name}: {ref}")
    assert hits == [], hits


def test_by_id_router_registered_before_serial_router():
    """`/api/onus/by-id/{id}` harus di-include sebelum `onus.router`, kalau tidak path
    parameter `/{serial}` akan menelannya."""
    main = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    order = re.search(r"for module in \(([^)]*)\)", main, re.S).group(1)
    names = [n.strip() for n in order.replace("\n", " ").split(",") if n.strip()]
    assert "onu_by_id" in names, names
    assert names.index("onu_by_id") < names.index("onus"), names


# --- lapis 2: resolver backend terhadap DB nyata ------------------------------

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


async def test_detail_accepts_internal_id_and_keeps_scope() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    serial = f"T{tag.upper()}"
    async with SessionLocal() as db:
        admin_a, admin_b = _user(tag + "a", "admin"), _user(tag + "b", "admin")
        db.add_all([admin_a, admin_b])
        await db.flush()
        olt = Olt(name=f"t_{tag}", host="192.0.2.3", vendor="zte", model="C320",
                  cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                  owner_id=admin_a.id, pon_port_count=16,
                  cli_port=20000 + int(tag, 16) % 40000)
        db.add(olt)
        await db.flush()
        pon = PonPort(olt_id=olt.id, slot=1, port=4)
        db.add(pon)
        await db.flush()
        onu = Onu(olt_id=olt.id, pon_port_id=pon.id, onu_index=11, serial_number=serial,
                  auth_type="sn", status="unknown", config_state="success",
                  admin_state="enabled")
        db.add(onu)
        await db.commit()
        onu_id, olt_id, pon_id = onu.id, olt.id, pon.id
        ids = [admin_a.id, admin_b.id]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            by_id = await c.get(f"/api/onus/by-id/{onu_id}", headers=_auth(admin_a))
            by_serial = await c.get(f"/api/onus/{serial}", headers=_auth(admin_a))
            other_admin = await c.get(f"/api/onus/by-id/{onu_id}", headers=_auth(admin_b))
            missing = await c.get("/api/onus/by-id/999999999", headers=_auth(admin_a))
            # `by-id` tidak boleh ketelan path `/{serial}`: serial literal "by-id" mustahil,
            # tapi pastikan juga serial masih jalan setelah router baru di-include.
            bogus_serial = await c.get("/api/onus/TIDAKADA", headers=_auth(admin_a))
        assert by_id.status_code == 200, by_id.text
        assert by_id.json()["id"] == onu_id
        assert by_id.json()["serial_number"] == serial
        assert by_serial.status_code == 200
        assert by_serial.json() == by_id.json()
        assert other_admin.status_code == 404, "id internal tidak boleh membocorkan lintas scope"
        assert missing.status_code == 404
        assert bogus_serial.status_code == 404
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(Onu).where(Onu.id == onu_id))
            await db.execute(delete(PonPort).where(PonPort.id == pon_id))
            await db.execute(delete(Olt).where(Olt.id == olt_id))
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()
        await engine.dispose()
