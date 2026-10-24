"""Parser/registry unit tests for the ZTE driver. list_unconfigured/fetch_inventory kini
diverifikasi terhadap transkrip nyata OLT SBI (lihat test_olt_inventory_sync.py);
delete/set_state/reboot CLI syntax masih UNVERIFIED.
"""

from pathlib import Path

import pytest

from app.drivers.errors import ZTE_ERROR_PATTERNS, is_error_output
from app.drivers.registry import get_driver_class
from app.drivers.zte_c320 import (
    OID_IF_DESCR,
    OID_OLT_RX_POWER,
    OID_ONU_PHASE_STATE,
    OID_ONU_RX_POWER,
    ZteC320Driver,
    _decode_olt_rx_dbm,
    _decode_onu_rx_dbm,
    _parse_onu_ids,
    _parse_onu_iface,
    _parse_port_status,
    _parse_slot_port,
    _parse_unconfigured,
    build_port_config_commands,
    decode_pon_ifindex,
    phase_state_to_status,
)

IFX_1_3_6 = 268435456 + 3 * 65536 + 6 * 256  # gpon-olt_1/3/6 under the UNVERIFIED layout
# Skema index KEDUA (tabel optical 1082.500): nilai nyata OLT SBI untuk PON 1/6/1 & 1/6/2.
OPT_IFX_1_6_1 = 285279745
OPT_IFX_1_6_2 = 285279746
IFX_1_4_3 = 268435456 + 4 * 65536 + 3 * 256

def _driver() -> ZteC320Driver:
    return ZteC320Driver(
        host="10.0.0.1", cli_username="a", cli_password="b", cli_protocol="ssh",
        cli_port=22, snmp_community="public", snmp_port=161,
    )

def test_open_cli_uses_zte_zxros_device_type():
    # BUG NYATA (OLT SBI, 2026-10-24): device_type default netmiko "generic_termserver"
    # tak tahu login-prompt ZXA10 -- session macet di "Username:"/"Password:" selamanya.
    ssh = _driver()._open_cli()
    assert ssh._params["device_type"] == "zte_zxros"
    telnet = ZteC320Driver(
        host="10.0.0.1", cli_username="a", cli_password="b", cli_protocol="telnet",
        cli_port=23, snmp_community="public", snmp_port=161,
    )._open_cli()
    assert telnet._params["device_type"] == "zte_zxros_telnet"


def test_decode_pon_ifindex():
    assert decode_pon_ifindex(268501248) == (1, 1)
    assert decode_pon_ifindex(IFX_1_3_6) == (3, 6)
    assert decode_pon_ifindex(IFX_1_4_3) == (4, 3)


def test_parse_unconfigured_matches_real_gpon_onu_prefix():
    # Format asli (verifikasi live, driver SmartOLT) — bukan "gpon-olt_" seperti dugaan lama.
    output = "gpon-onu_1/2/1:1      ZTEGCC929729      unknown\ngpon-onu_1/2/3:5      ZTEGAABBCCDD\n"
    onus = _parse_unconfigured(output)
    assert [(o.slot, o.port, o.serial_number, o.onu_type) for o in onus] == [
        (2, 1, "ZTEGCC929729", "unknown"),
        (2, 3, "ZTEGAABBCCDD", None),
    ]

def test_phase_state_to_status():
    # Nilai nyata (NEXFIBER-SNMP-OID + silang `show gpon onu state` OLT SBI):
    # 3 working, 4 dyingGasp, 1 los, 6 offline. Lihat test_olt_inventory_sync.py.
    assert phase_state_to_status(3) == "online"
    assert phase_state_to_status(1) == "los"
    assert phase_state_to_status(4) == "dying_gasp"
    assert phase_state_to_status(6) == "offline"
    for transitional in (0, 2, 5, 99, None, "x"):
        assert phase_state_to_status(transitional) == "unknown"

async def test_fetch_onu_status_decodes_every_pon(monkeypatch):
    driver = _driver()

    async def fake_bulkwalk(base_oid):
        assert base_oid == OID_ONU_PHASE_STATE
        return [
            (f"{OID_ONU_PHASE_STATE}.{IFX_1_3_6}.59", 3),
            (f"{OID_ONU_PHASE_STATE}.{IFX_1_4_3}.46", 1),
            (f"{OID_ONU_PHASE_STATE}.{IFX_1_3_6}", 3),  # malformed suffix, skipped
        ]

    monkeypatch.setattr(driver._snmp, "bulkwalk", fake_bulkwalk)
    samples = await driver.fetch_onu_status()
    assert [(s.slot, s.port, s.onu_id, s.status) for s in samples] == [
        (3, 6, 59, "online"),
        (4, 3, 46, "los"),
    ]

FIXTURES = Path(__file__).parent / "fixtures" / "cli"

def test_registry_resolves_zte_c320():
    assert get_driver_class("zte", "C320") is ZteC320Driver

