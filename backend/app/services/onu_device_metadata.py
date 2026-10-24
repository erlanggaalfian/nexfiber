"""Helper TERPISAH (tidak menyentuh parser bersama `drivers/zte_c320._parse_onu_metadata`)
untuk dua hal yang tampil kosong di Detail ONU: metadata terstruktur (zone/alamat/ODP/
tanggal otorisasi) dan daftar VLAN layanan per-ONU.

Semua fungsi di sini PURE (teks masuk, dataclass/list keluar) — tidak ada query DB, tidak
ada perintah ke perangkat, jadi bisa diuji penuh dengan fixture (AGENTS.md: parser wajib
punya unit test fixture).

Sumber format `zone_..._descr_..._odb_..._authd_...` = aplikasi referensi pemilik
(`/home/kamal/smartolt/backend/db.php::parse_structured_description` +
`frontend/action/auth-onu.php` yang MENULIS string itu:
`name_{name}_zone_{zone}_descr_{address}_odb_{splitter}_authd_{YYYYMMDD}`).
Jadi delimiter ini kontrak eksplisit operator, bukan inferensi lokasi karangan.

Aturan anti-fabrikasi:
- field yang tidak ada di description tetap None — tidak ditebak dari field lain,
  TIDAK PERNAH diturunkan dari timestamp sync/registrasi;
- `zone`/`splitter` hanya teks dari perangkat; pemetaan ke baris master `zones`/
  `splitters` BUKAN tugas file ini (butuh dedupe + scope owner, lihat QUEUE);
- VLAN tidak pernah diambil dari description (contoh operator tidak memuat VLAN) —
  hanya dari baris `service-port` running-config.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

# --- Metadata terstruktur dari `description` perangkat ------------------------------

# Delimiter ditulis dengan underscore pembatas; nilainya boleh memuat spasi, titik,
# garis miring, bahkan underscore (mis. "Griya_Rivera_Hills_C_15"), jadi tiap field
# berhenti di delimiter BERIKUTNYA yang dikenal, bukan di underscore pertama.
_DELIMS = ("zone", "descr", "odb", "authd", "contact", "name", "extid")
_NEXT = r"(?=_(?:" + "|".join(_DELIMS) + r")_|$)"


def _field(desc: str, key: str) -> str | None:
    m = re.search(rf"(?:^|_){key}_(.*?){_NEXT}", desc, re.I | re.S)
    if not m:
        return None
    value = m.group(1).strip().strip("_").strip()
    return value or None


def _clean(value: str | None) -> str | None:
    """Kosong/None/"None" (nilai literal yang ditulis aplikasi referensi) = tidak ada."""
    if value is None:
        return None
    value = value.strip()
    return None if value == "" or value.lower() == "none" else value


@dataclass
class DeviceMetadata:
    """Hasil parse satu `description` perangkat. Semua opsional."""

    zone: str | None = None
    address: str | None = None
    splitter: str | None = None
    contact: str | None = None
    external_id: str | None = None
    authorized_on: date | None = None
    # description yang tersisa setelah semua token dikenali dibuang; dipakai sebagai
    # alamat kalau description memang teks bebas (mayoritas ONU OLT SBI).
    free_text: str | None = None
    structured: bool = False


def parse_device_description(description: str | None) -> DeviceMetadata:
    """`description` ONU -> metadata terstruktur.

    Toleran: description boleh (a) terstruktur penuh, (b) campuran (hanya `zone_` atau
    hanya `_authd_`), atau (c) teks bebas. Bentuk (c) TIDAK dipaksa jadi zone/ODP.
    """
    if not description:
        return DeviceMetadata()
    # OLT kadang hard-wrap baris panjang; satukan dulu supaya token tidak terpotong.
    desc = re.sub(r"\s*\r?\n\s*", " ", description).strip()
    has_token = bool(re.search(r"(?:^|_)(?:" + "|".join(_DELIMS) + r")_", desc, re.I))
    meta = DeviceMetadata(structured=has_token)
    if not has_token:
        meta.free_text = _clean(desc)
        return meta

    meta.zone = _clean(_field(desc, "zone"))
    meta.address = _clean(_field(desc, "descr"))
    meta.contact = _clean(_field(desc, "contact"))
    meta.external_id = _clean(_field(desc, "extid"))
    splitter = _clean(_field(desc, "odb"))
    if splitter:
        splitter = re.sub(r"^ODP\s+", "", splitter, flags=re.I)
        # Referensi kadang menempelkan koordinat ke nama ODP; buang jejaknya.
        splitter = re.sub(r"\s*lat\s+-?\d+\.?\d*\s+long\s+-?\d+\.?\d*.*$", "", splitter, flags=re.I)
        splitter = _clean(splitter)
    meta.splitter = splitter
    meta.authorized_on = _parse_authd(desc)
    if meta.address is None:
        # "Alamat bebas_authd_20260425": teks sebelum token pertama adalah alamat.
        head = re.split(r"(?:^|_)(?:" + "|".join(_DELIMS) + r")_", desc, maxsplit=1, flags=re.I)[0]
        meta.free_text = _clean(head.strip(" _"))
    return meta


def _parse_authd(desc: str) -> date | None:
    """`_authd_YYYYMMDD` -> date. Tanggal tidak valid diabaikan (bukan ditebak)."""
    m = re.search(r"(?:^|_)authd_(\d{8})", desc, re.I)
    if not m:
        return None
    raw = m.group(1)
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        return None


# --- VLAN layanan per-ONU dari running-config ---------------------------------------

# `service-port <id> vport <n> user-vlan <inner> vlan <outer>` — nilai yang dipakai
# untuk display adalah angka SETELAH keyword `vlan` (sesuai instruksi user). `user-vlan`
# tetap diambil supaya selisih inner/outer bisa dilaporkan, tidak disembunyikan.
_SERVICE_PORT_RE = re.compile(
    r"^[ \t]*service-port\s+(?P<sp>\d+)\s+vport\s+(?P<vport>\d+)\s+"
    r"user-vlan\s+(?P<user_vlan>\d+)\s+vlan\s+(?P<vlan>\d+)\s*$",
    re.M | re.I,
)


@dataclass
class ServicePort:
    service_port: int
    vport: int
    user_vlan: int
    vlan: int


def parse_service_ports(config_text: str) -> list[ServicePort]:
    """Semua baris `service-port` satu stanza `interface gpon-onu_...` (urutan perangkat)."""
    return [
        ServicePort(int(m["sp"]), int(m["vport"]), int(m["user_vlan"]), int(m["vlan"]))
        for m in _SERVICE_PORT_RE.finditer(config_text or "")
    ]


def service_vlan_ids(config_text: str) -> list[int]:
    """VLAN layanan per-ONU, dedupe, urutan STABIL (urutan kemunculan di perangkat).

    Tidak memilih "primary" satu VLAN saja: ONU multi-layanan (mis. 15 + 100) harus
    tampil utuh.
    """
    seen: list[int] = []
    for sp in parse_service_ports(config_text):
        if sp.vlan not in seen:
            seen.append(sp.vlan)
    return seen


@dataclass
class ServiceVlan:
    vlan_id: int  # nomor VLAN di perangkat (yang setelah keyword `vlan`)
    name: str | None = None  # dari master `vlans` kalau cocok (olt_id + vlan_id)
    is_management: bool = False  # master `vlans.type == "management"`
    in_master: bool = False  # False = ada di perangkat tapi belum ada di master


def classify_service_vlans(
    vlan_ids: list[int], master: Mapping[int, tuple[str | None, str | None]]
) -> list[ServiceVlan]:
    """Gabungkan VLAN perangkat dengan master VLAN **OLT yang sama**.

    `master` = {vlan_id: (name, type)} hasil query `vlans` untuk olt_id ONU (plus VLAN
    global kalau pemanggil mau menggabungkannya). `is_management` HANYA dari
    `vlans.type == "management"` — tidak ada angka yang di-hardcode sebagai management.
    VLAN yang belum ada di master tetap ditampilkan (`in_master=False`): itu data nyata
    perangkat, bukan error.
    """
    rows: list[ServiceVlan] = []
    for vid in vlan_ids:
        name, vtype = master.get(vid, (None, None))
        rows.append(ServiceVlan(
            vlan_id=vid, name=name,
            is_management=(vtype == "management"),
            in_master=vid in master,
        ))
    return rows


def display_service_vlans(rows: list[ServiceVlan]) -> list[ServiceVlan]:
    """Baris untuk kolom "VLAN" Detail ONU: VLAN management disembunyikan.

    Kalau SEMUA VLAN ONU bertanda management, hasilnya daftar KOSONG — pemanggil wajib
    menampilkan itu apa adanya (jujur), tidak jatuh balik ke VLAN management.
    """
    return [r for r in rows if not r.is_management]
