"""Regresi helper metadata/VLAN per-ONU (`app/services/onu_device_metadata.py`).

Semua string di sini adalah bentuk NYATA yang sudah diverifikasi read-only:
- contoh terstruktur penuh = format yang ditulis aplikasi referensi pemilik
  (`frontend/action/auth-onu.php`) dan contoh eksplisit dari user;
- contoh teks bebas + `service-port` ganda = transkrip OLT SBI (C300) 2026-10-24.
"""

from datetime import date

from app.services.onu_device_metadata import (
    classify_service_vlans,
    display_service_vlans,
    parse_device_description,
    parse_service_ports,
    service_vlan_ids,
)

FULL = ("zone_Nawangan_descr_Grandring Pucung RT 03/ 05 kec Kismantoro"
        "_odb_LGD-01B0214-Gandring_authd_20261022")

ONU_STANZA = """interface gpon-onu_1/6/2:15
  tcont 1 profile SMARTOLT-HFA_Lite-UP
  tcont 2 profile SMARTOLT-VOIPMNG-10M
  gemport 1 tcont 1
  gemport 2 tcont 2
  service-port 1 vport 1 user-vlan 15 vlan 15
  service-port 2 vport 2 user-vlan 100 vlan 100
!
"""


# --- metadata description ----------------------------------------------------------

def test_parses_all_four_fields_from_explicit_example():
    meta = parse_device_description(FULL)
    assert meta.zone == "Nawangan"
    assert meta.address == "Grandring Pucung RT 03/ 05 kec Kismantoro"
    assert meta.splitter == "LGD-01B0214-Gandring"
    assert meta.authorized_on == date(2026, 10, 22)
    assert meta.structured is True


def test_values_may_contain_spaces_slashes_and_underscores():
    meta = parse_device_description(
        "zone_Boyolali_descr_Griya_Rivera_Hills_C_15_authd_20260901"
    )
    assert (meta.zone, meta.address) == ("Boyolali", "Griya_Rivera_Hills_C_15")
    assert meta.splitter is None  # tidak ada _odb_ -> tidak ditebak
    assert meta.authorized_on == date(2026, 9, 1)


def test_empty_and_none_tokens_are_not_values():
    meta = parse_device_description("zone_None_descr_Jalan Mawar 1_odb__authd_20261019")
    assert meta.zone is None
    assert meta.splitter is None
    assert meta.address == "Jalan Mawar 1"


def test_free_text_description_is_not_turned_into_zone_or_odp():
    meta = parse_device_description("Perum Rivera Hills Blok B.22 Boyolali")
    assert (meta.zone, meta.splitter, meta.authorized_on) == (None, None, None)
    assert meta.structured is False
    assert meta.free_text == "Perum Rivera Hills Blok B.22 Boyolali"


def test_partial_token_free_text_plus_auth_date():
    meta = parse_device_description(
        "Perum Griya Rivera Hills Blok F.18 Boyolali_authd_20260425"
    )
    assert meta.authorized_on == date(2026, 4, 25)
    assert meta.zone is None and meta.splitter is None
    assert meta.free_text == "Perum Griya Rivera Hills Blok F.18 Boyolali"


def test_zone_only_description():
    meta = parse_device_description("zone_GBB")
    assert meta.zone == "GBB"
    assert meta.address is None and meta.splitter is None


def test_invalid_auth_date_is_dropped_not_guessed():
    assert parse_device_description("zone_A_authd_20261345").authorized_on is None
    assert parse_device_description("zone_A").authorized_on is None
    assert parse_device_description(None).authorized_on is None


def test_hard_wrapped_description_is_joined_before_parsing():
    meta = parse_device_description("zone_Nawangan_descr_Jalan Panjang\n  Sekali_authd_20261022")
    assert meta.zone == "Nawangan"
    assert meta.address == "Jalan Panjang Sekali"


def test_odp_prefix_and_gps_contamination_cleaned():
    meta = parse_device_description("zone_A_odb_ODP TGR-01D1111 lat -7.1 long 111.2_authd_20261016")
    assert meta.splitter == "TGR-01D1111"


# --- VLAN layanan ------------------------------------------------------------------

def test_service_ports_give_all_vlans_in_device_order():
    assert service_vlan_ids(ONU_STANZA) == [15, 100]
    ports = parse_service_ports(ONU_STANZA)
    assert [(p.service_port, p.vport, p.user_vlan, p.vlan) for p in ports] == [
        (1, 1, 15, 15), (2, 2, 100, 100)]


def test_duplicate_vlans_deduped_stable():
    cfg = ("  service-port 1 vport 1 user-vlan 15 vlan 15\n"
           "  service-port 2 vport 2 user-vlan 100 vlan 100\n"
           "  service-port 3 vport 3 user-vlan 15 vlan 15\n"
           "  service-port 4 vport 4 user-vlan 3045 vlan 3045\n")
    assert service_vlan_ids(cfg) == [15, 100, 3045]


def test_inner_outer_vlan_difference_is_kept_display_uses_outer():
    cfg = "  service-port 1 vport 1 user-vlan 15 vlan 1500\n"
    assert service_vlan_ids(cfg) == [1500]
    assert parse_service_ports(cfg)[0].user_vlan == 15


def test_management_vlan_hidden_by_master_flag_not_hardcoded_number():
    master = {15: ("VLAN15", "internet"), 100: ("VLAN100", "management")}
    rows = classify_service_vlans([15, 100], master)
    assert [r.vlan_id for r in display_service_vlans(rows)] == [15]
    # angka 100 tidak spesial: kalau master bilang internet, 100 tetap tampil
    master2 = {15: ("VLAN15", "internet"), 100: ("VLAN100", "internet")}
    rows2 = classify_service_vlans([15, 100], master2)
    assert [r.vlan_id for r in display_service_vlans(rows2)] == [15, 100]


def test_all_management_yields_empty_display_without_fallback():
    master = {15: ("MGMT-A", "management"), 100: ("MGMT-B", "management")}
    rows = classify_service_vlans([15, 100], master)
    assert display_service_vlans(rows) == []
    assert all(r.is_management for r in rows)


def test_vlan_unknown_to_master_is_still_reported_as_real():
    rows = classify_service_vlans([15, 777], {15: ("VLAN15", "internet")})
    unknown = rows[1]
    assert (unknown.vlan_id, unknown.in_master, unknown.name) == (777, False, None)
    assert unknown.is_management is False
    assert [r.vlan_id for r in display_service_vlans(rows)] == [15, 777]


def test_no_service_port_means_empty_list_not_invented_vlan():
    assert service_vlan_ids("interface gpon-onu_1/6/1:1\n  name Siapa\n") == []
    assert service_vlan_ids("") == []