def test_registry_raises_for_unknown_vendor():
    with pytest.raises(ValueError):
        get_driver_class("cdata", "FD1602S-B1")

def test_parse_slot_port_matches_real_transcript():
    # From tests/fixtures/cli/zte_show_running_config_onu.txt: "interface gpon-olt_1/3/6"
    assert _parse_slot_port("gpon-olt_1/3/6") == (3, 6)

def test_parse_onu_iface_matches_real_transcript():
    # "interface gpon-onu_1/3/6:59"
    assert _parse_onu_iface("gpon-onu_1/3/6:59") == (3, 6, 59)

def test_is_error_output_detects_known_zte_errors():
    assert is_error_output("% Invalid input detected", ZTE_ERROR_PATTERNS)
    assert is_error_output("Unknown command", ZTE_ERROR_PATTERNS)
    assert not is_error_output("tcont 1 profile SMARTOLT-HFA_Lite-UP", ZTE_ERROR_PATTERNS)

def test_real_transcript_contains_expected_authorize_fields():
    text = (FIXTURES / "zte_show_running_config_onu.txt").read_text()
    assert "onu 59 type ALL-ONT sn ZTEGD3A146F9" in text
    assert "tcont 1 profile SMARTOLT-HFA_Lite-UP" in text

@pytest.mark.parametrize(
    ("fixture", "onu_type"),
    [
        ("zte_show_running_config_onu.txt", "ALL-ONT"),
        ("zte_show_running_config_onu_2.txt", "ONU-type-eth-4-pots-2-catv-0"),
        ("zte_show_running_config_onu_3.txt", "HG8245H5"),
    ],
)
def test_real_transcripts_have_varying_onu_type(fixture, onu_type):
    # Regression guard: authorize() used to hardcode "ALL-ONT" for every ONU, but real
    # transcripts show the type varies per ONU model (ZTE/Fiberhome/Huawei CPEs all register
    # against the same ZTE OLT with their own type string).
    text = (FIXTURES / fixture).read_text()
    assert f"type {onu_type} sn" in text

def test_decode_onu_rx_dbm_handles_signed_16bit_and_sentinel():
    assert _decode_onu_rx_dbm(2147483647) is None  # SNMP "not available"
    assert _decode_onu_rx_dbm(65536 - 1292) == pytest.approx(-32.58)  # raw 64244 -> -1292 raw units
    assert _decode_onu_rx_dbm(15000) == pytest.approx(0.0)  # (15000*0.002)-30 = 0
    assert _decode_onu_rx_dbm("not-a-number") is None
    # Sentinel ONU mati: semua 32 ONU phase los/dyingGasp di WNG raw 65535. Dulu lolos
    # sebagai -30.02 dBm (konversi signed -> -1) dan tampil seperti Rx sah.
    assert _decode_onu_rx_dbm(65535) is None
    assert _decode_onu_rx_dbm(0) is None  # belum diukur, bukan -30 dBm
    # Ambang bawah -40, bukan -30: ONU working nyata di WNG ada yang -30.46 dBm.
    assert _decode_onu_rx_dbm(65536 - 230) == pytest.approx(-30.46)

def test_decode_olt_rx_dbm_reads_millidbm():
    # Nilai nyata OLT SBI: raw -23768 = -23.768 dBm (silang `show pon power olt-rx`).
    assert _decode_olt_rx_dbm(2147483647) is None
    assert _decode_olt_rx_dbm(-23768) == pytest.approx(-23.77)
    assert _decode_olt_rx_dbm(-23115) == pytest.approx(-23.11)  # pembulatan 2 desimal
    assert _decode_olt_rx_dbm(120080) is None  # di luar -40..10 dBm
    assert _decode_olt_rx_dbm(-80000) is None  # sentinel "tidak ada sinyal"
    assert _decode_olt_rx_dbm(0) is None  # belum diukur

@pytest.mark.asyncio
async def test_fetch_optical_decodes_and_joins_olt_rx(monkeypatch):
    driver = ZteC320Driver(
        host="10.0.0.1", cli_username="a", cli_password="b", cli_protocol="ssh",
        cli_port=22, snmp_community="public", snmp_port=161,
    )

    async def fake_bulkwalk(base_oid):
        if base_oid == OID_ONU_RX_POWER:
            return [(f"{OID_ONU_RX_POWER}.{OPT_IFX_1_6_1}.1.1", 5470),
                    (f"{OID_ONU_RX_POWER}.{OPT_IFX_1_6_2}.1.1", 5470)]  # PON lain, difilter
        if base_oid == OID_OLT_RX_POWER:
            return [(f"{OID_OLT_RX_POWER}.{OPT_IFX_1_6_1}.1", -23768)]
        raise AssertionError(f"unexpected OID {base_oid}")

    monkeypatch.setattr(driver._snmp, "bulkwalk", fake_bulkwalk)
    samples = await driver.fetch_optical(slot=6, port=1)
    assert len(samples) == 1
    sample = samples[0]
    assert (sample.slot, sample.port, sample.onu_id) == (6, 1, 1)
    assert sample.rx_power_dbm == pytest.approx(-19.06)
    assert sample.olt_rx_power_dbm == pytest.approx(-23.77)


