"""Unit test LIVE traffic per-ONU (SNMP read-only). TIDAK menyentuh OLT/ONU nyata:
`SnmpTransport.bulkwalk` diganti fungsi palsu, nilai counter dari fixture di file ini.

Yang dipaku di sini:
- arah field (in = download ke ONU, out = upload dari ONU) tidak boleh tertukar;
- octet dikirim sebagai string desimal, termasuk nilai > 2**53 (BigInt frontend);
- counter_bits ikut tipe SNMP nyata (Counter32 vs Counter64);
- error OLT TIDAK pernah jadi angka 0;
- rate limit 1 per ONU per 3 detik ditegakkan di backend;
- ONU di luar scope -> 404 (lewat scope_olt_ids), bukan kebocoran data Admin lain.
"""

from pathlib import Path

import pytest

from app.core.exceptions import DriverError, NotFoundError
from app.drivers.zte_c320 import decode_optical_ifindex
from app.models.user import User
from app.schemas.onu_traffic import OnuTrafficSample
from app.services import onu_traffic_service as svc
from app.services.onu_traffic_service import RateLimitedError

RX = svc.OID_OLT_RX_OCTETS   # OLT terima dari ONU = upload pelanggan
TX = svc.OID_OLT_TX_OCTETS   # OLT kirim ke ONU   = download pelanggan
IFINDEX = svc.encode_perf_ifindex(1, 6)  # PON 1/6
ONU_INDEX = 11


class Counter64(int):
    """Berperan sebagai tipe pysnmp Counter64: deteksi lebar counter lewat nama kelas."""


class Counter32(int):
    pass


def _fake_walk(rows: dict[str, list[tuple[str, object]]]):
    async def walk(self, base_oid: str):  # noqa: ANN001
        return rows.get(base_oid, [])

    return walk


def _rows(up: object, down: object, onu_index: int = ONU_INDEX) -> dict:
    return {
        f"{RX}.{IFINDEX}": [(f"{RX}.{IFINDEX}.{onu_index}", up)],
        f"{TX}.{IFINDEX}": [(f"{TX}.{IFINDEX}.{onu_index}", down)],
    }


# --- index encoder: harus kebalikan persis decoder yang sudah ada di driver ---

@pytest.mark.parametrize(("slot", "port"), [(1, 1), (1, 6), (2, 4), (3, 16), (15, 8)])
def test_encode_perf_ifindex_roundtrips_driver_decoder(slot, port):
    assert decode_optical_ifindex(svc.encode_perf_ifindex(slot, port)) == (slot, port)


def test_encode_perf_ifindex_matches_known_value():
    """PON 1/6/1 = 285279745 (nilai nyata yang tercatat di zte_c320.decode_optical_ifindex)."""
    assert svc.encode_perf_ifindex(6, 1) == 285279745
    assert svc.encode_perf_ifindex(2, 4) == 285278724  # dokumen MIB ZTE: 0x11010204


# --- counter_bits ---

def test_counter_bits_from_snmp_type():
    assert svc.counter_bits(Counter64(5)) == 64
    assert svc.counter_bits(Counter32(5)) == 32
    assert svc.counter_bits(Counter32(0)) == 32  # counter kecil tetap 32, tidak ditebak


# --- pembacaan sample lewat service (DB + SNMP dipalsukan) ---

def _test_user(role: str = "admin") -> User:
    """User asli (belum disimpan) supaya rbac.scope_olt_ids benar-benar dijalankan."""
    u = User(username="t_traffic", full_name="t", password_hash="x", role=role)
    u.id = 7
    return u


class _FakeOnu:
    def __init__(self, serial="TEST0001", onu_index=ONU_INDEX, olt_id=1, onu_id=42):
        self.id = onu_id
        self.serial_number = serial
        self.onu_index = onu_index
        self.olt_id = olt_id


class _FakeOlt:
    host = "192.0.2.10"
    snmp_community_enc = b"enc"
    snmp_port = 161
    deleted_at = None
    id = 1


