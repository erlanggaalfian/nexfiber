"""Regresi diagnostik Detail ONU: parser/formatter per blok, job, dan RBAC.

TIDAK ADA satu pun test di sini yang menyentuh OLT/ONU nyata — driver diganti objek
palsu dan seluruh keluaran CLI berasal dari teks fixture di file ini.

Fixture SENGAJA memakai nilai sintetis untuk apa pun yang berbentuk kredensial
(`SECRET-NOT-REAL`): contoh output asli milik user memuat kredensial nyata dan tidak
boleh disalin ke repo.
"""

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, ValidationAppError
from app.drivers import onu_report
from app.drivers.types import OnuReport, OpticalSample
from app.models.job import JobType
from app.models.olt import PonPort
from app.models.onu import Onu
from app.models.user import User
from app.services import onu_service
from app.worker.handlers import HANDLERS

# --- fixture teks CLI ---------------------------------------------------------------

ATTENUATION = """\
ZXAN#show pon power attenuation gpon-onu_1/4/1:11
Wavelength  OLT                   ONU                  Attenuation
1310nm      Rx :-18.240(dbm)      Tx:2.250(dbm)        20.490(dB)
1490nm      Tx :7.236(dbm)        Rx:-26.576(dbm)      33.812(dB)
"""

CATV = """\
Admin status:        unlock
State:               disabled
1550nm Rx:           N/A(dBm)
RF output:           N/A(dBuV)
"""

DETAIL_INFO = """\
ONU interface: gpon-onu_1/4/1:11
Name: Rumah A
Type: F660
State: ready
Admin state: enable
Phase state: working
Serial number: TESTSN000011
ONU Distance: 1832 m
Online Duration: 3 day 04:31:22
History:
     Authpass Time          OfflineTime             Cause
 1   2026-08-05 14:53:24    2026-08-06 10:10:55     Power Fail
 2   2026-08-06 10:14:46    ONU is currently online
Software version: V1.2.3P4
"""

IP_HOST = """\
Host ID: 1
MAC address: 0011.2233.4455
Current IP address: 10.0.0.9
Current mask: 255.255.255.0
"""

ETH = """\
Port          Speed        Admin     Max-frame  Status changes
eth_0/1       auto         unlock    1632       3
"""

VLAN = """\
Interface     Mode        VLAN-ID    Def-Prio    Vlan-list
eth_0/1       tag         100        0           100
"""

VOIP = """\
Tel line:           pots_0/1
Service status:     none
"""

MACS = """\
Mac address         Vlan  Type      Port                     Vc
0011.2233.4455      100   Dynamic   gpon-onu_1/4/1:11        vport 1
"""

OLT_IFACE_CONFIG = """\
ZXAN#show running-config interface gpon-olt_1/4/1
Building configuration...
interface gpon-olt_1/4/1
 onu 10 type ALL-ONT sn TESTSN000010
 onu 11 type F660 sn TESTSN000011
 onu 12 type ALL-ONT sn TESTSN000012
!
end
"""

ONU_IFACE_CONFIG = """\
ZXAN#show running-config interface gpon-onu_1/4/1:11
Building configuration...
interface gpon-onu_1/4/1:11
 name Rumah A
 tcont 1 profile PAKET20_UP
 gemport 1 tcont 1
 service-port 1 vport 1 user-vlan 100 vlan 100
!
end
"""

ONU_MNG_CONFIG = """\
ZXAN#show onu running config gpon-onu_1/4/1:11
pon-onu-mng gpon-onu_1/4/1:11
 flow 1 pri 0 vlan 100
 pppoe 1 nat enable user fixture@example.invalid password SECRET-NOT-REAL
 wifi-ssid 1 name FIXTURE-SSID key SECRET-NOT-REAL
!
end
"""

EQUIP = """\
Vendor ID            : ZTEG
Version              : V5.3
SN                   : TESTSN000011
OMCC version         : b2
Model                : F660
"""

CAPABILITY = """\
Ethernet UNI number  : 4 (10GE:0 GE:4 FE:0)
POTS UNI number      : 1
Video UNI number     : 0
WIFI UNI number      : 4
"""

ERROR_OUT = "ZXAN#show gpon remote-onu catv gpon-onu_1/4/1:11\n%Error 20200 Invalid command.\n"

