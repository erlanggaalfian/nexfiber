"""Pembangun perintah CLI ZTE C320 untuk aksi/konfigurasi ONU (modal SmartOLT).

Semua fungsi di sini PURE (list[str] perintah, tanpa I/O) supaya bisa diuji tanpa OLT.
Driver hanya mengirimkannya lewat `send_config_set`.

Sumber sintaks: probe `?` (context-sensitive help) langsung di OLT TGR (id=8) pada ONU uji
gpon-onu_1/4/1:11, 2026-10-25. Yang TIDAK terbukti di perangkat TIDAK ditulis di sini —
`SUPPORTED_KINDS` adalah daftar putihnya, sisanya dijawab 501 oleh service.

Transkrip help yang dipakai (ringkas, mode `pon-onu-mng`):
  vlan port <uni> mode {tag|hybrid|trunk|transparent} [vlan <id>|def-vlan <id>]
  vlan port <uni> vlan {<1-4094>|all}       (daftar: "X,X..." atau "X-X")
  vlan-filter ethuni <eth> pri <0-7> vlan <id>
  vlan-filter-mode ethuni <eth> tag-filter {discard|forward|vlan-filter|...}
  dhcp-ip ethuni <eth> {no-ctrl|from-internet|from-onu|forbidden}
  interface eth <eth> state {lock|unlock}
  interface wifi <wifi> state {lock|unlock}
  ssid ctrl <wifi> name <WORD 1-32>
  ssid auth wpa <wifi> {wpa-psk|wpa2-psk|wpa-wpa2-psk} encrypt {aes|tkip|...} key <WORD 8-63>
  no ssid ctrl <wifi>
  voip protocol {sip|h248|mgcp|none|non-omci}
  mgmt-ip {<A.B.C.D> <mask>|auto-assign [host]|release}
mode `interface gpon-onu_...`:
  name <WORD>, description <WORD>, type <WORD>, enable, disable, clear,
  service-port N vport N user-vlan V vlan V, tcont/gemport, iptv ...
mode `interface gpon-olt_...`: onu <id> type <nama> [sn ...]
"""

from __future__ import annotations

import ipaddress
import re

VLAN_MIN, VLAN_MAX = 1, 4094

#: Rack OLT di semua nama interface `gpon-onu_`/`gpon-olt_`. SATU-SATUNYA sumber
#: rack yang tersedia: tidak ada kolom rack di `olts`/`pon_ports` (hanya slot, port,
#: dan ifindex), dan skema ifindex PON (1012.3.28) hanya mengkode slot/port — jadi
#: rack tidak bisa diturunkan dari DB mana pun. `show card` memang punya kolom Rack,
#: tapi kartu tidak disimpan per PON. Semua transkrip di repo memakai rack 1 (C320
#: satu rak yang teramati); bila OLT multi-rak dipakai, rack harus jadi kolom DB +
#: migrasi, bukan sekadar mengganti angka di sini.
RACK = 1

# Mode port eth: label SmartOLT -> mode CLI ZTE. "lan"/"access" dua-duanya tagged
# single-VLAN di ZTE (tidak ada kata "lan"/"access" di CLI-nya).
ETH_MODE_CLI = {
    "lan": "tag",
    "access": "tag",
    "hybrid": "hybrid",
    "trunk": "trunk",
    "transparent": "transparent",
}
WIFI_MODES = ("lan", "access", "hybrid", "trunk")
DHCP_CLI = {
    "none": "no-ctrl",
    "isp": "from-internet",
    "onu": "from-onu",
    "forbidden": "forbidden",
}
# Auth WiFi SmartOLT -> kata kunci `ssid auth wpa`. "open" = hapus auth (tanpa key).
WIFI_AUTH_CLI = {"wpa2": "wpa2-psk", "auto": "wpa-wpa2-psk"}

SSID_MAX = 32
WPA_KEY_MIN, WPA_KEY_MAX = 8, 63

