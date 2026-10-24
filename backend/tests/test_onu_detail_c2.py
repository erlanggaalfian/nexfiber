"""Unit test Fase C2: bucket sinyal (backend == frontend), filter SQL bucket, export CSV,
dan aksi Detail ONU lewat driver palsu.

TIDAK ADA satu pun test di sini yang menyentuh OLT/ONU nyata: driver diganti objek palsu.
Keluaran CLI berasal dari teks fixture di file ini, kecuali satu test yang membaca
transkrip nyata (read-only) dari OLT SBI di tests/fixtures/cli/.
"""

import csv
import io
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.exceptions import CommandRejectedError, ConflictError
from app.core.signal import BUCKETS, bucket_filter, rx_bucket
from app.drivers.types import DriverResult
from app.drivers.zte_c320 import (
    _duration_seconds,
    _parse_attenuation,
    _parse_equip,
    _parse_onu_detail_info,
)
from app.models.onu import Onu
from app.schemas.onu import OnuRow
from app.services import onu_service

# --- bucket sinyal: harus identik dengan rxBucket() di frontend/src/components/data.tsx ---
# Tabel di bawah ditulis ulang dari fungsi TypeScript-nya, bukan dari rx_bucket(), supaya
# test ini benar-benar mendeteksi kalau salah satu sisi berubah sendiri.

def _rx_bucket_like_frontend(dbm: float | None) -> str:
    if dbm is None:
        return "los"
    if dbm > -8 or dbm <= -28:
        return "critical"
    if dbm < -27:
        return "weak"
    if dbm < -25:
        return "fair"
    return "good"


BOUNDARY_DBM = [None, -40.0, -28.1, -28.0, -27.9, -27.1, -27.0, -26.0, -25.1, -25.0,
                -24.0, -15.0, -8.1, -8.0, -7.9, 0.0, 3.0]


@pytest.mark.parametrize("dbm", BOUNDARY_DBM)
def test_rx_bucket_matches_frontend_rule(dbm):
    assert rx_bucket(dbm) == _rx_bucket_like_frontend(dbm)


def test_rx_bucket_boundaries_explicit():
    """Batas yang disebut DECISIONS.md, dipaku supaya tidak bergeser tanpa sengaja."""
    assert rx_bucket(None) == "los"
    assert rx_bucket(-28.0) == "critical"   # <= -28 masuk critical
    assert rx_bucket(-27.5) == "weak"
    assert rx_bucket(-27.0) == "fair"       # -27 sudah fair, bukan weak
    assert rx_bucket(-25.1) == "fair"
    assert rx_bucket(-25.0) == "good"       # -25 sudah good
    assert rx_bucket(-8.0) == "good"
    assert rx_bucket(-7.9) == "critical"    # kelewat kuat
    assert set(BUCKETS) == {"good", "fair", "weak", "critical", "los"}


def test_bucket_filter_sql_agrees_with_rx_bucket():
    """Predikat SQL dievaluasi di SQLite in-memory dan dibandingkan dengan rx_bucket()."""
    import sqlite3

    rows = [(i, v) for i, v in enumerate(BOUNDARY_DBM)]
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER, rx REAL)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", rows)

    from sqlalchemy import Column, Float, Integer, MetaData, Table
    from sqlalchemy.dialects import sqlite

    table = Table("t", MetaData(), Column("id", Integer), Column("rx", Float))
    for bucket in BUCKETS:
        stmt = select(table.c.id).where(bucket_filter(table.c.rx, bucket))
        sql = str(stmt.compile(dialect=sqlite.dialect(),
                               compile_kwargs={"literal_binds": True}))
        got = {r[0] for r in conn.execute(sql)}
        want = {i for i, v in rows if rx_bucket(v) == bucket}
        assert got == want, f"bucket {bucket}: SQL {got} != python {want}"
    conn.close()


def test_bucket_filter_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown rx bucket"):
        bucket_filter(Onu.rx_power_dbm, "mantap")


# --- export CSV ---------------------------------------------------------------