# Pola khas data demo aplikasi referensi; tidak boleh pernah muncul dari Nexfiber.
REFERENCE_DEMO_STRINGS = (
    "ec6c.b532.be20", "172.29.24.246", "eth_0/1       auto         unlock    1632       0",
    "Tel line:           pots_0/1\nService status:     none\nTel line:           pots_0/2",
    "DEMOSN000001", "F609V5.3", "10438m",
)


# --- formatter per blok -------------------------------------------------------------

def test_clean_output_drops_echo_and_prompt_keeps_content():
    cleaned = onu_report.clean_output(ATTENUATION)
    assert not cleaned.startswith("ZXAN#")
    assert "1310nm      Rx :-18.240(dbm)" in cleaned
    assert "Wavelength  OLT" in cleaned


def test_block_text_marks_missing_output_instead_of_inventing():
    assert onu_report.block_text("") == onu_report.NOT_REPORTED
    assert onu_report.block_text("   \n\n") == onu_report.NOT_REPORTED


def test_block_text_shows_device_error_verbatim():
    body = onu_report.block_text(ERROR_OUT)
    assert "%Error 20200 Invalid command." in body
    assert onu_report.NOT_REPORTED not in body


def test_status_report_block_titles_and_order_are_the_contract():
    output = _status_output()
    positions = [output.index(title) for title in onu_report.STATUS_BLOCKS]
    assert positions == sorted(positions), "urutan blok Status berubah"
    assert output.startswith("Optical status\n")


def test_status_report_appends_snmp_olt_rx_line():
    output = _status_output(olt_rx_dbm=-18.24)
    assert "1310nm OLT Rx for this ONU: -18.24 (dBm) [SNMP]" in output
    # tanpa nilai SNMP baris itu tidak muncul (bukan "N/A" palsu)
    assert "[SNMP]" not in _status_output()


def test_status_report_history_comes_from_detail_info_without_extra_command():
    output = _status_output()
    history = output.split("History\n", 1)[1].split("\n\nONU WAN", 1)[0]
    assert "Power Fail" in history
    assert "ONU is currently online" in history


def test_status_report_history_missing_is_marked_not_fabricated():
    assert onu_report.history_block("Name: X\nType: F660\n") == onu_report.NOT_REPORTED


def test_status_report_empty_device_answers_never_fabricate_demo_data():
    output = onu_report.status_report(
        attenuation="", catv="", detail_info="", ip_host="", eth="", vlan="", voip="", macs="",
    )
    for title in onu_report.STATUS_BLOCKS:
        assert f"{title}\n{onu_report.NOT_REPORTED}" in output
    for demo in REFERENCE_DEMO_STRINGS:
        assert demo not in output


def test_running_config_report_has_three_blocks_separated_by_bang():
    output = _running_output()
    assert output.count("\n!\n") == 2
    assert output.endswith("\n!")
    assert output.index("interface gpon-olt_1/4/1") < output.index("interface gpon-onu_1/4/1:11")
    assert output.index("interface gpon-onu_1/4/1:11") < output.index("pon-onu-mng")


def test_running_config_registration_block_filters_only_this_onu():
    block = onu_report.registration_block(DETAIL_INFO, "1/4/1", 11)
    assert "onu 11 type F660 sn TESTSN000011" in block
    assert "TESTSN000010" not in block and "TESTSN000012" not in block


def test_running_config_is_unmasked_by_explicit_decision():
    """User eksplisit minta config TIDAK disamarkan untuk tampilan berwenang.

    Pagar keamanannya ada di RBAC + tidak disimpan/dilog, bukan di masking.
    """
    output = _running_output()
    assert "password SECRET-NOT-REAL" in output
    assert "key SECRET-NOT-REAL" in output
    assert "[REDACTED]" not in output and "***" not in output


def test_running_config_missing_block_marked_not_reported():
    output = onu_report.running_config_report(
        detail_info="", onu_iface_config=ONU_IFACE_CONFIG, onu_mng_config="",
        pon="1/4/1", onu_id=11,
    )
    assert output.count(onu_report.NOT_REPORTED) == 2
    assert "service-port 1 vport 1 user-vlan 100 vlan 100" in output


