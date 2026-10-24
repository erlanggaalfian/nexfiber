"""Unit test Fase C3 (Detail OLT): parser kesehatan OLT, tes koneksi CLI+SNMP dua boolean
terpisah, job gabungan sync_olt_metrics, dan push port uplink VLAN.

Semua lewat driver/transport palsu — TIDAK pernah menyentuh device nyata.
"""

import pytest

from app.core.exceptions import CommandRejectedError
from app.drivers.types import DriverResult, OltCard, OltHealth, PonPortInfo
from app.drivers.zte_c320 import (
    ZteC320Driver,
    _merge_card_load,
    _parse_cards,
    _parse_processor,
    _parse_software_version,
)
from app.services import olt_service, sync_service, vlan_service
from app.worker import handlers

# Transkrip nyata diambil read-only dari OLT SBI (103.210.52.64, 2026-10-24) — bukan
# dugaan lagi. show gpon onu uncfg di device ini kosong saat capture (tak ada ONU
# unconfigured), tidak dipakai di sini.
SHOW_CARD = """
Rack Shelf Slot CfgType RealType Port  HardVer SoftVer         Status
-------------------------------------------------------------------------------
1    1     0    PRWH    PRWH     0     V1.0.0                  INSERVICE
1    1     1    PRWH    PRWH     0     V1.0.0                  NOPOWER
1    1     3    GTGO             8                             OFFLINE
1    1     6    GTGO    GTGOG    8     V1.0.0  V2.1.0          INSERVICE
1    1     10   SCXM    SCXM     0     V1.0.0  V2.1.0          INSERVICE
OLT_C300_SBI_01#
"""

SHOW_PROCESSOR = """
Rack   Shelf    Slot   CPU(5s)   CPU(1m)    CPU(5m)   PhyMem(MB)  Memory
-------------------------------------------------------------------------------
1       1       6       13%       13%       13%       512         25%
1       1       10      12%       22%       19%       510         52%
OLT_C300_SBI_01#
"""

SHOW_VERSION = """
PhyLoc  FileType   VerType    VerTag            BuildTime           VerLength
-------------------------------------------------------------------------------
1/1/6   GTGOG      MVR        V2.1.0            2017-01-17 00:41:50 6906120
1/1/6   GTGOG      BT         V4.0.17           2018-10-30 00:50:09 524288
OLT_C300_SBI_01#
"""


def test_parse_cards_reads_slot_rows_only():
    cards = _parse_cards(SHOW_CARD)
    assert [c.slot for c in cards] == [0, 1, 3, 6, 10]
    assert cards[3].real_type == "GTGOG"
    assert cards[0].port_count == 0
    assert cards[2].status == "offline"
    # Slot tanpa RealType sama sekali tetap terbaca, Port-nya jangan jatuh ke RealType.
    assert cards[2].real_type == "GTGO"
    assert cards[2].port_count == 8


def test_parse_processor_maps_cpu_and_memory_per_slot():
    assert _parse_processor(SHOW_PROCESSOR) == {6: (13.0, 25.0), 10: (12.0, 52.0)}


def test_merge_card_load_attaches_load_and_keeps_processor_only_slots():
    cards = _merge_card_load(
        [OltCard(slot=6), OltCard(slot=10)], {6: (13.0, 25.0), 9: (2.0, 10.0)}
    )
    assert [(c.slot, c.cpu_pct, c.ram_pct) for c in cards] == [
        (6, 13.0, 25.0), (9, 2.0, 10.0), (10, None, None),
    ]


def test_parse_software_version():
    assert _parse_software_version(SHOW_VERSION) == "V2.1.0"
    assert _parse_software_version("") is None


# --- test_connection: dua boolean dari dua tes sungguhan --------------------
# DECISIONS "Audit fitur SmartOLT": status satu protokol TIDAK boleh ditentukan dari
# mencocokkan teks pesan protokol lain.

class FakeCli:
    def __init__(self, output="ZXA10 C320", fail=False):
        self.output, self.fail = output, fail

    async def __aenter__(self):
        if self.fail:
            raise OSError("connection refused")
        return self

    async def __aexit__(self, *_exc):
        return False

    async def send_command(self, _command):
        return self.output

    async def send_config_set(self, _commands):
        return self.output


class FakeSnmp:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail = rows or [], fail

    async def bulkwalk(self, _oid):
        if self.fail:
            raise OSError("snmp timeout")
        return self.rows


def _driver(cli=None, snmp=None) -> ZteC320Driver:
    driver = ZteC320Driver(host="192.0.2.1", cli_username="u", cli_password="p",
                           cli_protocol="ssh", cli_port=22, snmp_community="c", snmp_port=161)
    driver._open_cli = lambda: cli or FakeCli()  # noqa: SLF001 - test seam
    driver._snmp = snmp or FakeSnmp([("1.3.6.1.2.1.1.3.0", 100)])  # noqa: SLF001
    return driver


