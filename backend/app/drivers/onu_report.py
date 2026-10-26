"""Perakitan teks output diagnostik satu ONU (tombol Status / Running config / Info SW).

Semua fungsi di sini PURE (teks masuk, teks keluar) supaya bisa diuji dengan fixture
tanpa menyentuh OLT (AGENTS.md: parser CLI wajib punya unit test fixture).

Aturan anti-fabrikasi (ONU-DETAIL-OUTPUT-PARITY-PROPOSAL §3.3): bila perangkat tidak
menjawab sebuah blok, blok itu ditulis `NOT_REPORTED` atau pesan error perangkat apa
adanya. TIDAK ADA nilai contoh/demo yang diisikan — aplikasi referensi melakukan itu
(MAC `ec6c.b532.be20`, `eth_0/1 auto unlock 1632 0`, `pots_0/1 none`) dan itu bug, bukan
fitur.
"""

import re
from ipaddress import ip_address

from app.drivers.errors import ZTE_ERROR_PATTERNS, is_error_output

NOT_REPORTED = "tidak dilaporkan perangkat"

# Judul + urutan blok = kontrak output tombol (dipaku di test).
STATUS_BLOCKS = (
    "Optical status",
    "ONU CATV port",
    "ONU details",
    "History",
    "ONU WAN Interfaces",
    "ONU LAN Interfaces status",
    "Realtime VLAN info",
    "VoIP status",
    "MACs on OLT from this ONU",
)
RUNNING_BLOCKS = ("interface gpon-olt", "interface gpon-onu", "pon-onu-mng")
SOFTWARE_BLOCKS = ("ONU Details", "Features reported by ONU", "Software Region")

# Baris sisa sesi CLI yang bukan isi jawaban: echo command, prompt, paging.
_NOISE_RE = re.compile(
    r"^\s*(?:[\w.\-]+(?:\([\w\-/:]+\))?[#>]\s*.*|show\s+.*|Building configuration\.\.\."
    r"|--More--|\x1b\[[0-9;]*[A-Za-z])\s*$",
    re.I,
)


def clean_output(raw: str) -> str:
    """Buang echo command/prompt/paging, rapikan baris kosong berulang.

    Isi jawaban perangkat TIDAK diubah: tidak ada field yang ditambah, dihapus, atau
    dinormalisasi nilainya.
    """
    lines = [ln.rstrip() for ln in (raw or "").replace("\r", "").split("\n")]
    kept: list[str] = []
    for line in lines:
        if _NOISE_RE.match(line):
            continue
        if not line.strip() and (not kept or not kept[-1].strip()):
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def block_text(raw: str) -> str:
    """Isi satu blok: teks perangkat apa adanya, atau penanda tidak dilaporkan.

    Pesan error perangkat (`%Error …`) DITAMPILKAN apa adanya — itu jawaban nyata dan
    lebih berguna daripada menyembunyikannya.
    """
    cleaned = clean_output(raw)
    if not cleaned.strip():
        return NOT_REPORTED
    if is_error_output(cleaned, ZTE_ERROR_PATTERNS):
        return cleaned.strip()
    return cleaned


def render(blocks: list[tuple[str, str]]) -> str:
    """Judul blok + isi, dipisah satu baris kosong (format sama dengan contoh user)."""
    return "\n\n".join(f"{title}\n{body}" for title, body in blocks).strip()


# --- Status (9 blok) ---------------------------------------------------------------

_HISTORY_RE = re.compile(
    r"^[ \t]*(?:Authpass|Online/Offline)?\s*History\s*:?\s*$(.*?)"
    r"(?=^\s*\S+\s*:\s|\Z)",
    re.I | re.M | re.S,
)


def history_block(detail_info: str) -> str:
    """Blok `History` diambil dari keluaran `show gpon onu detail-info` yang sama.

    Tidak ada command tambahan: histori authpass/offline memang bagian dari output itu.
    """
    match = _HISTORY_RE.search((detail_info or "").replace("\r", ""))
    if match is None:
        return NOT_REPORTED
    return block_text(match.group(1))