def test_parse_onu_ids_from_real_transcript():
    text = (FIXTURES / "zte_show_running_config_onu.txt").read_text()
    assert _parse_onu_ids(text) == [59]

async def test_list_pon_ports_filters_ifdescr(monkeypatch):
    driver = _driver()

    async def fake_bulkwalk(base_oid):
        assert base_oid == OID_IF_DESCR
        return [(f"{OID_IF_DESCR}.{IFX_1_3_6}", "gpon-olt_1/3/6"),
                (f"{OID_IF_DESCR}.1", "gei_1/9/1")]

    monkeypatch.setattr(driver._snmp, "bulkwalk", fake_bulkwalk)
    ports = await driver.list_pon_ports()
    assert [(p.slot, p.port, p.ifindex) for p in ports] == [(3, 6, IFX_1_3_6)]


# --- Tab Interfaces: port uplink (PRD 3.4.7) ----------------------------------

def test_parse_port_status_from_real_transcript():
    """Transkrip nyata OLT SBI: 2 port sah + 2 baris error, header harus terlewat."""
    text = (FIXTURES / "zte_show_interface_port_status.txt").read_text()
    rows = _parse_port_status(text)
    assert [r.name for r in rows] == ["xgei_1/19/1", "xgei_1/19/2"]
    first = rows[0]
    assert (first.media, first.pvid, first.auto_nego) == ("optical", 1, "disable")
    assert (first.speed, first.duplex, first.flow_ctrl) == ("10000", "full", "disable")
    assert (first.admin_status, first.link) == ("activate", "up")
    assert rows[1].link == "down"


def test_build_port_config_commands_auto_nego_ignores_speed_duplex():
    assert build_port_config_commands("xgei_1/19/2", "enable", "1000", "half") == [
        "interface xgei_1/19/2", "negotiation auto", "exit",
    ]


def test_build_port_config_commands_manual():
    assert build_port_config_commands("xgei_1/19/2", "disable", "10000", "full") == [
        "interface xgei_1/19/2", "no negotiation auto", "speed 10000", "duplex full", "exit",
    ]


@pytest.mark.parametrize(
    "port,auto_nego,speed,duplex",
    [
        ("gpon-olt_1/3/6", "disable", "1000", "full"),  # bukan port uplink
        ("xgei_1/19/2", "maybe", "1000", "full"),
        ("xgei_1/19/2", "disable", "2500", "full"),  # speed di luar daftar
        ("gei_1/19/2", "disable", "10000", "full"),  # port GE tak bisa 10G
        ("xgei_1/19/2", "disable", "1000", "auto"),
        ("xgei_1/19/2", "disable", None, None),
    ],
)
def test_build_port_config_commands_rejects_bad_input(port, auto_nego, speed, duplex):
    with pytest.raises(ValueError):
        build_port_config_commands(port, auto_nego, speed, duplex)


async def test_fetch_interfaces_probes_cards_when_ifdescr_empty(monkeypatch):
    """BUG NYATA (OLT SBI): seluruh ifDescr kosong, jadi nama port ditebak dari
    `show card` dan port yang ditolak perangkat hilang sendiri."""
    driver = _driver()
    status = (FIXTURES / "zte_show_interface_port_status.txt").read_text()
    cards = (
        "Rack Shelf Slot CfgType RealType Port  HardVer SoftVer         Status\n"
        "1    1     6    GTGO    GTGOG    8     V1.0.0  V2.1.0          INSERVICE\n"
        "1    1     19   HUVQ    HUVQ     2     V1.0.0  V2.1.0          INSERVICE\n"
    )
    seen: list[str] = []

    async def fake_bulkwalk(_base_oid):
        return []  # ifDescr kosong, seperti perangkat nyata

    class FakeCli:
        async def send_command(self, command: str) -> str:
            seen.append(command)
            if command == "show card":
                return cards
            if command.endswith("xgei_1/19/1"):
                return status.split("show interface port-status xgei_1/19/2")[0]
            if command.endswith("xgei_1/19/2"):
                return status
            return "%Error 20202: Invalid input detected at '^' marker."

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

    monkeypatch.setattr(driver._snmp, "bulkwalk", fake_bulkwalk)
    monkeypatch.setattr(driver, "_open_cli", lambda: FakeCli())
    rows = await driver.fetch_interfaces()
    assert sorted({r.name for r in rows}) == ["xgei_1/19/1", "xgei_1/19/2"]
    # Kartu PON slot 6 ditolak di port 1 untuk kedua awalan -> tidak diprobe 8x.
    assert seen.count("show interface port-status xgei_1/6/1") == 1
    assert "show interface port-status xgei_1/6/2" not in seen