async def test_connection_both_protocols_ok():
    check = await _driver().test_connection()
    assert (check.cli_ok, check.snmp_ok) == (True, True)


async def test_connection_cli_down_snmp_up_reports_each_separately():
    check = await _driver(cli=FakeCli(fail=True)).test_connection()
    assert (check.cli_ok, check.snmp_ok) == (False, True)
    assert "CLI gagal" in check.cli_message
    assert check.snmp_message == "SNMP menjawab"


async def test_connection_snmp_down_does_not_flip_cli_result():
    """Regresi bug SmartOLT: SNMP mati tidak boleh membuat CLI dinilai gagal."""
    check = await _driver(snmp=FakeSnmp(fail=True)).test_connection()
    assert (check.cli_ok, check.snmp_ok) == (True, False)
    assert "SNMP gagal" in check.snmp_message


async def test_connection_cli_error_text_does_not_flip_snmp_result():
    """Kebalikannya: teks error CLI tidak boleh dipakai menilai SNMP."""
    check = await _driver(cli=FakeCli(output="% Invalid input detected")).test_connection()
    assert (check.cli_ok, check.snmp_ok) == (False, True)


# --- handler test_connection ------------------------------------------------

class FakeOlt:
    id = 8
    status = "unreachable"
    last_sync_at = None
    last_error = None


class FakeJob:
    id = 1
    created_by = None
    olt_id = 8
    result = None

    def __init__(self, payload=None):
        self.payload = payload or {}


async def test_handler_marks_online_when_only_one_protocol_answers():
    olt = FakeOlt()
    result = await handlers.test_connection(None, FakeJob(), olt,
                                            _driver(snmp=FakeSnmp(fail=True)))
    assert (result["cli_ok"], result["snmp_ok"]) == (True, False)
    assert olt.status == "online"
    assert "SNMP gagal" in olt.last_error  # satu protokol mati tetap dicatat


async def test_handler_fails_only_when_both_protocols_fail():
    olt = FakeOlt()
    driver = _driver(cli=FakeCli(fail=True), snmp=FakeSnmp(fail=True))
    with pytest.raises(CommandRejectedError):
        await handlers.test_connection(None, FakeJob(), olt, driver)
    assert olt.status == "unreachable"


# --- sync_olt_metrics: optical + health satu job ----------------------------

class MetricsDriver:
    def __init__(self):
        self.calls: list[str] = []

    async def fetch_optical(self, _slot, _port):
        self.calls.append("fetch_optical")
        return []

    async def fetch_health(self):
        self.calls.append("fetch_health")
        return OltHealth(cpu_pct=12.0, ram_pct=55.0, temperature_c=41.5, uptime_seconds=3600,
                         software_version="ZXA10 C320 V2.1.0", cards=[OltCard(slot=1)],
                         uplink_ports=["gei_1/5/1"])

    async def list_pon_ports(self):
        self.calls.append("list_pon_ports")
        return [PonPortInfo(slot=1, port=1, ifindex=268501248)]


class MetricsDb:
    """Cukup untuk sync_olt_metrics: tidak ada ONU, eksekusi SQL dicatat saja."""

    def __init__(self):
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        return _EmptyResult()

    def add(self, _obj):
        pass


class _EmptyResult:
    def __iter__(self):
        return iter(())


class MetricsOlt(FakeOlt):
    cpu_pct = ram_pct = temperature_c = uptime_seconds = software_version = None
    cards: list = []
    uplink_ports: list = []


async def test_sync_olt_metrics_writes_health_in_one_job():
    olt, driver = MetricsOlt(), MetricsDriver()
    out = await sync_service.sync_olt_metrics(MetricsDb(), olt, driver)
    assert "fetch_optical" in driver.calls and "fetch_health" in driver.calls
    assert (olt.cpu_pct, olt.ram_pct, olt.temperature_c) == (12.0, 55.0, 41.5)
    assert olt.software_version == "ZXA10 C320 V2.1.0"
    assert olt.cards == [{"slot": 1, "cfg_type": None, "real_type": None, "port_count": None,
                          "hardware_version": None, "software_version": None, "status": None,
                          "cpu_pct": None, "ram_pct": None}]
    assert olt.uplink_ports == ["gei_1/5/1"]
    assert olt.status == "online"
    assert out["cards"] == 1


def test_scheduler_has_no_separate_health_job():
    """DECISIONS: optical+health gabung di sync_olt_metrics, jangan ada sync_olt_health."""
    assert "sync_olt_metrics" in handlers.HANDLERS
    assert "sync_olt_health" not in handlers.HANDLERS