def test_running_config_strips_end_and_trailing_bang_without_losing_lines():
    output = _running_output()
    assert "\nend" not in output
    assert "Building configuration..." not in output
    assert output.count("!") == 3  # 2 separator + 1 penutup


def test_software_report_blocks_and_region_not_fabricated():
    output = onu_report.software_report(equip=EQUIP, capability=CAPABILITY)
    positions = [output.index(title) for title in onu_report.SOFTWARE_BLOCKS]
    assert positions == sorted(positions)
    assert "OMCC version         : b2" in output
    assert "Ethernet UNI number  : 4 (10GE:0 GE:4 FE:0)" in output
    # Region 1/2 OMCI-only: ditulis apa adanya sebagai tidak dilaporkan, bukan angka tebakan
    region = output.split("Software Region\n", 1)[1]
    assert onu_report.NOT_REPORTED in region
    assert "Active: yes" not in output


def test_software_report_shows_regions_when_device_reports_them():
    equip = EQUIP + "Region 1 version : V1.0.0  Active: yes\nRegion 2 version : V0.9.9\n"
    output = onu_report.software_report(equip=equip, capability=CAPABILITY)
    assert "Region 1 version : V1.0.0  Active: yes" in output
    assert onu_report.NOT_REPORTED not in output.split("Software Region\n", 1)[1]


def _status_output(olt_rx_dbm=None) -> str:
    return onu_report.status_report(
        attenuation=ATTENUATION, catv=CATV, detail_info=DETAIL_INFO, ip_host=IP_HOST,
        eth=ETH, vlan=VLAN, voip=VOIP, macs=MACS, olt_rx_dbm=olt_rx_dbm,
    )


def _running_output() -> str:
    return onu_report.running_config_report(
        detail_info=DETAIL_INFO, onu_iface_config=ONU_IFACE_CONFIG,
        onu_mng_config=ONU_MNG_CONFIG, pon="1/4/1", onu_id=11,
    )


# --- driver: satu sesi CLI, command yang dipakai -----------------------------------

class FakeCli:
    def __init__(self, replies: dict[str, str], log: list[str]):
        self._replies, self._log = replies, log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def send_command(self, command: str) -> str:
        self._log.append(command)
        return self._replies.get(command, "")

    show = send_command


def _driver(replies: dict[str, str]) -> tuple:
    from app.drivers.zte_c320 import ZteC320Driver

    driver = ZteC320Driver(
        host="127.0.0.1", cli_username="u", cli_password="p", cli_protocol="ssh",
        cli_port=22, snmp_community="c", snmp_port=161,
    )
    log: list[str] = []
    sessions: list[int] = []

    def open_cli():
        sessions.append(1)
        return FakeCli(replies, log)

    driver._open_cli = open_cli  # noqa: SLF001 - test double, tidak ada device nyata
    return driver, log, sessions


async def test_driver_status_report_uses_allowed_commands_in_one_session():
    iface = "gpon-onu_1/4/1:11"
    replies = {
        f"show pon power attenuation {iface}": ATTENUATION,
        f"show gpon remote-onu catv {iface}": CATV,
        f"show gpon onu detail-info {iface}": DETAIL_INFO,
        f"show gpon remote-onu ip-host {iface}": IP_HOST,
        f"show gpon remote-onu interface eth {iface}": ETH,
        f"show gpon remote-onu vlan {iface}": VLAN,
        f"show gpon remote-onu voip {iface}": VOIP,
        f"show mac gpon onu {iface}": MACS,
    }
    driver, log, sessions = _driver(replies)

    async def fake_optical(slot, port):
        assert (slot, port) == (4, 1)
        return [OpticalSample(slot=4, port=1, onu_id=11, olt_rx_power_dbm=-18.24)]

    driver.fetch_optical = fake_optical
    report = await driver.fetch_onu_status_report(4, 1, 11)

    assert isinstance(report, OnuReport) and report.view == "status"
    assert log == list(replies)  # urutan command persis, tidak ada command tambahan
    assert len(sessions) == 1  # satu sesi CLI untuk semua command (PRD 4.3)
    assert "[SNMP]" not in report.output  # Rx OLT sudah ada di output attenuation CLI
    # command yang terdaftar "Ditolak" di NEXFIBER-CLI-REFERENCE tidak boleh dipakai
    for banned in ("wan-info", "eth-status", "traffic-info", f"show mac {iface}"):
        assert banned not in report.raw_command