def optical_block(attenuation: str, olt_rx_dbm: float | None) -> str:
    """Blok 1: keluaran attenuation apa adanya + satu baris Rx OLT dari SNMP bila ada.

    Nilai SNMP dibaca lewat jalur optical yang sudah ada di driver (DRY: tidak ada
    pembacaan OID kedua di modul ini).
    """
    body = block_text(attenuation)
    if olt_rx_dbm is None:
        return body
    line = f"1310nm OLT Rx for this ONU: {olt_rx_dbm:.2f} (dBm) [SNMP]"
    return line if body == NOT_REPORTED else f"{body}\n{line}"


def status_report(*, attenuation: str, catv: str, detail_info: str, ip_host: str,
                  eth: str, vlan: str, voip: str, macs: str,
                  olt_rx_dbm: float | None = None) -> str:
    bodies = (
        optical_block(attenuation, olt_rx_dbm),
        block_text(catv),
        block_text(detail_info),
        history_block(detail_info),
        block_text(ip_host),
        block_text(eth),
        block_text(vlan),
        block_text(voip),
        block_text(macs),
    )
    return render(list(zip(STATUS_BLOCKS, bodies, strict=True)))


# --- Running config (3 blok) -------------------------------------------------------

def registration_block(detail_info: str, pon: str, onu_id: int) -> str:
    """Blok 1: `onu <id> type <T> sn <SN>` dari `show gpon onu detail-info` ONU itu saja.

    Nilainya dibaca dari perangkat (Type & Serial number), bukan dump config satu PON.
    """
    txt = clean_output(detail_info)
    typ = re.search(r"^\s*Type:\s*(\S+)", txt, re.M)
    sn = re.search(r"^\s*Serial number:\s*(\S+)", txt, re.M)
    if not (typ and sn):
        return NOT_REPORTED
    return f"interface gpon-olt_{pon}\n onu {onu_id} type {typ.group(1)} sn {sn.group(1)}"


def _strip_config_tail(raw: str) -> str:
    """Buang baris `end` dan `!` penutup supaya tidak dobel dengan separator `!`."""
    lines = [ln for ln in clean_output(raw).split("\n") if ln.strip().lower() != "end"]
    text = "\n".join(lines).strip()
    while text.endswith("!"):
        text = text[:-1].rstrip()
    return text


def running_config_report(*, detail_info: str, onu_iface_config: str,
                          onu_mng_config: str, pon: str, onu_id: int) -> str:
    """Tiga blok dipisah `!`, urutan: registrasi → interface ONU → pon-onu-mng.

    Output ditampilkan UTUH tanpa penyamaran (keputusan eksplisit user). Pemanggil wajib
    memastikan role berwenang; isi blok ini tidak boleh masuk log/fixture/dokumen.
    """
    blocks = []
    for text in (registration_block(detail_info, pon, onu_id),
                 _strip_config_tail(onu_iface_config) or NOT_REPORTED,
                 _strip_config_tail(onu_mng_config) or NOT_REPORTED):
        blocks.append(text if text.strip() else NOT_REPORTED)
    return "\n!\n".join(blocks) + "\n!"


_PPPOE_RE = re.compile(r"^\s*pppoe\s+\d+\b.*?\buser\s+(\S+)(?:.*?\bpassword\s+(\S+))?", re.I | re.M)


def parse_pppoe(running: str) -> tuple[str, str | None] | None:
    """(username, password) dari baris `pppoe N ... user U password P` di pon-onu-mng.

    None bila running-config tidak memuat PPPoE. Hanya fakta dari perangkat; mode lain
    (DHCP/static/bridging) sengaja tidak ditebak dari teks ini.
    """
    m = _PPPOE_RE.search(running or "")
    return (m.group(1), m.group(2)) if m else None


_WAN_FLOW_RE = re.compile(r"^\s*flow\s+1\s+pri\s+\d+\s+vlan\s+(\d+)\s*$", re.I | re.M)


def parse_wan_vlan(running: str) -> int | None:
    """VLAN WAN ONU = `flow 1 pri <p> vlan <N>` di stanza `pon-onu-mng`.

    `flow 1` adalah flow yang dipakai gemport 1 (layanan WAN) pada semua stanza nyata OLT
    ini; flow 2 dst. milik layanan lain (mgmt/VoIP) dan sengaja TIDAK dianggap VLAN WAN.
    None bila perangkat tidak melaporkan baris itu — tidak ada tebakan dari VLAN lain.
    """
    m = _WAN_FLOW_RE.search(running or "")
    return int(m.group(1)) if m else None