def _row(**over) -> OnuRow:
    base = dict(
        id=1, serial_number="ZTEGC1234567", name="Rumah A", customer_name="Budi",
        customer_id="C-001", olt_id=8, olt_name="OLT-TEST", slot=4, port=1, onu_index=11,
        onu_type="F660", status="online", config_state="success", admin_state="enabled",
        rx_power_dbm=-26.5, olt_rx_power_dbm=-18.2, download_profile_name="PAKET20_DN",
        upload_profile_name="PAKET20_UP",
        vlan_number=100, zone_name="Zona 1", splitter_name="SPL-01",
        last_seen_at=None, last_down_at=None, last_down_reason=None,
    )
    return OnuRow(**{**base, **over})


def test_csv_header_and_bucket_column():
    rows = list(onu_service.csv_rows([
        _row(rx_power_dbm=-26.5),                        # fair
        _row(id=2, serial_number="ZTEGC7654321", rx_power_dbm=None),  # los
        _row(id=3, serial_number="ZTEGC1111111", rx_power_dbm=-29.0),  # critical
    ]))
    header, *body = rows
    assert header[0] == "Serial Number"
    assert "Sinyal" in header
    signal_col = header.index("Sinyal")
    assert [r[signal_col] for r in body] == ["fair", "los", "critical"]
    # kolom RX kosong (bukan "None") kalau tidak ada bacaan
    rx_col = header.index("RX ONU (dBm)")
    assert body[1][rx_col] == ""


def test_csv_bytes_is_excel_safe_and_parsable():
    blob = onu_service.csv_bytes([_row(customer_name="Café Müller")])
    assert blob.startswith(b"\xef\xbb\xbf")  # BOM supaya Excel tidak merusak non-ASCII
    text = blob.decode("utf-8-sig")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0][0] == "Serial Number"
    assert "Café Müller" in parsed[1]
    assert parsed[1][header_index(parsed[0], "PON")] == "4/1"


def header_index(header: list[str], label: str) -> int:
    return header.index(label)


# --- parser keluaran CLI Detail ONU (fixture teks, bukan device) ----------------

DETAIL_INFO = """
ONU interface: gpon-onu_1/4/1:11
Name: Rumah A
Type: F660
State: enable
Admin state: enable
Phase state: working
Channel: 1
OMCC state: OMCI
Config state: success
Authentic type: SN
Serial number: ZTEGC1234567
Password:
Online Duration: 3 day 04:31:22
ONU Distance: 1832 m
ONU RX power: -26.514(dbm)
ONU TX power: 2.113(dbm)
OLT RX power: -18.240(dbm)
Temperature: 43.50(C)
Supply Voltage: 3.28(V)
Software version: V1.2.3P4
Hardware version: V5.0
"""

ATTENUATION = """
OltRxOnuTx: -18.24(dbm)   Up   Rx : -18.24(dbm)
OnuRxOltTx: -26.51(dbm)   Down Rx : -26.51(dbm)
"""

EQUIP = """
Active software version   : V1.2.3P4
Standby software version  : V1.2.2P9
Hardware version          : V5.0
"""


def test_parse_onu_detail_info():
    d = _parse_onu_detail_info(DETAIL_INFO)
    assert d.phase_state == "working"
    assert d.rx_power_dbm == -26.51
    assert d.tx_power_dbm == 2.11
    assert d.olt_rx_power_dbm == -18.24
    assert d.temperature_c == 43.5
    assert d.voltage_v == 3.28
    assert d.distance_m == 1832
    assert d.online_duration_s == 3 * 86400 + 4 * 3600 + 31 * 60 + 22
    assert d.software_version == "V1.2.3P4"


def test_parse_onu_detail_info_tolerates_garbage():
    """Format tak dikenal tidak boleh bikin job gagal: semua field tetap None."""
    d = _parse_onu_detail_info("ZXAN# \n%Error: invalid command\n")
    assert (d.rx_power_dbm, d.distance_m, d.phase_state) == (None, None, None)


def test_parse_onu_detail_distance_in_km():
    d = _parse_onu_detail_info("ONU Distance: 1.83(km)\n")
    assert d.distance_m == 1830