async def test_driver_running_config_report_reads_three_blocks():
    pon, iface = "1/4/1", "gpon-onu_1/4/1:11"
    replies = {
        f"show gpon onu detail-info {iface}": DETAIL_INFO,
        f"show running-config interface {iface}": ONU_IFACE_CONFIG,
        f"show onu running config {iface}": ONU_MNG_CONFIG,
    }
    driver, log, sessions = _driver(replies)
    report = await driver.fetch_onu_running_config(4, 1, 11)
    assert log == list(replies)
    assert len(sessions) == 1
    assert report.view == "running"
    assert report.output.count("\n!\n") == 2
    # tidak ada `| include` (bentuk belum terverifikasi di CLI-REFERENCE)
    assert "|" not in report.raw_command


async def test_driver_software_report_reads_equip_and_capability():
    iface = "gpon-onu_1/4/1:11"
    replies = {
        f"show gpon remote-onu equip {iface}": EQUIP,
        f"show gpon remote-onu capability {iface}": CAPABILITY,
    }
    driver, log, sessions = _driver(replies)
    report = await driver.fetch_onu_software_report(4, 1, 11)
    assert log == list(replies)
    assert len(sessions) == 1
    assert report.view == "software"
    assert "Model                : F660" in report.output


# --- job: handler terdaftar, enum, hasil ------------------------------------------

def test_diagnostic_job_types_registered_everywhere():
    """Enum DB, HANDLERS worker, dan map service harus sepakat (satu sumber per lapis)."""
    expected = {"read_onu_status", "read_onu_running_config", "read_onu_software"}
    assert expected <= set(JobType.enums)
    assert expected <= set(HANDLERS)
    assert set(onu_service.DIAGNOSTIC_JOBS.values()) == expected


class FakeDb:
    def __init__(self, users: dict[int, User] | None = None):
        self._users, self.commits = users or {}, 0

    async def get(self, model, pk, **_kw):
        return self._users.get(pk) if model is User else None

    async def commit(self):
        self.commits += 1

    async def flush(self):
        return None

    async def rollback(self):
        return None


class FakeJob:
    def __init__(self, created_by=1, view="status"):
        self.id, self.onu_id, self.olt_id = 7, 1, 8
        self.created_by, self.payload = created_by, {"view": view}


class ReportDriver:
    def __init__(self):
        self.calls: list[tuple] = []

    async def fetch_onu_status_report(self, slot, port, onu_id):
        self.calls.append(("status", slot, port, onu_id))
        return OnuReport(view="status", output=_status_output(), raw_command="show ...")

    async def fetch_onu_running_config(self, slot, port, onu_id):
        self.calls.append(("running", slot, port, onu_id))
        return OnuReport(view="running", output=_running_output(), raw_command="show ...")

    async def fetch_onu_software_report(self, slot, port, onu_id):
        self.calls.append(("software", slot, port, onu_id))
        return OnuReport(
            view="software",
            output=onu_report.software_report(equip=EQUIP, capability=CAPABILITY),
            raw_command="show ...",
        )


@pytest.fixture
def patched(monkeypatch):
    onu = Onu(id=1, olt_id=8, pon_port_id=3, serial_number="TESTSN000011", onu_index=11,
              status="online", config_state="success", admin_state="enabled")
    pon = PonPort(id=3, olt_id=8, slot=4, port=1)
    logs: list[dict] = []

    async def fake_load(_db, _job):
        return onu, pon

    async def fake_log(_db, **kw):
        logs.append(kw)

    monkeypatch.setattr(onu_service, "_load", fake_load)
    monkeypatch.setattr(onu_service, "log_activity", fake_log)
    return onu, pon, logs


async def test_read_onu_status_job_returns_output_and_view(patched):
    driver = ReportDriver()
    result = await onu_service.read_onu_status(FakeDb(), FakeJob(), driver)
    assert driver.calls == [("status", 4, 1, 11)]
    assert result["view"] == "status"
    assert result["output"].startswith("Optical status\n")


async def test_read_onu_software_job_returns_output(patched):
    driver = ReportDriver()
    result = await onu_service.read_onu_software(FakeDb(), FakeJob(view="software"), driver)
    assert driver.calls == [("software", 4, 1, 11)]
    assert result["view"] == "software"
    assert "Features reported by ONU" in result["output"]