# --- VLAN: port uplink tagged/untagged --------------------------------------

class PortsDriver:
    def __init__(self, success=True):
        self.success, self.calls = success, []

    async def set_vlan_ports(self, vlan_id, ports):
        self.calls.append((vlan_id, ports))
        return DriverResult(success=self.success, raw_command=f"switchport vlan {vlan_id}",
                            raw_output="" if self.success else "%Error: command rejected",
                            message="" if self.success else "OLT rejected command")


class PortsDb:
    def __init__(self, obj):
        self.obj, self.commits = obj, 0

    async def get(self, _model, _pk):
        return self.obj

    async def commit(self):
        self.commits += 1


async def _noop_log(*_a, **_kw):
    return None


@pytest.fixture(autouse=True)
def _allow_writes(monkeypatch):
    monkeypatch.setattr("app.services.onu_service.settings.allow_write_commands", True)


async def test_push_ports_sends_tagged_untagged(monkeypatch):
    from app.models.vlan import Vlan

    vlan = Vlan(id=3, olt_id=8, vlan_id=100, name="INTERNET")
    driver = PortsDriver()
    monkeypatch.setattr(vlan_service, "log_activity", _noop_log)
    ports = {"gei_1/5/1": "tagged", "gei_1/5/2": "untagged"}
    out = await vlan_service.push_ports(PortsDb(vlan), FakeJob({"vlan_db_id": 3, "ports": ports}),
                                        driver)
    assert driver.calls == [(100, ports)]
    assert out["ports"] == 2


async def test_push_ports_rejected_raises(monkeypatch):
    from app.models.vlan import Vlan

    vlan = Vlan(id=3, olt_id=8, vlan_id=100, name="INTERNET")
    monkeypatch.setattr(vlan_service, "log_activity", _noop_log)
    with pytest.raises(CommandRejectedError):
        await vlan_service.push_ports(PortsDb(vlan), FakeJob({"vlan_db_id": 3, "ports": {}}),
                                      PortsDriver(success=False))


def test_driver_builds_hybrid_before_untag():
    """Kode 60584: `untag` ditolak selama port masih trunk, jadi hybrid harus lebih dulu."""
    import asyncio

    cli = FakeCli()
    driver = _driver(cli=cli)
    sent: list[list[str]] = []

    async def capture(commands):
        sent.append(commands)
        return ""

    cli.send_config_set = capture
    asyncio.run(driver.set_vlan_ports(100, {"gei_1/5/1": "untagged"}))
    assert sent == [["interface gei_1/5/1", "switchport mode hybrid",
                     "switchport vlan 100 untag", "exit"]]


# --- Tab Interfaces: push konfigurasi port uplink ----------------------------

class PortConfigDriver:
    def __init__(self, success=True):
        self.success, self.calls = success, []

    async def set_port_config(self, port, auto_nego, speed, duplex):
        self.calls.append((port, auto_nego, speed, duplex))
        return DriverResult(
            success=self.success, raw_command=f"interface {port} ; speed {speed}",
            raw_output="" if self.success else "%Error 20202: Invalid input detected",
            message="" if self.success else "OLT menolak perintah",
        )


async def test_push_port_config_returns_debug_log(monkeypatch):
    driver = PortConfigDriver()
    monkeypatch.setattr(olt_service, "log_activity", _noop_log)
    job = FakeJob({"port": "xgei_1/19/2", "auto_nego": "disable", "speed": "10000",
                   "duplex": "full"})
    out = await olt_service.push_port_config(PortsDb(None), job, driver)
    assert driver.calls == [("xgei_1/19/2", "disable", "10000", "full")]
    # Jejak CLI live yang ditampilkan di Drawer tab Interfaces.
    assert out["debug_log"]["command"] == "interface xgei_1/19/2 ; speed 10000"
    assert out["debug_log"]["success"] is True


async def test_push_port_config_rejected_keeps_debug_log(monkeypatch):
    """Saat gagal, jejak CLI harus tetap tersimpan di job.result sebelum error dilempar."""
    monkeypatch.setattr(olt_service, "log_activity", _noop_log)
    job = FakeJob({"port": "xgei_1/19/2", "auto_nego": "enable", "speed": None, "duplex": None})
    with pytest.raises(CommandRejectedError):
        await olt_service.push_port_config(PortsDb(None), job, PortConfigDriver(success=False))
    assert job.result["debug_log"]["success"] is False
    assert "%Error" in job.result["debug_log"]["output"]


def test_set_port_config_handler_registered():
    assert handlers.HANDLERS["set_port_config"] is handlers.set_port_config