def test_parse_attenuation_only_fills_missing():
    rx, tx, olt_rx = _parse_attenuation(ATTENUATION, None, None, None)
    assert (rx, olt_rx) == (-26.51, -18.24)
    # nilai dari detail-info menang, attenuation tidak menimpanya
    rx2, _, _ = _parse_attenuation(ATTENUATION, -30.0, None, None)
    assert rx2 == -30.0


def test_parse_attenuation_falls_back_to_nm_format():
    # Format alternatif (verifikasi live, driver SmartOLT) saat label key:value absen.
    output = "1490nm Tx: 2.50 Rx: -21.30\n1310nm Rx: -16.80\n"
    rx, tx, olt_rx = _parse_attenuation(output, None, None, None)
    assert (rx, tx, olt_rx) == (-21.30, 2.50, -16.80)


def test_parse_equip_versions():
    active, standby, hardware = _parse_equip(EQUIP, None)
    assert (active, standby, hardware) == ("V1.2.3P4", "V1.2.2P9", "V5.0")


def test_parse_equip_real_transcript_olt_sbi_c300():
    # Transkrip CLI nyata `show gpon remote-onu equip` dari OLT SBI (C300, read-only,
    # 2026-10-24) — tidak ada label "active/standby software version" sama sekali,
    # cuma "Version" (firmware aktif) dan "Model" (tipe hardware). Standby selalu None.
    real = (Path(__file__).parent / "fixtures" / "cli"
            / "zte_show_gpon_remote_onu_equip.txt").read_text()
    active, standby, hardware = _parse_equip(real, None)
    assert (active, standby, hardware) == ("V7.1", None, "TF210G")


@pytest.mark.parametrize(("text", "want"), [
    ("04:31:22", 4 * 3600 + 31 * 60 + 22),
    ("12 day 00:00:01", 12 * 86400 + 1),
    ("unknown", None),
    ("", None),
])
def test_duration_seconds(text, want):
    assert _duration_seconds(text) == want


# --- aksi Detail ONU lewat driver palsu ---------------------------------------

class FakeDriver:
    """Mencatat panggilan; tidak ada koneksi jaringan sama sekali."""

    def __init__(self, success=True):
        self.success = success
        self.calls: list[tuple] = []

    async def fetch_onu_detail(self, slot, port, onu_id):
        self.calls.append(("fetch_onu_detail", slot, port, onu_id))
        detail = _parse_onu_detail_info(DETAIL_INFO)
        detail.software_version, detail.software_version_standby, detail.hardware_version = (
            _parse_equip(EQUIP, detail.hardware_version)
        )
        detail.running_config = "interface gpon-onu_1/4/1:11\n name Rumah A\n"
        detail.raw_command = "show gpon onu detail-info gpon-onu_1/4/1:11"
        return detail

    async def set_onu_vlan(self, slot, port, onu_id, old_vlan, new_vlan):
        self.calls.append(("set_onu_vlan", slot, port, onu_id, old_vlan, new_vlan))
        return self._result(f"flow 1 pri 0 vlan {new_vlan}")

    async def restore_factory(self, slot, port, onu_id):
        self.calls.append(("restore_factory", slot, port, onu_id))
        return self._result("restore factory")

    async def delete(self, slot, port, onu_id):
        self.calls.append(("delete", slot, port, onu_id))
        return self._result(f"no onu {onu_id}")

    def _result(self, command):
        return DriverResult(
            success=self.success, raw_command=command,
            raw_output="" if self.success else "%Error: command rejected",
            message="" if self.success else "OLT rejected command",
        )


class FakeJob:
    id = 42
    created_by = None
    olt_id = 8
    onu_id = 1

    def __init__(self, payload=None):
        self.payload = payload or {}


class FakeDb:
    def __init__(self, objects: dict | None = None):
        self.objects = objects or {}
        self.flushes = 0
        self.commits = 0

    async def get(self, model, pk):
        return self.objects.get((model.__name__, pk))

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1

    async def execute(self, _stmt):
        return None