#: kind -> (menulis ke perangkat?, catatan). Satu-satunya daftar putih aksi.
SUPPORTED_KINDS: dict[str, tuple[bool, str | None]] = {
    "attached-vlans": (True, None),
    "eth-port": (True, None),
    "wifi-port": (True, "Butuh ONU dengan UNI WiFi; OLT menolak bila ONU tanpa WiFi."),
    "wifi-clear": (True, None),
    "external-id": (False, "Hanya kolom DB Nexfiber."),
    "onu-type": (True, None),
    "speed-profile": (True, None),
    "mgmt-ip": (True, "auto-assign butuh IP pool di OLT."),
    "voip-enable": (True, None),
    "voip-disable": (True, None),
    "reboot": (True, None),
    "disable": (True, None),
    "enable": (True, None),
    "restore-factory": (True, None),
    "resync-config": (True, None),
    "delete": (True, None),
    "replace-sn": (True, None),
    "move": (True, None),
}

#: kind -> alasan 501. Sintaks belum terbukti di perangkat; jangan dikarang.
UNSUPPORTED_KINDS: dict[str, str] = {
    "onu-mode": (
        "Routing/bridging + WAN (DHCP/static/PPPoE) belum terbukti: `wan`/`wan-ip`/`pppoe` "
        "hanya ada di ONU ber-VEIP mode TR069 dan ditolak di ONU uji. Butuh transkrip asli."
    ),
    "iptv": (
        "`iptv` di interface ONU butuh profil IPTV (channel/package/right-mode) yang belum "
        "ada di Nexfiber; tanpa profil, perintah ditolak OLT."
    ),
}


def onu_iface(slot: int, port: int, onu_id: int) -> str:
    return f"gpon-onu_{RACK}/{slot}/{port}:{onu_id}"


def olt_iface(slot: int, port: int) -> str:
    return f"gpon-olt_{RACK}/{slot}/{port}"


def validate_vlan(vlan: int | None) -> int:
    if not isinstance(vlan, int) or isinstance(vlan, bool) or not VLAN_MIN <= vlan <= VLAN_MAX:
        raise ValueError(f"VLAN harus {VLAN_MIN}..{VLAN_MAX}, dapat {vlan!r}")
    return vlan


def validate_vlans(vlans: list[int]) -> list[int]:
    if not vlans:
        raise ValueError("Daftar VLAN tidak boleh kosong")
    out = sorted({validate_vlan(v) for v in vlans})
    if len(out) > 32:
        raise ValueError("Maksimal 32 VLAN per ONU")
    return out


