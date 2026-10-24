"""Bug Rx -30 dBm palsu: ONU dying-gasp/LOS tidak boleh menyimpan nilai optik lama.

Pasangan dari test_optical_clear_on_down.py (jalur sinkron SNMP); di sini jalur
"Cek ulang" / refresh_onu_detail (CLI detail-info) dan bucket LOS di core.signal.
"""

import pytest

from app.core.signal import rx_bucket
from app.drivers.types import OnuLiveDetail
from app.services import onu_service
from tests.test_onu_detail_c2 import FakeDb, FakeDriver, FakeJob, _onu, _pon

OPTICAL = ("rx_power_dbm", "tx_power_dbm", "olt_rx_power_dbm",
           "temperature_c", "voltage_v", "bias_current_ma")


@pytest.fixture
def patched(monkeypatch):
    onu, pon = _onu(), _pon()

    async def fake_load(_db, _job):
        return onu, pon

    async def noop(*_a, **_kw):
        return None

    monkeypatch.setattr(onu_service, "_load", fake_load)
    monkeypatch.setattr(onu_service, "log_activity", noop)
    return onu, pon


def _stale(onu):
    onu.rx_power_dbm = -24.0
    onu.tx_power_dbm = 2.1
    onu.olt_rx_power_dbm = -18.2
    onu.temperature_c = 43.5
    onu.voltage_v = 3.28
    onu.bias_current_ma = 12.0


def _detail_driver(driver, monkeypatch, detail):
    async def fetch(*_a):
        return detail

    monkeypatch.setattr(driver, "fetch_onu_detail", fetch)
    return driver


@pytest.mark.parametrize("phase", ["dyinggasp", "DyingGasp", "los", "offline"])
async def test_refresh_clears_optical_when_onu_not_working(patched, monkeypatch, phase):
    """ONU mati: 6 kolom optik ditulis apa adanya (None), bukan nilai lama."""
    onu, _ = patched
    _stale(onu)
    driver = _detail_driver(FakeDriver(), monkeypatch,
                            OnuLiveDetail(phase_state=phase, raw_command="x"))
    await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), driver)
    assert [getattr(onu, f) for f in OPTICAL] == [None] * len(OPTICAL)


async def test_refresh_keeps_versions_when_onu_not_working(patched, monkeypatch):
    """Versi software/hardware bukan nilai optik: tetap pola `if value is not None`."""
    onu, _ = patched
    onu.software_version = "V1.0"
    onu.hardware_version = "V5.0"
    onu.distance_m = 1832
    driver = _detail_driver(FakeDriver(), monkeypatch,
                            OnuLiveDetail(phase_state="los", raw_command="x"))
    await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), driver)
    assert (onu.software_version, onu.hardware_version, onu.distance_m) == ("V1.0", "V5.0", 1832)


async def test_refresh_keeps_optical_when_working_but_unparsed(patched, monkeypatch):
    """ONU working + parser gagal (None) = bacaan tidak terbaca, jangan hapus nilai lama."""
    onu, _ = patched
    _stale(onu)
    driver = _detail_driver(FakeDriver(), monkeypatch,
                            OnuLiveDetail(phase_state="working", raw_command="x"))
    await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), driver)
    assert onu.rx_power_dbm == -24.0


async def test_refresh_keeps_optical_when_phase_state_unknown(patched, monkeypatch):
    """phase_state kosong = format output beda, bukan bukti ONU mati."""
    onu, _ = patched
    _stale(onu)
    driver = _detail_driver(FakeDriver(), monkeypatch, OnuLiveDetail(raw_command="x"))
    await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), driver)
    assert onu.rx_power_dbm == -24.0


async def test_refresh_working_writes_fresh_optical(patched):
    """Jalur normal tetap jalan: ONU working menulis nilai baru."""
    onu, _ = patched
    _stale(onu)
    await onu_service.refresh_onu_detail(FakeDb(), FakeJob(), FakeDriver())
    assert (onu.rx_power_dbm, onu.olt_rx_power_dbm) == (-26.51, -18.24)


def test_rx_bucket_none_is_los_not_critical():
    """Rx NULL = tidak ada bacaan (LOS). Kalau jadi 'critical', tabel/filter/CSV
    akan melaporkan ONU mati sebagai sinyal kritis -- itu bug Rx -30 dBm palsu."""
    assert rx_bucket(None) == "los"
    assert rx_bucket(-30.0) == "critical"