class _FakeDb:
    """Cukup untuk service: `db.get(Olt, id)` saja."""

    def __init__(self, olt=None):
        self._olt = olt

    async def get(self, _model, _pk):
        return self._olt


def _patch(monkeypatch, *, row, rows=None, olt=_FakeOlt()):
    async def get_row_by_serial(_db, _serial, _scope):
        return row

    monkeypatch.setattr("app.repositories.onu_repo.get_row_by_serial", get_row_by_serial)
    monkeypatch.setattr(svc, "decrypt_secret", lambda _b: "public")
    monkeypatch.setattr(
        "app.drivers.transport.snmp.SnmpTransport.bulkwalk", _fake_walk(rows or {})
    )
    svc._last_read.clear()
    return _FakeDb(olt)


def _row(onu=None, slot=1, port=6):
    return (onu or _FakeOnu(), "OLT8", slot, port)


async def test_read_sample_maps_direction_relative_to_onu(monkeypatch):
    """Kontrak arah: tabel ZTE Rx (sudut OLT) = upload = `out_octets`;
    Tx (sudut OLT) = download = `in_octets`. Kalau tertukar, grafik pelanggan terbalik."""
    db = _patch(monkeypatch, row=_row(),
                rows=_rows(up=Counter64(1_000), down=Counter64(9_000_000)))
    sample = await svc.read_sample(db, "TEST0001", user=_test_user())
    assert isinstance(sample, OnuTrafficSample)
    assert sample.in_octets == "9000000"   # masuk ke ONU = download
    assert sample.out_octets == "1000"     # keluar dari ONU = upload
    assert sample.counter_bits == 64
    assert sample.sampled_at.tzinfo is not None
    assert sample.serial_number == "TEST0001"


async def test_octets_are_decimal_strings_beyond_js_safe_integer(monkeypatch):
    big = 2**63 - 1
    db = _patch(monkeypatch, row=_row(), rows=_rows(up=Counter64(big), down=Counter64(big - 1)))
    sample = await svc.read_sample(db, "TEST0001", user=_test_user())
    assert sample.out_octets == str(big)
    assert sample.in_octets == str(big - 1)
    assert int(sample.out_octets) > 2**53  # frontend wajib BigInt, bukan Number
    assert sample.model_dump()["in_octets"] == str(big - 1)  # tetap string di JSON


async def test_counter32_reported_as_32_bits(monkeypatch):
    db = _patch(monkeypatch, row=_row(), rows=_rows(up=Counter32(10), down=Counter32(20)))
    sample = await svc.read_sample(db, "TEST0001", user=_test_user())
    assert sample.counter_bits == 32


async def test_mixed_width_reports_narrowest(monkeypatch):
    """Wrap terjadi pada counter tersempit; ambil yang paling kecil supaya frontend aman."""
    db = _patch(monkeypatch, row=_row(), rows=_rows(up=Counter32(10), down=Counter64(20)))
    assert (await svc.read_sample(db, "TEST0001", user=_test_user())).counter_bits == 32


# --- error: tidak ada angka nol palsu ---

async def test_missing_onu_row_raises_not_zero(monkeypatch):
    """ONU tidak ada di tabel performance -> error, BUKAN in/out = 0."""
    db = _patch(monkeypatch, row=_row(), rows=_rows(up=Counter64(1), down=Counter64(2),
                                                    onu_index=ONU_INDEX + 1))
    with pytest.raises(DriverError):
        await svc.read_sample(db, "TEST0001", user=_test_user())


async def test_snmp_failure_propagates(monkeypatch):
    async def boom(self, base_oid):  # noqa: ANN001
        raise DriverError(f"SNMP walk {base_oid} failed: timeout")

    db = _patch(monkeypatch, row=_row())
    monkeypatch.setattr("app.drivers.transport.snmp.SnmpTransport.bulkwalk", boom)
    with pytest.raises(DriverError):
        await svc.read_sample(db, "TEST0001", user=_test_user())


