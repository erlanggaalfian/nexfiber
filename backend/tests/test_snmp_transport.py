"""BUG NYATA (OLT SBI, 2026-10-24, read-only): pysnmp 6.x bulkCmd mengembalikan
var_binds sebagai list-per-OID, tiap elemen sendiri list berisi 1 tuple (oid, value)
-- bukan (oid, value) langsung. Unpack lama meledak "not enough values to unpack
(expected 2, got 1)" di SEMUA test_connection SNMP check sejak pysnmp di-upgrade.
"""
import pytest

from app.drivers.transport.snmp import SnmpTransport


@pytest.mark.asyncio
async def test_bulkwalk_unpacks_pysnmp6_nested_var_binds(monkeypatch):
    t = SnmpTransport("10.0.0.1", "public", 161)

    class FakeOid:
        def __init__(self, s):
            self._s = s

        def __str__(self):
            return self._s

    calls = {"n": 0}

    async def fake_bulk_cmd(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return (None, 0, 0, [[(FakeOid("1.3.6.1.2.1.1.1.0"), "hello")]])
        return (None, 0, 0, [[]])  # habis

    monkeypatch.setattr("app.drivers.transport.snmp.bulkCmd", fake_bulk_cmd)
    rows = await t.bulkwalk("1.3.6.1.2.1.1.1")
    assert rows == [("1.3.6.1.2.1.1.1.0", "hello")]


@pytest.mark.asyncio
async def test_bulkwalk_tidak_membocorkan_socket(monkeypatch):
    """BUG NYATA (worker produksi, 2026-10-26): engine SNMP dibuat sekali per
    SnmpTransport dan socket UDP-nya tak pernah ditutup; build_driver() membuat
    transport baru per job, jadi worker kehabisan fd (terukur 1021/1024) dan SEMUA job
    sesudahnya gagal "No module __SNMP-FRAMEWORK-MIB loaded".

    Kontraknya: satu walk = satu engine yang dispatcher-nya DITUTUP, sukses maupun gagal.
    """
    closed: list[str] = []

    class FakeDispatcher:
        def closeDispatcher(self) -> None:  # noqa: N802 - nama API pysnmp
            closed.append("x")

    class FakeEngine:
        def __init__(self) -> None:
            self.transportDispatcher = FakeDispatcher()  # noqa: N803 - nama API pysnmp

    monkeypatch.setattr("app.drivers.transport.snmp.SnmpEngine", FakeEngine)
    monkeypatch.setattr("app.drivers.transport.snmp.UdpTransportTarget", lambda *_a, **_k: None)

    async def ok_bulk_cmd(*_args, **_kwargs):
        return (None, 0, 0, [[]])

    async def boom_bulk_cmd(*_args, **_kwargs):
        raise OSError("device unreachable")

    t = SnmpTransport("10.0.0.1", "public", 161)

    monkeypatch.setattr("app.drivers.transport.snmp.bulkCmd", ok_bulk_cmd)
    for _ in range(3):
        await t.bulkwalk("1.3.6.1.2.1.1.1")
    assert len(closed) == 3, "socket walk sukses harus ditutup"

    monkeypatch.setattr("app.drivers.transport.snmp.bulkCmd", boom_bulk_cmd)
    with pytest.raises(OSError):
        await t.bulkwalk("1.3.6.1.2.1.1.1")
    assert len(closed) == 4, "socket walk GAGAL juga harus ditutup"
