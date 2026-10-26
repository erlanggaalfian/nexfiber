"""Unit test sampler histori trafik: hitung bps, wrap counter, dan reset.

Tanpa OLT/DB: `delta_bps` adalah fungsi murni, dan itulah satu-satunya tempat laju
dihitung (service memakai fungsi ini, frontend hanya menggambar angkanya).
"""

import pytest

from app.services.onu_traffic_history_service import (
    MAX_DELTA_S,
    RETENTION_DAYS,
    SAMPLE_INTERVAL_MINUTES,
    delta_bps,
)

C32 = 1 << 32
C64 = 1 << 64


def test_bps_hitungan_dasar():
    """1_000_000 octet dalam 10 detik = 800_000 bit/detik."""
    assert delta_bps(0, 1_000_000, 10.0, 64) == 800_000


def test_bps_memakai_selisih_bukan_nilai_absolut():
    assert delta_bps(5_000_000, 5_001_250, 10.0, 64) == 1000


@pytest.mark.parametrize("bits", [32, 64])
def test_wrap_counter_dikoreksi_modulus(bits):
    """Counter unsigned berputar: 10 octet sebelum batas -> 15 sesudahnya = 25 octet."""
    modulus = 1 << bits
    assert delta_bps(modulus - 10, 15, 1.0, bits) == 25 * 8


def test_lompatan_besar_dianggap_reset_dan_mengembalikan_none():
    """Agen SNMP restart: counter turun jauh. Jangan gambar angka raksasa — None."""
    assert delta_bps(C64 - 1, C64 // 2, 1.0, 64) is None
    assert delta_bps(1_000_000_000, 5, 300.0, 32) is None


def test_reset_ke_nol_pada_counter32_tidak_jadi_angka_karangan():
    """Reset ke 0 dari nilai tinggi: delta setelah modulus > setengah ruang -> None."""
    assert delta_bps(C32 - 1_000, 0, 300.0, 32) == 1_000 * 8 // 300  # wrap wajar
    # Reset ke 0 dari nilai rendah: delta setelah modulus > setengah ruang -> tak dipercaya.
    assert delta_bps(C32 // 2 - 100, 0, 300.0, 32) is None


def test_waktu_tidak_maju_tidak_pernah_dibagi():
    assert delta_bps(0, 100, 0.0, 64) is None
    assert delta_bps(0, 100, -5.0, 64) is None


def test_jeda_terlalu_lama_tidak_dirata_ratakan():
    """Worker mati berjam-jam: rata-rata lintas jam menyamarkan puncak -> None."""
    assert delta_bps(0, 10**9, MAX_DELTA_S + 1, 64) is None
    assert delta_bps(0, 10**9, MAX_DELTA_S, 64) is not None


def test_counter_tidak_bergerak_adalah_nol_bukan_none():
    """Nol NYATA (counter sama) harus terbaca 0, bukan 'tidak diketahui'."""
    assert delta_bps(12_345, 12_345, 300.0, 64) == 0


def test_konstanta_interval_dan_retensi():
    assert SAMPLE_INTERVAL_MINUTES == 5
    assert RETENTION_DAYS == 30