async def test_non_numeric_counter_raises(monkeypatch):
    db = _patch(monkeypatch, row=_row(), rows=_rows(up="No Such Object", down=Counter64(2)))
    with pytest.raises(DriverError):
        await svc.read_sample(db, "TEST0001", user=_test_user())


async def test_onu_without_index_not_found(monkeypatch):
    db = _patch(monkeypatch, row=_row(_FakeOnu(onu_index=None)))
    with pytest.raises(NotFoundError):
        await svc.read_sample(db, "TEST0001", user=_test_user())


# --- scope: ONU di luar scope OLT -> 404 ---

async def test_out_of_scope_onu_is_not_found(monkeypatch):
    """Repo mengembalikan None karena query sudah di-scope; service wajib 404, bukan 403/200."""
    db = _patch(monkeypatch, row=None)
    with pytest.raises(NotFoundError) as exc:
        await svc.read_sample(db, "OTHER-ADMIN-ONU", user=_test_user())
    assert exc.value.status_code == 404


async def test_service_uses_scope_olt_ids(monkeypatch):
    """Scope benar-benar diteruskan ke repo (bukan None diam-diam untuk role non-superadmin)."""
    seen = {}

    async def get_row_by_serial(_db, serial, scope):
        seen["serial"], seen["scope"] = serial, scope
        return None

    monkeypatch.setattr("app.repositories.onu_repo.get_row_by_serial", get_row_by_serial)
    monkeypatch.setattr(svc, "scope_olt_ids", lambda _u: "SCOPE-SENTINEL")
    with pytest.raises(NotFoundError):
        await svc.read_sample(_FakeDb(), "TEST0001", user=_test_user())
    assert seen == {"serial": "TEST0001", "scope": "SCOPE-SENTINEL"}


# --- rate limit: 1 pembacaan per ONU per 3 detik, ditegakkan backend ---

def test_rate_limit_rejects_second_read_within_window():
    svc._last_read.clear()
    svc._check_rate_limit(1, now=100.0)
    with pytest.raises(RateLimitedError) as exc:
        svc._check_rate_limit(1, now=100.0 + svc.MIN_INTERVAL_S - 0.1)
    assert exc.value.status_code == 429


def test_rate_limit_allows_after_window_and_is_per_onu():
    svc._last_read.clear()
    svc._check_rate_limit(1, now=100.0)
    svc._check_rate_limit(2, now=100.0)  # ONU lain tidak terkena
    svc._check_rate_limit(1, now=100.0 + svc.MIN_INTERVAL_S)  # tepat di batas: boleh
    assert svc.MIN_INTERVAL_S == 3.0


def test_rate_limit_table_is_bounded():
    svc._last_read.clear()
    for i in range(svc._MAX_TRACKED + 50):
        svc._check_rate_limit(i, now=float(i))
    assert len(svc._last_read) <= svc._MAX_TRACKED
    svc._last_read.clear()


async def test_second_read_within_window_rejected_end_to_end(monkeypatch):
    db = _patch(monkeypatch, row=_row(), rows=_rows(up=Counter64(1), down=Counter64(2)))
    await svc.read_sample(db, "TEST0001", user=_test_user())
    with pytest.raises(RateLimitedError):
        await svc.read_sample(db, "TEST0001", user=_test_user())


# --- endpoint terdaftar + no-store (tanpa menyentuh onus.py) ---

def test_endpoint_registered_with_no_store():
    """Diuji di level router module, bukan `app.main`: file `onus.py` dipegang track lain,
    import app.main bisa gagal karena pekerjaan mereka yang belum selesai, dan itu bukan
    kegagalan track ini. Registrasi di main.py tetap satu baris (lihat `main.py`)."""
    import inspect

    from fastapi.routing import APIRoute

    from app.routers import onu_traffic as router_mod

    paths = {r.path for r in router_mod.router.routes if isinstance(r, APIRoute)}
    assert paths == {"/api/onus/{serial}/traffic", "/api/onus/{serial}/traffic/history"}
    assert "no-store" in inspect.getsource(router_mod)
    main_src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "onu_traffic" in main_src
