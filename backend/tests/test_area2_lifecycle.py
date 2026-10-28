"""Unit test murni (tanpa perangkat, tanpa Postgres) untuk perbaikan Area 2:
normalisasi serial/customer, validasi set_state, parser ip-host, pemetaan VLAN host,
nama port uplink hyphen, dan fallback VLAN WAN.

Bukan tes integrasi: jalur worker/sync yang butuh DB nyata tetap diuji tes lain
yang skip bila Postgres tidak terjangkau.
"""

import pytest

from app.core.exceptions import ValidationAppError
from app.drivers.onu_report import (
    _host_vlan_map,
    parse_management_ip,
    wan_vlan_not_management,
)
from app.drivers.zte_c320 import build_port_config_commands, normalize_uplink_name
from app.services.onu_service import (
    _validate_job_payload,
    normalize_customer_id,
    normalize_serial,
)


def test_normalize_serial_strips_and_uppercases():
    assert normalize_serial("  zte123abc ") == "ZTE123ABC"
    assert normalize_serial("") == ""
    assert normalize_serial(None) == ""  # type: ignore[arg-type]


def test_normalize_customer_id_strips_but_keeps_case():
    # Strip saja, bukan lower: ID pelanggan yang ditampilkan tidak boleh berubah
    # bentuknya; unique DB (agen 5) yang menutup balapan persis.
    assert normalize_customer_id("  Cust-01 ") == "Cust-01"
    assert normalize_customer_id("") == ""


async def test_validate_set_state_requires_bool_enabled():
    await _validate_job_payload(None, None, "set_state", {"enabled": True})  # type: ignore[arg-type]
    await _validate_job_payload(None, None, "set_state", {"enabled": False})  # type: ignore[arg-type]
    for bad in (None, {}, {"enabled": "true"}, {"enabled": 1}, {"enabled": None}):
        with pytest.raises(ValidationAppError):
            await _validate_job_payload(None, None, "set_state", bad)  # type: ignore[arg-type]


def test_parse_management_ip_skips_unpaired_host_only():
    # Satu ip-host tanpa gemport bernomor sama dilewati, bukan membatalkan daftar.
    body = ("  flow 1 pri 0 vlan 15\n  gemport 1 flow 1\n"
            "  ip-host 1 dhcp-enable enable\n  ip-host 9 dhcp-enable enable\n")
    assert parse_management_ip(body) == [(15, "dhcp", None)]


def test_host_vlan_map_vlan_filter_wins_over_flow_fallback():
    # vlan-filter memberi host 1 -> VLAN 100; fallback flow (gemport 1 -> flow 1 ->
    # vlan 15) TIDAK boleh menimpanya. Bug lama: kunci str vs int membuat guard
    # `n not in out` selalu True sehingga fallback selalu menang.
    running = ("  vlan-filter iphost 1 pri 0 vlan 100\n"
               "  flow 1 pri 0 vlan 15\n  gemport 1 flow 1\n  ip-host 1 dhcp-enable enable\n")
    assert _host_vlan_map(running) == {1: 100}


def test_normalize_uplink_name_hyphen_to_underscore():
    assert normalize_uplink_name("gei-1/5/1") == "gei_1/5/1"
    assert normalize_uplink_name("XGEI-1/5/2") == "xgei_1/5/2"
    assert normalize_uplink_name("gei_1/5/1") == "gei_1/5/1"


def test_build_port_config_accepts_hyphen_form():
    cmds = build_port_config_commands("gei-1/5/1", "disable", "1000", "full")
    assert cmds[0] == "interface gei_1/5/1"
    with pytest.raises(ValueError):
        build_port_config_commands("eth-1/5/1", "disable", "1000", "full")


def test_wan_vlan_not_management_rules():
    # flow 1 bukan management -> dipakai apa adanya; flow 1 management -> kandidat
    # non-management pertama (hanya flow ber-ip-host, sesuai tes refresh yang ada);
    # tanpa kandidat -> None, bukan VLAN management.
    assert wan_vlan_not_management(15, [(100, "dhcp", None)], {100}) == 15
    assert wan_vlan_not_management(100, [(200, "dhcp", None)], {100}) == 200
    assert wan_vlan_not_management(100, [(100, "dhcp", None)], {100}) is None
    assert wan_vlan_not_management(None, [(200, "dhcp", None)], {100}) is None