async def test_diagnostic_job_never_writes_output_to_activity_logs(patched):
    """Output (terutama running-config) tidak boleh ikut ke activity_logs/backup."""
    _onu, _pon, logs = patched
    db = FakeDb({1: User(id=1, role="admin")})
    result = await onu_service.read_onu_running_config(db, FakeJob(), ReportDriver())
    assert "SECRET-NOT-REAL" in result["output"]  # sampai ke UI lewat job.result
    assert len(logs) == 1
    entry = logs[0]
    assert entry.get("raw_output") is None
    assert "SECRET-NOT-REAL" not in repr(entry)
    assert entry["after"]["lines"] > 0  # jejak akses: jumlah baris saja
    assert entry["action"] == "onu.read_running"


async def test_read_running_config_job_rejects_non_manager_creator(patched):
    db = FakeDb({1: User(id=1, role="user")})
    with pytest.raises(ForbiddenError):
        await onu_service.read_onu_running_config(db, FakeJob(), ReportDriver())


async def test_read_running_config_job_rejects_missing_creator(patched):
    with pytest.raises(ForbiddenError):
        await onu_service.read_onu_running_config(FakeDb(), FakeJob(created_by=None),
                                                  ReportDriver())


# --- RBAC enqueue ------------------------------------------------------------------

@pytest.fixture
def enqueue_patched(monkeypatch):
    onu = Onu(id=1, olt_id=8, pon_port_id=3, serial_number="TESTSN000011", onu_index=11,
              status="online", config_state="success", admin_state="enabled")
    enqueued: list[dict] = []
    state = {"active": False}

    async def fake_get_row(_db, serial, _user):
        if serial != onu.serial_number:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(f"ONU {serial} not found")
        return (onu, "OLT-TEST", 4, 1, None, None, None, None, None, None, None)

    async def fake_exists_active(_db, _onu_id, job_type):
        return state["active"]

    async def fake_enqueue(_db, job_type, **kw):
        enqueued.append({"job_type": job_type, **kw})
        return type("J", (), {"id": 42})()

    monkeypatch.setattr(onu_service, "_get_row", fake_get_row)
    monkeypatch.setattr(onu_service.job_repo, "exists_active_for_onu", fake_exists_active)
    monkeypatch.setattr(onu_service.job_service, "enqueue", fake_enqueue)
    return onu, enqueued, state


@pytest.mark.parametrize("role", ["superadmin", "admin"])
async def test_enqueue_running_config_allowed_for_managers(enqueue_patched, role):
    _onu, enqueued, _state = enqueue_patched
    job_id = await onu_service.enqueue_diagnostic(
        FakeDb(), "TESTSN000011", "running", User(id=1, role=role))
    assert job_id == 42
    assert enqueued[0]["job_type"] == "read_onu_running_config"
    assert enqueued[0]["payload"] == {"view": "running"}


async def test_enqueue_running_config_forbidden_for_role_user(enqueue_patched):
    _onu, enqueued, _state = enqueue_patched
    with pytest.raises(ForbiddenError):
        await onu_service.enqueue_diagnostic(
            FakeDb(), "TESTSN000011", "running", User(id=2, role="user"))
    assert enqueued == []


@pytest.mark.parametrize("view", ["status", "software"])
async def test_enqueue_status_and_software_allowed_for_role_user(enqueue_patched, view):
    _onu, enqueued, _state = enqueue_patched
    await onu_service.enqueue_diagnostic(FakeDb(), "TESTSN000011", view, User(id=2, role="user"))
    assert enqueued[0]["job_type"] == onu_service.DIAGNOSTIC_JOBS[view]


async def test_enqueue_out_of_scope_onu_is_404_not_403(enqueue_patched):
    """Di luar scope = 404 (AGENTS.md), supaya data Admin lain tidak terbocorkan."""
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await onu_service.enqueue_diagnostic(
            FakeDb(), "OTHERSN00001", "running", User(id=1, role="superadmin"))


async def test_enqueue_rejects_unknown_view(enqueue_patched):
    with pytest.raises(ValidationAppError):
        await onu_service.enqueue_diagnostic(
            FakeDb(), "TESTSN000011", "wifi", User(id=1, role="admin"))


