"""Parser/registry unit tests for the ZTE driver. See zte_c320.py module docstring:
list_unconfigured/delete/set_state/reboot/fetch_inventory command syntax is UNVERIFIED
(no real device transcript available) — these tests cover only what's confirmed against
real transcripts (backup_config passthrough) plus pure-function parsing helpers.
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
    _parse_slot_port,
    _parse_unconfigured,
    decode_pon_ifindex,
    phase_state_to_status,
)

IFX_1_3_6 = 268435456 + 3 * 65536 + 6 * 256  # gpon-olt_1/3/6 under the UNVERIFIED layout
IFX_1_4_3 = 268435456 + 4 * 65536 + 3 * 256

def _driver() -> ZteC320Driver:
    return ZteC320Driver(
        host="10.0.0.1", cli_username="a", cli_password="b", cli_protocol="ssh",
        cli_port=22, snmp_community="public", snmp_port=161,
    )

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
    assert phase_state_to_status(4) == "online"
    assert phase_state_to_status(2) == "los"
    assert phase_state_to_status(5) == "dying_gasp"
    assert phase_state_to_status(7) == "offline"
    for transitional in (1, 3, 6, 99, None, "x"):
        assert phase_state_to_status(transitional) == "unknown"

async def test_fetch_onu_status_decodes_every_pon(monkeypatch):
    driver = _driver()

    async def fake_bulkwalk(base_oid):
        assert base_oid == OID_ONU_PHASE_STATE
        return [
            (f"{OID_ONU_PHASE_STATE}.{IFX_1_3_6}.59", 4),
            (f"{OID_ONU_PHASE_STATE}.{IFX_1_4_3}.46", 2),
            (f"{OID_ONU_PHASE_STATE}.{IFX_1_3_6}", 4),  # malformed suffix, skipped
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

def test_decode_olt_rx_dbm_rejects_out_of_range():
    assert _decode_olt_rx_dbm(2147483647) is None
    # source's own worked example (28492) fails its own -60..10 dBm sanity range check
    assert _decode_olt_rx_dbm(28492) is None
    assert _decode_olt_rx_dbm(120080) == pytest.approx(-20.08)  # (10000 - 12008) / 100

@pytest.mark.asyncio
async def test_fetch_optical_decodes_and_joins_olt_rx(monkeypatch):
    driver = ZteC320Driver(
        host="10.0.0.1", cli_username="a", cli_password="b", cli_protocol="ssh",
        cli_port=22, snmp_community="public", snmp_port=161,
    )

    async def fake_bulkwalk(base_oid):
        if base_oid == OID_ONU_RX_POWER:
            return [(f"{OID_ONU_RX_POWER}.{IFX_1_3_6}.1.1", 15000),
                    (f"{OID_ONU_RX_POWER}.{IFX_1_4_3}.1.1", 15000)]  # other PON, filtered
        if base_oid == OID_OLT_RX_POWER:
            return [(f"{OID_OLT_RX_POWER}.{IFX_1_3_6}.1", 120080)]
        raise AssertionError(f"unexpected OID {base_oid}")

    monkeypatch.setattr(driver._snmp, "bulkwalk", fake_bulkwalk)
    samples = await driver.fetch_optical(slot=3, port=6)
    assert len(samples) == 1
    sample = samples[0]
    assert (sample.slot, sample.port, sample.onu_id) == (3, 6, 1)
    assert sample.rx_power_dbm == pytest.approx(0.0)
    assert sample.olt_rx_power_dbm == pytest.approx(-20.08)


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