def _onu() -> Onu:
    return Onu(
        id=1, olt_id=8, pon_port_id=3, serial_number="ZTEGC1234567", onu_index=11,
        status="online", config_state="success", admin_state="enabled", vlan_id=None,
    )


def _pon():
    from app.models.olt import PonPort

    return PonPort(id=3, olt_id=8, slot=4, port=1)


@pytest.fixture(autouse=True)
def _allow_writes(monkeypatch):
    monkeypatch.setattr("app.services.onu_service.settings.allow_write_commands", True)


@pytest.fixture
def patched(monkeypatch):
    """Ganti _load dan log_activity supaya service bisa diuji tanpa DB sungguhan."""
    onu, pon = _onu(), _pon()

    async def fake_load(_db, _job):
        return onu, pon

    async def noop(*_a, **_kw):
        return None

    monkeypatch.setattr(onu_service, "_load", fake_load)
    monkeypatch.setattr(onu_service, "log_activity", noop)
    return onu, pon


async def test_refresh_onu_detail_writes_optical_to_row(patched):
    onu, _ = patched
    driver = FakeDriver()
    out = await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), driver)
    assert driver.calls == [("fetch_onu_detail", 4, 1, 11)]
    assert onu.rx_power_dbm == -26.51
    assert onu.distance_m == 1832
    assert onu.software_version == "V1.2.3P4"
    assert onu.last_sync_at is not None
    # running-config tidak disimpan ke DB, hanya ikut di hasil job
    assert "interface gpon-onu_1/4/1:11" in out["running_config"]
    assert out["software_version_standby"] == "V1.2.2P9"


async def test_refresh_onu_detail_keeps_old_values_when_unparsed(patched, monkeypatch):
    onu, _ = patched
    onu.rx_power_dbm = -20.0
    driver = FakeDriver()

    async def empty_detail(*_a):
        from app.drivers.types import OnuLiveDetail

        return OnuLiveDetail(raw_command="x")

    monkeypatch.setattr(driver, "fetch_onu_detail", empty_detail)
    await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), driver)
    assert onu.rx_power_dbm == -20.0  # tidak ditimpa None


async def test_set_onu_vlan_passes_old_vlan_and_updates_row(patched):
    from app.models.vlan import Vlan

    onu, _ = patched
    onu.vlan_id = 7
    db = FakeDb({("Vlan", 9): Vlan(id=9, olt_id=8, vlan_id=200, name="NEW"),
                 ("Vlan", 7): Vlan(id=7, olt_id=8, vlan_id=100, name="OLD")})
    driver = FakeDriver()
    await onu_service.set_onu_vlan(db, FakeJob({"vlan_id": 9}), driver)
    assert driver.calls == [("set_onu_vlan", 4, 1, 11, 100, 200)]
    assert onu.vlan_id == 9


async def test_set_onu_vlan_rejected_keeps_old_vlan(patched):
    from app.models.vlan import Vlan

    onu, _ = patched
    onu.vlan_id = 7
    db = FakeDb({("Vlan", 9): Vlan(id=9, olt_id=8, vlan_id=200, name="NEW"),
                 ("Vlan", 7): Vlan(id=7, olt_id=8, vlan_id=100, name="OLD")})
    with pytest.raises(CommandRejectedError):
        await onu_service.set_onu_vlan(db, FakeJob({"vlan_id": 9}), FakeDriver(success=False))
    assert onu.vlan_id == 7


async def test_restore_factory_sends_command(patched):
    driver = FakeDriver()
    await onu_service.restore_factory(FakeDb(), FakeJob(), driver)
    assert driver.calls == [("restore_factory", 4, 1, 11)]


async def test_replace_onu_swaps_serial_and_clears_device_fields(patched, monkeypatch):
    onu, _ = patched
    onu.software_version = "V1.0"
    onu.mac_address = "AA:BB:CC:DD:EE:FF"
    driver = FakeDriver()

    async def no_dupe(*_a, **_kw):
        return False

    async def fake_authorize(_db, _job, _driver):
        return {"raw_command": "onu 11 type F660 sn ZTEGC9999999"}

    monkeypatch.setattr(onu_service.onu_repo, "exists_serial", no_dupe)
    monkeypatch.setattr(onu_service, "authorize_onu", fake_authorize)
    out = await onu_service.replace_onu(
        FakeDb(), FakeJob({"serial_number": "ZTEGC9999999"}), driver)
    assert ("delete", 4, 1, 11) in driver.calls
    assert onu.serial_number == "ZTEGC9999999"
    assert onu.software_version is None and onu.mac_address is None
    assert onu.config_state == "configuring"
    assert "no onu 11" in out["raw_command"]