def validate_ip(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except Exception as exc:  # noqa: BLE001 - pesan pendek untuk API
        raise ValueError(f"IP tidak valid: {value!r}") from exc


def validate_netmask(value: str) -> str:
    ip = validate_ip(value)
    if ipaddress.IPv4Network(f"0.0.0.0/{ip}", strict=False).prefixlen is None:  # pragma: no cover
        raise ValueError("Netmask tidak valid")
    return ip


_UNI_RE = re.compile(r"^(eth|wifi|veip)_\d+/\d+$")


def eth_uni(port: int) -> str:
    if not 1 <= port <= 24:
        raise ValueError("Port eth 1..24")
    return f"eth_0/{port}"


def wifi_uni(port: int) -> str:
    if not 1 <= port <= 8:
        raise ValueError("Port WiFi 1..8")
    return f"wifi_0/{port}"


def validate_uni(name: str) -> str:
    if not _UNI_RE.match(name):
        raise ValueError(f"Nama UNI tidak valid: {name!r}")
    return name


def validate_ssid(ssid: str) -> str:
    ssid = ssid.strip()
    if not 1 <= len(ssid) <= SSID_MAX:
        raise ValueError(f"SSID 1..{SSID_MAX} karakter")
    if any(c.isspace() and c != " " for c in ssid) or '"' in ssid or "?" in ssid:
        raise ValueError("SSID memuat karakter yang tidak diterima CLI OLT")
    return ssid


def validate_wpa_key(key: str) -> str:
    if not WPA_KEY_MIN <= len(key) <= WPA_KEY_MAX:
        raise ValueError(f"Password WiFi {WPA_KEY_MIN}..{WPA_KEY_MAX} karakter")
    if any(c.isspace() for c in key) or "?" in key:
        raise ValueError("Password WiFi tidak boleh memuat spasi atau '?'")
    return key


def validate_profile_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 64 or not re.match(r"^[\w.:/-]+$", name):
        raise ValueError(f"Nama profil tidak valid: {name!r}")
    return name


def _vlan_list(vlans: list[int]) -> str:
    return ",".join(str(v) for v in vlans)


def build_attached_vlans(slot: int, port: int, onu_id: int, vlans: list[int],
                         previous_count: int | None = None) -> list[str]:
    """Update attached VLANs lewat `service-port` di interface ONU.

    `no service-port N` dulu supaya idempotent (mengirim ulang nilai yang sama tidak
    ditolak OLT) — terbukti di ONU uji 2026-10-25.

    Mengurangi daftar juga menghapus service-port sisa: indeks di atas jumlah VLAN baru
    (sampai `previous_count`, yaitu jumlah service-port yang diketahui dari DB) ikut
    dikirim `no service-port N`. Tanpa ini, mengurangi 3 VLAN jadi 1 hanya menulis ulang
    port 1 dan port 2/3 tetap aktif di perangkat. Batasan jujur: indeks perangkat yang
    tidak tercatat di DB sama sekali tidak bisa dihapus dari sini — tidak ada perintah
    baca service-port yang terbukti di repo untuk menentukannya.

    SENGAJA TIDAK menyentuh `flow`/`gemport`/`vlan-filter` di `pon-onu-mng`: di C320
    `no flow N` MENGHAPUS seluruh definisi flow dan sesudahnya `flow N pri ... vlan ...`
    dijawab "%Code 63953-GPONRM : Flow does not exist." sampai flow dibuat ulang satu per
    satu — sekali salah urutan, trafik ONU mati. VLAN yang dipakai UI SmartOLT memang
    dibaca dari `service-port`, jadi bagian itu cukup dan aman.
    """
    vlans = validate_vlans(vlans)
    total = max(len(vlans), previous_count or 0)
    cmds = [f"interface {onu_iface(slot, port, onu_id)}"]
    for i in range(1, total + 1):
        cmds.append(f"no service-port {i}")
        if i <= len(vlans):
            vlan = vlans[i - 1]
            cmds.append(f"service-port {i} vport {i} user-vlan {vlan} vlan {vlan}")
    cmds.append("exit")
    return cmds


def build_eth_port(slot: int, port: int, onu_id: int, *, eth_port: int, enabled: bool,
                   mode: str, vlan_id: int | None, allowed_vlans: list[int] | None,
                   dhcp: str) -> list[str]:
    """Configure ethernet port eth_0/N (modal SmartOLT "Configure ethernet port")."""
    if mode not in ETH_MODE_CLI:
        raise ValueError(f"Mode eth harus salah satu {sorted(ETH_MODE_CLI)}")
    if dhcp not in DHCP_CLI:
        raise ValueError(f"DHCP harus salah satu {sorted(DHCP_CLI)}")
    uni = eth_uni(eth_port)
    cli_mode = ETH_MODE_CLI[mode]
    iface = onu_iface(slot, port, onu_id)
    cmds = [f"pon-onu-mng {iface}", f"interface eth {uni} state {'unlock' if enabled else 'lock'}"]

    if cli_mode == "transparent":
        cmds.append(f"vlan port {uni} mode transparent")
    elif cli_mode == "tag":
        cmds.append(f"vlan port {uni} mode tag vlan {validate_vlan(vlan_id)}")
    elif cli_mode == "hybrid":
        cmds.append(f"vlan port {uni} mode hybrid def-vlan {validate_vlan(vlan_id)}")
        if allowed_vlans:
            cmds.append(f"vlan port {uni} vlan {_vlan_list(validate_vlans(allowed_vlans))}")
    else:  # trunk
        cmds.append(f"vlan port {uni} mode trunk")
        if allowed_vlans:
            cmds.append(f"vlan port {uni} vlan {_vlan_list(validate_vlans(allowed_vlans))}")
    cmds.append(f"dhcp-ip ethuni {uni} {DHCP_CLI[dhcp]}")
    cmds.append("exit")
    return cmds


def build_wifi_port(slot: int, port: int, onu_id: int, *, wifi_port: int, enabled: bool,
                    mode: str, vlan_id: int | None, allowed_vlans: list[int] | None,
                    ssid: str | None, auth_mode: str, password: str | None,
                    dhcp: str) -> list[str]:
    """Configure WiFi port wifi_0/N. `password` tidak pernah di-log pemanggil.

    `dhcp` hanya divalidasi, tidak dikirim ke perangkat: tidak ada sintaks DHCP WiFi
    yang terbukti di repo, jadi UI tidak lagi menawarkan field ini daripada dibuang
    diam-diam. Jangan mengarang perintah `dhcp-ip wifiuni ...` tanpa transkrip.
    """
    if mode not in WIFI_MODES:
        raise ValueError(f"Mode WiFi harus salah satu {sorted(WIFI_MODES)}")
    if auth_mode not in (*WIFI_AUTH_CLI, "open"):
        raise ValueError("auth_mode harus wpa2, auto, atau open")
    if dhcp not in DHCP_CLI:
        raise ValueError(f"DHCP harus salah satu {sorted(DHCP_CLI)}")
    if auth_mode != "open":
        if not password:
            raise ValueError("Password wajib untuk auth wpa2/auto")
        validate_wpa_key(password)
    uni = wifi_uni(wifi_port)
    iface = onu_iface(slot, port, onu_id)
    cmds = [f"pon-onu-mng {iface}",
            f"interface wifi {uni} state {'unlock' if enabled else 'lock'}"]
    if ssid:
        cmds.append(f"ssid ctrl {uni} name {validate_ssid(ssid)}")
    if auth_mode != "open":
        cmds.append(
            f"ssid auth wpa {uni} {WIFI_AUTH_CLI[auth_mode]} encrypt aes key {password}"
        )
    cli_mode = ETH_MODE_CLI[mode]
    if cli_mode == "tag":
        cmds.append(f"vlan port {uni} mode tag vlan {validate_vlan(vlan_id)}")
    elif cli_mode == "hybrid":
        cmds.append(f"vlan port {uni} mode hybrid def-vlan {validate_vlan(vlan_id)}")
        if allowed_vlans:
            cmds.append(f"vlan port {uni} vlan {_vlan_list(validate_vlans(allowed_vlans))}")
    else:  # trunk
        cmds.append(f"vlan port {uni} mode trunk")
        if allowed_vlans:
            cmds.append(f"vlan port {uni} vlan {_vlan_list(validate_vlans(allowed_vlans))}")
    cmds.append("exit")
    return cmds


def build_wifi_clear(slot: int, port: int, onu_id: int, *, wifi_port: int) -> list[str]:
    """Tombol "Clear WiFi port settings".

    BATAS FIRMWARE (terbukti di ONU uji 2026-10-25, ZTE-F670L di C320): baris
    `ssid auth wpa <uni> ...` TIDAK bisa dihapus — `no ssid auth ...` dijawab
    "%Error 20206: Unrecognized command" dan `restore wifi` pun tidak membuangnya.
    Jadi clear hanya mengembalikan nama SSID, VLAN port, dan state; auth/key lama
    tetap tertulis di OMCI sampai ditimpa `build_wifi_port` berikutnya.
    `no ssid ctrl <uni>` saja dijawab "Incomplete command." — wajib sampai `name`.
    """
    uni = wifi_uni(wifi_port)
    iface = onu_iface(slot, port, onu_id)
    return [f"pon-onu-mng {iface}", f"no ssid ctrl {uni} name",
            f"no vlan port {uni} mode", "restore wifi", "exit"]


def build_onu_type(slot: int, port: int, onu_id: int, *, onu_type: str) -> list[str]:
    """Change ONU type — `type <nama>` di interface ONU (terbukti ada di help)."""
    return [f"interface {onu_iface(slot, port, onu_id)}",
            f"type {validate_profile_name(onu_type)}", "exit"]


def build_speed_profile(slot: int, port: int, onu_id: int, *, upload_profile: str | None,
                        download_profile: str | None) -> list[str]:
    """Configure speed profiles: tcont (upload) + gemport traffic-limit (download).

    TIDAK dipakai jalur produksi mana pun (speed profile lewat job memakai
    `zte_c320.modify`); dipertahankan karena `tests/test_onu_actions.py` masih
    mengujinya dan file tes itu di luar kepemilikan area ini. Menghapusnya tanpa
    memperbarui tes tersebut hanya akan memecahkan tes, bukan membersihkan kode.
    """
    if not upload_profile and not download_profile:
        raise ValueError("Minimal satu arah profil harus diisi")
    cmds = [f"interface {onu_iface(slot, port, onu_id)}"]
    if upload_profile:
        cmds.append(f"tcont 1 profile {validate_profile_name(upload_profile)}")
        cmds.append("gemport 1 tcont 1")
    if download_profile:
        cmds.append(
            f"gemport 1 traffic-limit downstream {validate_profile_name(download_profile)}"
        )
    cmds.append("exit")
    return cmds


def build_mgmt_ip(slot: int, port: int, onu_id: int, *, mode: str, ip: str | None,
                  netmask: str | None = "255.255.255.0") -> list[str]:
    """Update Management IP. mode: pool (auto-assign) | manual | release."""
    iface = onu_iface(slot, port, onu_id)
    if mode == "pool":
        inner = "mgmt-ip auto-assign"
    elif mode == "release":
        inner = "mgmt-ip release"
    elif mode == "manual":
        if not ip:
            raise ValueError("mode manual butuh ip")
        inner = f"mgmt-ip {validate_ip(ip)} {validate_netmask(netmask or '255.255.255.0')}"
    else:
        raise ValueError("mode harus pool, manual, atau release")
    return [f"pon-onu-mng {iface}", inner, "exit"]


def build_voip(slot: int, port: int, onu_id: int, *, enabled: bool) -> list[str]:
    """Enable/Disable VoIP: `voip protocol sip` vs `voip protocol none`.

    Hanya itu yang terbukti: round-trip sip -> none -> sip di ONU uji
    gpon-onu_1/4/1:11, 2026-10-25 (tests/test_live_onu_actions.py). TIDAK ada
    sintaks akun SIP (nomor telepon/sandi) yang terbukti di repo — probe help
    `pon-onu-mng` hanya memuat `voip protocol {sip|h248|mgcp|none|non-omci}`,
    dan NEXFIBER-CLI-REFERENCE tidak punya blok akun SIP. Karena itu builder ini
    sengaja TIDAK menerima nomor/sandi, dan service menolaknya eksplisit bila
    dikirim — daripada diam-diam membuangnya seperti dulu.
    """
    return [f"pon-onu-mng {onu_iface(slot, port, onu_id)}",
            f"voip protocol {'sip' if enabled else 'none'}", "exit"]


def build_state(slot: int, port: int, onu_id: int, *, enabled: bool) -> list[str]:
    """Enable/Disable ONU — `enable`/`disable` di interface ONU (terbukti di help)."""
    return [f"interface {onu_iface(slot, port, onu_id)}",
            "enable" if enabled else "disable", "exit"]


def build_replace_sn(slot: int, port: int, onu_id: int, *, onu_type: str,
                     new_sn: str) -> list[str]:
    """Replace ONU by SN: daftar ulang onu id yang sama dengan SN baru."""
    sn = new_sn.strip().upper()
    if not re.match(r"^[A-Z0-9]{8,20}$", sn):
        raise ValueError(f"Serial number tidak valid: {new_sn!r}")
    return [f"interface {olt_iface(slot, port)}",
            f"onu {onu_id} type {validate_profile_name(onu_type)} sn {sn}", "exit"]