_FLOW_RE = re.compile(r"^\s*flow\s+(\d+)\s+pri\s+\d+\s+vlan\s+(\d+)\s*$", re.I | re.M)
_GEM_FLOW_RE = re.compile(r"^\s*gemport\s+(\d+)\s+flow\s+(\d+)\s*$", re.I | re.M)
_IPHOST_RE = re.compile(r"^\s*ip-host\s+(\d+)\s+(.+)$", re.I | re.M)


def parse_management_ip(running: str) -> list[tuple[int, str, str | None]] | None:
    """Kandidat `(VLAN, mode, IP)` per flow, dari pasangan `ip-host N` ↔ `gemport N`
    ↔ `flow F`; pemilih VLAN management ada di layer service.

    Aturan pasangan dari konfigurasi nyata: `ip-host 2` membawa `flow 2` lewat
    `gemport 2 flow 2` — nilai diambil dari baris `ip-host` dan flow-nya, bukan
    menyebar ke semua flow. Tanpa baris `ip-host N` untuk gemport N = inactive.
    Bentuk ambigu/tidak dikenal = None.
    """
    text = running or ""
    flows = {int(flow): int(vlan) for flow, vlan in _FLOW_RE.findall(text)}
    gems = {int(gem): int(flow) for gem, flow in _GEM_FLOW_RE.findall(text)}
    hosts = {int(n): value.strip() for n, value in _IPHOST_RE.findall(text)}
    if any(n not in gems for n in hosts):
        return None  # ip-host tanpa `gemport N` bernomor sama: tak bisa dipasangkan
    out: list[tuple[int, str, str | None]] = []
    for gem, flow in sorted(gems.items()):
        if flow not in flows:
            continue
        value = hosts.get(gem)
        if value is None:
            mode, ip = "inactive", None
        else:
            static = re.search(r"ip-address\s+(\d+\.\d+\.\d+\.\d+)(?:/\d+)?(?:\s|$)", value, re.I)
            if re.search(r"(?:^|\s)dhcp-enable\s+enable(?:\s|$)", value, re.I):
                mode, ip = "dhcp", None
            elif static:
                try:
                    ip = str(ip_address(static.group(1)))
                except ValueError:
                    return None
                mode = "static"
            else:
                return None  # bentuk tidak dikenal
        out.append((flows[flow], mode, ip))
    return out or None


def wan_vlan_not_management(
    wan: int | None,
    candidates: list[tuple[int, str, str | None]] | None,
    management: set[int],
) -> int | None:
    """Aturan: WAN = VLAN yang BUKAN ditandai management; mgmt = yang ditandai.

    `wan` (biasanya `flow 1`) dipakai bila memang bukan management. Bila kena VLAN
    management, ganti dengan kandidat non-management pertama (urutan flow); tidak
    ada kandidat = None — VLAN management tidak boleh jadi VLAN WAN.
    """
    if wan is None or wan not in management:
        return wan
    for vlan, _mode, _ip in candidates or []:
        if vlan not in management:
            return vlan
    return None


# --- Info SW ----------------------------------------------------------------------

_REGION_RE = re.compile(
    r"^\s*(?:Software\s+)?Region\s*(\d+)\s*(?:version)?\s*:.*$", re.I | re.M
)


def software_regions(equip: str) -> str:
    """Region 1/2 hanya ditampilkan bila perangkat benar-benar melaporkannya.

    Pada C300/C320 field per-region itu OMCI-only dan tidak keluar di CLI (dicatat juga
    oleh driver referensi). Tidak ada tebakan di sini.
    """
    lines = [m.group(0).strip() for m in _REGION_RE.finditer(equip or "")]
    return "\n".join(lines) if lines else f"{NOT_REPORTED} (CLI tidak mengekspos Region 1/2)"


def software_report(*, equip: str, capability: str) -> str:
    return render([
        (SOFTWARE_BLOCKS[0], block_text(equip)),
        (SOFTWARE_BLOCKS[1], block_text(capability)),
        (SOFTWARE_BLOCKS[2], software_regions(equip)),
    ])
