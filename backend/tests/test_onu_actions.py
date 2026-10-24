"""Unit test aksi/konfigurasi ONU — TANPA perangkat.

Yang dijaga di sini: validasi batas (VLAN/IP/SSID/enum), `confirm` wajib untuk aksi yang
menulis ke perangkat, redaksi rahasia, dan 501 untuk kind yang belum terbukti.
Perintah di `expected` adalah yang BENAR-BENAR dijalankan di ONU uji gpon-onu_1/4/1:11
(OLT TGR id=8, 2026-10-25) — jangan diubah tanpa transkrip baru dari perangkat.
"""

import pytest

from app.core.exceptions import ValidationAppError
from app.drivers import zte_onu_actions as za
from app.services.onu_action_service import ensure_confirmed, redact_commands

SLOT, PORT, IDX = 4, 1, 11


def test_attached_vlans_terbukti_di_onu_uji():
    cmds = za.build_attached_vlans(SLOT, PORT, IDX, [15, 100])
    assert cmds[0] == "interface gpon-onu_1/4/1:11"
    assert "service-port 1 vport 1 user-vlan 15 vlan 15" in cmds
    assert "service-port 2 vport 2 user-vlan 100 vlan 100" in cmds
    assert "no service-port 1" in cmds  # idempotent: kirim ulang nilai sama tidak ditolak
    # flow/gemport TIDAK disentuh: `no flow N` menghapus definisi flow dan mematikan trafik.
    assert not [c for c in cmds if c.startswith(("flow ", "no flow ", "gemport "))]


@pytest.mark.parametrize("vlans", [[0], [4095], [-1], [], [1.5]])
def test_vlan_di_luar_batas_ditolak(vlans):
    with pytest.raises(ValueError):
        za.build_attached_vlans(SLOT, PORT, IDX, vlans)


def test_vlan_bool_bukan_int_valid():
    with pytest.raises(ValueError):
        za.validate_vlan(True)


def test_eth_port_mode_tag():
    cmds = za.build_eth_port(SLOT, PORT, IDX, eth_port=1, enabled=True, mode="lan",
                             vlan_id=15, allowed_vlans=None, dhcp="onu")
    assert cmds == [
        "pon-onu-mng gpon-onu_1/4/1:11",
        "interface eth eth_0/1 state unlock",
        "vlan port eth_0/1 mode tag vlan 15",
        "dhcp-ip ethuni eth_0/1 from-onu",
        "exit",
    ]


def test_eth_port_shutdown_dan_trunk_allowed_vlans():
    cmds = za.build_eth_port(SLOT, PORT, IDX, eth_port=2, enabled=False, mode="trunk",
                             vlan_id=None, allowed_vlans=[15, 100], dhcp="none")
    assert "interface eth eth_0/2 state lock" in cmds
    assert "vlan port eth_0/2 mode trunk" in cmds
    assert "vlan port eth_0/2 vlan 15,100" in cmds
    assert "dhcp-ip ethuni eth_0/2 no-ctrl" in cmds


def test_eth_port_mode_dan_dhcp_enum_dijaga():
    for bad in ({"mode": "bogus"}, {"dhcp": "bogus"}):
        kwargs = {"eth_port": 1, "enabled": True, "mode": "lan", "vlan_id": 15,
                  "allowed_vlans": None, "dhcp": "none", **bad}
        with pytest.raises(ValueError):
            za.build_eth_port(SLOT, PORT, IDX, **kwargs)


def test_eth_port_mode_tag_tanpa_vlan_ditolak():
    with pytest.raises(ValueError):
        za.build_eth_port(SLOT, PORT, IDX, eth_port=1, enabled=True, mode="access",
                          vlan_id=None, allowed_vlans=None, dhcp="none")


def test_wifi_port_lengkap():
    cmds = za.build_wifi_port(SLOT, PORT, IDX, wifi_port=1, enabled=True, mode="lan",
                              vlan_id=15, allowed_vlans=None, ssid="Nexfiber Test",
                              auth_mode="wpa2", password="rahasia123", dhcp="onu")
    assert "ssid ctrl wifi_0/1 name Nexfiber Test" in cmds
    assert "ssid auth wpa wifi_0/1 wpa2-psk encrypt aes key rahasia123" in cmds
    assert "vlan port wifi_0/1 mode tag vlan 15" in cmds


def test_wifi_open_tanpa_password():
    cmds = za.build_wifi_port(SLOT, PORT, IDX, wifi_port=1, enabled=True, mode="lan",
                              vlan_id=15, allowed_vlans=None, ssid="Terbuka",
                              auth_mode="open", password=None, dhcp="none")
    assert not [c for c in cmds if "key" in c]


@pytest.mark.parametrize("pwd", ["pendek", "a" * 64, "ada spasi disini"])
def test_password_wifi_tidak_valid_ditolak(pwd):
    with pytest.raises(ValueError):
        za.build_wifi_port(SLOT, PORT, IDX, wifi_port=1, enabled=True, mode="lan",
                           vlan_id=15, allowed_vlans=None, ssid="X", auth_mode="wpa2",
                           password=pwd, dhcp="none")