async def test_enqueue_debounces_while_same_job_active(enqueue_patched):
    _onu, enqueued, state = enqueue_patched
    state["active"] = True
    with pytest.raises(ConflictError):
        await onu_service.enqueue_diagnostic(
            FakeDb(), "TESTSN000011", "status", User(id=1, role="admin"))
    assert enqueued == []


async def test_enqueue_diagnostic_tidak_retry_otomatis(enqueue_patched):
    """Pembacaan manual read-only: 1 percobaan saja.

    BUG NYATA (produksi 2026-10-26): dengan max_attempts=3 satu klik yang gagal menahan
    tombol ~90 detik (backoff 30s+60s) dan selama itu klik ulang dijawab 409 "Pembacaan
    untuk ONU ini masih berjalan, tunggu selesai." — padahal job-nya sudah gagal.
    """
    _onu, enqueued, _state = enqueue_patched
    await onu_service.enqueue_diagnostic(
        FakeDb(), "TESTSN000011", "status", User(id=1, role="admin"))
    assert enqueued[0]["max_attempts"] == 1


async def test_enqueue_diagnostic_is_readonly_even_when_writes_disabled(enqueue_patched,
                                                                        monkeypatch):
    """Diagnostik read-only harus tetap jalan saat ALLOW_WRITE_COMMANDS=false."""
    monkeypatch.setattr("app.services.onu_service.settings.allow_write_commands", False)
    job_id = await onu_service.enqueue_diagnostic(
        FakeDb(), "TESTSN000011", "status", User(id=1, role="admin"))
    assert job_id == 42


# --- tidak ada persistensi permanen ------------------------------------------------

def test_no_db_column_stores_diagnostic_output():
    """Aplikasi referensi menyimpan output ke onus.last_status_cli / last_running_config.

    Nexfiber sengaja tidak: hasil hidup di jobs.result saja (retensi job), karena
    running-config memuat kredensial dan kolom DB ikut ke backup.
    """
    columns = set(Onu.__table__.columns.keys())
    assert not {"last_status_cli", "last_running_config"} & columns


def test_refresh_onu_detail_no_longer_logs_running_config(patched):
    """Regresi: refresh_onu_detail dulu menulis running-config penuh ke raw_output."""
    import inspect

    source = inspect.getsource(onu_service.refresh_onu_detail)
    assert "raw_output=detail.running_config" not in source


def test_parse_pppoe_from_running_config():
    from app.drivers.onu_report import parse_pppoe
    cfg = "pon-onu-mng gpon-onu_1/1/1:1\n  pppoe 1 nat enable user a@b.invalid password X-NOT-REAL\n"
    assert parse_pppoe(cfg) == ("a@b.invalid", "X-NOT-REAL")
    assert parse_pppoe("  ip-host 2 ip 10.0.0.2 mask 255.255.255.0") is None


def test_sync_wan_from_running_sets_pppoe_and_keeps_secret_encrypted():
    from types import SimpleNamespace
    from app.core.security import decrypt_secret
    from app.services.onu_service import _sync_wan_from_running
    onu = SimpleNamespace(wan_mode="dhcp", onu_mode=None, pppoe_username=None, pppoe_password_enc=None)
    _sync_wan_from_running(onu, "  pppoe 1 nat enable user u@x.invalid password P-NOT-REAL")
    assert (onu.wan_mode, onu.onu_mode, onu.pppoe_username) == ("pppoe", "routing", "u@x.invalid")
    assert decrypt_secret(onu.pppoe_password_enc) == "P-NOT-REAL"
    _sync_wan_from_running(onu, "tanpa pppoe")
    assert onu.wan_mode == "pppoe"


def test_inventory_parses_pppoe_per_onu():
    from app.drivers.zte_c320 import _parse_onu_pppoe
    cfg = ("interface gpon-onu_1/3/6:59\n  name X\n!\npon-onu-mng gpon-onu_1/3/6:59\n"
           "  pppoe 1 nat enable user u@x.invalid password P-NOT-REAL\n!\n"
           "pon-onu-mng gpon-onu_1/3/6:60\n  ip-host 2 ip 10.0.0.2 mask 255.255.255.0\n!\n")
    assert _parse_onu_pppoe(cfg) == {(3, 6, 59): ("u@x.invalid", "P-NOT-REAL")}
