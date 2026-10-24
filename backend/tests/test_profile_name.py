"""Pembersih nama speed profile (`app.core.profile_name`): token SmartOLT dibuang, sisa
nama tidak dirusak. Satu-satunya tempat varian nama perangkat nyata dikunci.
"""

from app.core.profile_name import clean_profile_name
from app.drivers.types import TrafficProfile
from app.models.speed_profile import SpeedProfile
from app.services import speed_profile_service


def test_clean_profile_name_strips_smartolt_token():
    assert clean_profile_name("SMARTOLT-5Mbps") == "5Mbps"
    assert clean_profile_name("5Mbps_SmartOLT") == "5Mbps"
    assert clean_profile_name("SmartOLT 10M") == "10M"
    assert clean_profile_name("smartolt_20Mbps") == "20Mbps"
    assert clean_profile_name("SMARTOLT-HFA_Lite") == "HFA_Lite"
    assert clean_profile_name("SMARTOLT-VOIPMNG-10M") == "VOIPMNG-10M"


def test_clean_profile_name_keeps_everything_else():
    # Token hanya dibuang sebagai kata utuh: `KhanzaNet` dan nama yang memuat huruf
    # bersambung tidak boleh tersentuh.
    for name in ("KhanzaNet", "PAKET20", "SmartOLTX", "XSmartOLT", "Smart OLT 10M"):
        assert clean_profile_name(name) == name


def test_clean_profile_name_never_returns_empty():
    assert clean_profile_name("SMARTOLT") == "SMARTOLT"
    assert clean_profile_name("-smartolt_") == "-smartolt_"
    assert clean_profile_name("") == ""
    assert clean_profile_name(None) is None


def test_merge_profiles_cleans_name_and_matches_existing_clean_row():
    """Device `SMARTOLT-5Mbps_DN` + baris DB `5Mbps` = sudah ada, jangan duplikat."""
    device = [
        TrafficProfile("SMARTOLT-5Mbps_DN", "download", 5000),
        TrafficProfile("SMARTOLT-10M_UP", "upload", 10000),
    ]
    existing = [SpeedProfile(name="5Mbps", direction="download", speed_kbps=5000)]
    assert speed_profile_service.merge_profiles(existing, device) == [
        ("SMARTOLT-10M", "upload", 10000),
    ]