def test_ssid_panjang_ditolak():
    with pytest.raises(ValueError):
        za.validate_ssid("x" * 33)


def test_wifi_clear():
    assert za.build_wifi_clear(SLOT, PORT, IDX, wifi_port=1) == [
        "pon-onu-mng gpon-onu_1/4/1:11", "no ssid ctrl wifi_0/1 name",
        "no vlan port wifi_0/1 mode", "restore wifi", "exit",
    ]


def test_mgmt_ip_manual_dan_pool():
    assert za.build_mgmt_ip(SLOT, PORT, IDX, mode="pool", ip=None)[1] == "mgmt-ip auto-assign"
    cmds = za.build_mgmt_ip(SLOT, PORT, IDX, mode="manual", ip="192.0.2.9")
    assert cmds[1] == "mgmt-ip 192.0.2.9 255.255.255.0"


@pytest.mark.parametrize("ip", ["999.1.1.1", "bukan-ip", "10.1.1", ""])
def test_mgmt_ip_tidak_valid_ditolak(ip):
    with pytest.raises(ValueError):
        za.build_mgmt_ip(SLOT, PORT, IDX, mode="manual", ip=ip)


def test_voip_enable_disable():
    assert za.build_voip(SLOT, PORT, IDX, enabled=True)[1] == "voip protocol sip"
    assert za.build_voip(SLOT, PORT, IDX, enabled=False)[1] == "voip protocol none"


def test_speed_profile_dua_arah():
    cmds = za.build_speed_profile(SLOT, PORT, IDX, upload_profile="SMARTOLT-HFA_3-UP",
                                  download_profile="SMARTOLT-HFA_3-DOWN")
    assert "tcont 1 profile SMARTOLT-HFA_3-UP" in cmds
    assert "gemport 1 traffic-limit downstream SMARTOLT-HFA_3-DOWN" in cmds


def test_speed_profile_tanpa_arah_ditolak():
    with pytest.raises(ValueError):
        za.build_speed_profile(SLOT, PORT, IDX, upload_profile=None, download_profile=None)


def test_nama_profil_disuntik_ditolak():
    with pytest.raises(ValueError):
        za.build_speed_profile(SLOT, PORT, IDX, upload_profile="A ; reload", download_profile=None)


def test_replace_sn_validasi():
    cmds = za.build_replace_sn(SLOT, PORT, IDX, onu_type="ZTE-F670L", new_sn="ztegaaaa1111")
    assert cmds[1] == "onu 11 type ZTE-F670L sn ZTEGAAAA1111"
    with pytest.raises(ValueError):
        za.build_replace_sn(SLOT, PORT, IDX, onu_type="ZTE-F670L", new_sn="bad sn!")


def test_resync_config_hanya_clear():
    assert za.build_resync_config(SLOT, PORT, IDX)[1] == "clear"


def test_redaksi_password_wifi_dan_pppoe():
    raw = [
        "ssid auth wpa wifi_0/1 wpa2-psk encrypt aes key rahasia123",
        "pppoe 1 nat enable user u@isp password SangatRahasia",
        "tr069-mgmt 1 acs http://acs.example validate basic username acsuser password AcsDummy1",
        "vlan port eth_0/1 mode tag vlan 15",
    ]
    out = redact_commands(raw)
    assert "rahasia123" not in " ".join(out)
    assert "SangatRahasia" not in " ".join(out)
    assert "acsuser password <REDACTED>" in out[2]
    assert out[3] == raw[3]  # perintah tanpa rahasia tidak diubah


def test_redaksi_tidak_menyentuh_kata_default():
    assert redact_commands(["ssid auth wpa wifi_0/1 key default"])[0].endswith("key default")


def test_confirm_wajib_untuk_aksi_tulis():
    with pytest.raises(ValidationAppError):
        ensure_confirmed("eth-port", {"port": 1})
    ensure_confirmed("eth-port", {"port": 1, "confirm": True})


def test_confirm_tidak_wajib_untuk_aksi_db():
    ensure_confirmed("external-id", {"external_id": "X1"})


def test_kind_belum_terbukti_tidak_punya_pembangun():
    assert set(za.UNSUPPORTED_KINDS) == {"onu-mode", "iptv"}
    assert not set(za.UNSUPPORTED_KINDS) & set(za.SUPPORTED_KINDS)


def test_semua_kind_kontrak_terdaftar():
    kontrak = {
        "attached-vlans", "onu-mode", "eth-port", "wifi-port", "wifi-clear", "external-id",
        "onu-type", "speed-profile", "move", "replace-sn", "mgmt-ip", "voip-enable",
        "voip-disable", "iptv", "reboot", "disable", "enable", "restore-factory",
        "resync-config", "delete",
    }
    assert kontrak == set(za.SUPPORTED_KINDS) | set(za.UNSUPPORTED_KINDS)