async def test_replace_onu_rejects_serial_already_registered(patched, monkeypatch):
    async def dupe(*_a, **_kw):
        return True

    monkeypatch.setattr(onu_service.onu_repo, "exists_serial", dupe)
    with pytest.raises(ConflictError):
        await onu_service.replace_onu(
            FakeDb(), FakeJob({"serial_number": "ZTEGC9999999"}), FakeDriver())


async def test_resync_reuses_authorize(patched, monkeypatch):
    """Resync tidak boleh punya alur perintah sendiri (DRY, AGENTS.md)."""
    called = []

    async def fake_authorize(_db, _job, _driver):
        called.append(True)
        return {"raw_command": "onu 11 ..."}

    monkeypatch.setattr(onu_service, "authorize_onu", fake_authorize)
    await onu_service.resync_onu(FakeDb(), FakeJob(), FakeDriver())
    assert called == [True]


# --- aksi massal ---------------------------------------------------------------

async def test_enqueue_bulk_continues_after_each_failure(monkeypatch):
    """Regresi: ONU yang gagal validasi tidak boleh menghentikan sisa daftar.

    Bug nyata yang pernah terjadi: rollback setelah kegagalan validasi membuat objek ONU
    di identity map kedaluwarsa, sehingga serial berikutnya memicu lazy-load sinkron
    (sqlalchemy MissingGreenlet) dan seluruh request jadi HTTP 500.
    """
    provisioned = Onu(id=1, olt_id=8, pon_port_id=3, serial_number="OK1", onu_index=11,
                      status="online", config_state="success", admin_state="enabled")
    not_ready = Onu(id=2, olt_id=8, pon_port_id=3, serial_number="BELUM", onu_index=None,
                    status="unknown", config_state="configuring", admin_state="enabled")
    rows = {"OK1": (provisioned, "OLT", 4, 1, None, None, None, None),
            "BELUM": (not_ready, "OLT", 4, 1, None, None, None, None)}
    rollbacks = []

    async def fake_get_row(_db, serial, _user):
        if serial not in rows:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(f"ONU {serial} not found")
        return rows[serial]

    class CountingDb(FakeDb):
        async def rollback(self):
            rollbacks.append(True)

    async def fake_enqueue(_db, job_type, **_kw):
        return FakeJob()

    monkeypatch.setattr(onu_service, "_get_row", fake_get_row)
    monkeypatch.setattr(onu_service.job_service, "enqueue", fake_enqueue)

    out = await onu_service.enqueue_bulk(
        CountingDb(), ["OK1", "BELUM", "HILANG", "OK1"], "resync_onu", _user())

    assert [i["serial_number"] for i in out] == ["OK1", "BELUM", "HILANG"]  # duplikat dibuang
    assert out[0]["job_id"] == 42 and out[0]["error"] is None
    assert "not provisioned" in out[1]["error"]
    assert "not found" in out[2]["error"]
    assert rollbacks == []  # kegagalan validasi tidak memicu rollback


def _user():
    from app.models.user import User

    return User(id=1, username="admin", role="superadmin", full_name="Admin", is_active=True)


async def test_enqueue_bulk_rejects_empty_and_oversized():
    from app.core.exceptions import ValidationAppError

    with pytest.raises(ValidationAppError):
        await onu_service.enqueue_bulk(FakeDb(), [], "reboot_onu", _user())
    with pytest.raises(ValidationAppError, match="Maksimal"):
        await onu_service.enqueue_bulk(
            FakeDb(), [f"SN{i}" for i in range(onu_service.BULK_MAX + 1)], "reboot_onu", _user())
