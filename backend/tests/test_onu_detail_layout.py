"""Regresi tata letak Detail ONU (satu halaman, urutan blok mengikuti ONU-DETAIL-PARITY.md).

Test ini membaca file TSX sebagai teks — tidak ada runner JS di repo ini, dan yang perlu
dipaku memang bentuk halamannya: urutan blok, tidak ada halaman detail kedua, tidak ada
tombol yang menembak endpoint yang tidak ada, dan tidak ada nama aplikasi referensi yang
ikut masuk kode. Kompilasi tipe tetap dijaga `tsc -b` di build frontend.
"""

import re
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "OnuDetail.tsx"
PAGES_DIR = PAGE.parent
ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers" / "onus.py"
# `/{serial}/traffic` hidup di router terpisah (app/routers/onu_traffic.py) supaya track
# LIVE traffic tidak bentrok dengan onus.py; prefix-nya sama, jadi ikut dipindai di sini.
TRAFFIC_ROUTER = ROUTERS.parent / "onu_traffic.py"


@pytest.fixture(scope="module")
def src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_block_order_matches_reference_layout(src: str):
    """Blok harus muncul dalam urutan referensi: grid identitas, Status, Trafik/Sinyal,
    Profil Kecepatan, Port Ethernet, WiFi, VoIP, CATV, baris aksi."""
    labels = re.findall(r'<Section label="([^"]+)"', src)
    assert labels == [
        "Trafik / Sinyal", "Profil Kecepatan", "Port Ethernet", "WiFi",
    ], labels
    # Kartu identitas/status mendahului seluruh Section, baris aksi sesudahnya.
    assert src.index("lg:grid-cols-2") < src.index('<Section label="Trafik / Sinyal"')
    assert src.index('<Section label="WiFi"') < src.index("Restore factory")


def test_identity_grid_keeps_reference_field_order(src: str):
    """Urutan baris kolom kiri (OLT .. Lokasi) dipaku supaya tidak bergeser diam-diam."""
    rows = re.findall(r'<DRow label="([^"]+)"', src)
    left = rows[: rows.index("Lokasi") + 1]
    assert left[:6] == ["OLT", "Shelf", "Slot", "Port", "ONU", "Kanal"], left[:6]
    assert "SN" in left and "Tipe ONU" in left and "Zone" in left and "Splitter / ODP" in left
    right = rows[rows.index("Lokasi") + 1 :]
    assert right[0] == "Tx ONU", right[0]
    assert "VLAN terpasang" in right and "Mode ONU" in right


def test_only_existing_onu_endpoints_are_called(src: str):
    """Setiap path /api/onus/{serial}<path> yang dipanggil halaman harus ada di router."""
    routes = set(re.findall(r'@router\.\w+\("/\{serial\}([^"]*)"',
                            ROUTERS.read_text() + TRAFFIC_ROUTER.read_text()))
    routes.add("")  # DELETE /{serial}
    called = set(re.findall(r'path: "(/[a-z-]*)"', src)) | {""}
    # Query langsung (signal, logs, info) ikut diperiksa.
    called |= {m for m in re.findall(r'/api/onus/\$\{serial\}(/[a-z-]+)', src)}
    assert called <= routes, called - routes


def test_no_second_detail_page(src: str):
    """Tidak boleh ada halaman detail ONU kedua."""
    others = [p.name for p in PAGES_DIR.glob("*.tsx") if "onudetail" in p.name.lower().replace("_", "")]
    assert others == ["OnuDetail.tsx"], others


def test_reference_app_branding_not_copied(src: str):
    """Nama aplikasi referensi tidak boleh masuk kode/UI Nexfiber."""
    assert "smartolt" not in src.lower()


def test_phase2_menus_are_labelled_not_fake_buttons(src: str):
    """WAN remote / port configure muncul sebagai penanda 'Segera', bukan tombol
    yang memanggil endpoint karangan."""
    for marker in ("Akses remote WAN", "TR-069 profile"):
        assert marker in src
    assert "tr069" not in src.lower().replace("tr-069", "")
    # Kolom aksi port Ethernet tidak boleh jadi <Button ... onClick=...>
    port_block = src[src.index('<Section label="Port Ethernet"') : src.index('<Section label="WiFi"')]
    assert "<Button" not in port_block


def test_tr069_status_button_hidden_without_internal_acs(src: str):
    """Referensi hanya menampilkan tombol "TR069 Status" saat profil TR-069 ONU memakai
    server ACS internal aplikasi. Nexfiber belum punya server ACS internal / katalog profil
    TR-069, jadi penandanya tidak boleh dirender dalam bentuk apa pun (termasuk
    placeholder "Segera") sampai prasyarat itu ada."""
    assert "TR-069 status" not in src
    assert "TR-069 status · Segera" not in src
    # Dan tidak boleh ada kondisi visibility berdasarkan field yang belum dikirim backend.
    assert "tr069_profile" not in src


def test_pppoe_password_never_rendered(src: str):
    """Password PPPoE/ONU tidak pernah dikirim/ditampilkan ke frontend."""
    assert "pppoe_password" not in src
    assert "Tidak ditampilkan" in src


def test_destructive_actions_keep_confirmation_and_rbac(src: str):
    """Hapus & restore factory tetap minta ketik serial dan tetap manager-only."""
    assert src.count("typed === d.serial_number") >= 1
    for action in ('setConfirm("restore-factory")', 'setConfirm("delete")'):
        idx = src.index(action)
        assert "isManager" in src[idx - 200 : idx], action


def test_port_counts_come_from_master_data_not_hardcode(src: str):
    """Jumlah port Ethernet/SSID/VoIP/CATV dibaca dari katalog ONU Types."""
    assert '/api/onu-types' in src
    for field in ("specs.eth_ports", "specs.wifi_ssids", "specs.voip_ports", "specs?.catv"):
        assert field in src, field
