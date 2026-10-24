"""Unit test Fase B4: parser profile kecepatan ZTE + merge hasil "Baca dari OLT",
plus push VLAN/speed profile lewat driver palsu (TIDAK pernah menyentuh device nyata).
"""

import pytest

from app.core.exceptions import CommandRejectedError
from app.drivers.types import DriverResult, TrafficProfile
from app.drivers.zte_c320 import _parse_traffic_profiles
from app.models.speed_profile import SpeedProfile
from app.services import speed_profile_service, vlan_service

CLI_OUTPUT = """
profile tcont PAKET20_UP type 5 fixed 64 assured 64 maximum 20000
profile tcont PAKET50_UP type 5 fixed 64 assured 64 maximum 50000
profile traffic PAKET20_DN sir 1000 pir 20000
profile traffic PAKET50_DN sir 1000 pir 50000
profile traffic BROKEN_DN sir 1000
ZXAN#
"""


def test_parse_traffic_profiles():
    got = _parse_traffic_profiles(CLI_OUTPUT)
    assert got == [
        TrafficProfile("PAKET20_UP", "upload", 20000),
        TrafficProfile("PAKET50_UP", "upload", 50000),
        TrafficProfile("PAKET20_DN", "download", 20000),
        TrafficProfile("PAKET50_DN", "download", 50000),
        TrafficProfile("BROKEN_DN", "download", None),
    ]


def test_merge_profiles_skips_known_unpaired_and_unparsed():
    device = _parse_traffic_profiles(CLI_OUTPUT) + [TrafficProfile("ORPHAN_UP", "upload", 1000)]
    existing = [SpeedProfile(name="PAKET20", download_kbps=20000, upload_kbps=20000)]
    assert speed_profile_service.merge_profiles(existing, device) == [("PAKET50", 50000, 50000)]


# --- driver palsu: push VLAN / speed profile tanpa device nyata --------------

class FakeDriver:
    def __init__(self, success=True):
        self.success = success
        self.calls: list[tuple] = []

    async def create_vlan(self, vlan_id, description):
        self.calls.append(("create_vlan", vlan_id, description))
        return self._result(f"vlan {vlan_id}")

    async def delete_vlan(self, vlan_id):
        self.calls.append(("delete_vlan", vlan_id))
        return self._result(f"no vlan {vlan_id}")

    async def create_traffic_profiles(self, name, download_kbps, upload_kbps):
        self.calls.append(("create_traffic_profiles", name, download_kbps, upload_kbps))
        return self._result(f"profile tcont {name}_UP")

    def _result(self, command):
        return DriverResult(
            success=self.success, raw_command=command,
            raw_output="" if self.success else "%Error: command rejected",
            message="" if self.success else "OLT rejected command",
        )


class FakeJob:
    id = 1
    created_by = None
    olt_id = 8

    def __init__(self, payload):
        self.payload = payload


class FakeDb:
    """Cukup untuk service: get() objek yang sudah disiapkan, add/delete/commit dicatat."""

    def __init__(self, obj):
        self.obj = obj
        self.deleted: list = []
        self.added: list = []
        self.commits = 0

    async def get(self, _model, _pk):
        return self.obj

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def _allow_writes(monkeypatch):
    monkeypatch.setattr("app.services.onu_service.settings.allow_write_commands", True)


async def test_push_create_vlan_sends_command_and_activates(monkeypatch):
    from app.models.vlan import Vlan

    vlan = Vlan(id=3, olt_id=8, vlan_id=100, name="INTERNET", description=None, is_active=False)
    db, driver = FakeDb(vlan), FakeDriver()
    monkeypatch.setattr(vlan_service, "log_activity", _noop_log)
    out = await vlan_service.push_create(db, FakeJob({"vlan_db_id": 3}), driver)
    assert driver.calls == [("create_vlan", 100, "INTERNET")]
    assert vlan.is_active is True
    assert out["raw_command"] == "vlan 100"


async def test_push_delete_vlan_removes_row(monkeypatch):
    from app.models.vlan import Vlan

    vlan = Vlan(id=3, olt_id=8, vlan_id=100, name="INTERNET")
    db, driver = FakeDb(vlan), FakeDriver()
    monkeypatch.setattr(vlan_service, "log_activity", _noop_log)
    await vlan_service.push_delete(db, FakeJob({"vlan_db_id": 3}), driver)
    assert driver.calls == [("delete_vlan", 100)]
    assert db.deleted == [vlan]


async def test_rejected_vlan_command_raises_and_keeps_row(monkeypatch):
    from app.models.vlan import Vlan

    vlan = Vlan(id=3, olt_id=8, vlan_id=100, name="INTERNET")
    db, driver = FakeDb(vlan), FakeDriver(success=False)
    monkeypatch.setattr(vlan_service, "log_activity", _noop_log)
    with pytest.raises(CommandRejectedError):
        await vlan_service.push_delete(db, FakeJob({"vlan_db_id": 3}), driver)
    assert db.deleted == []


async def test_push_speed_profile_sets_device_profile_names(monkeypatch):
    profile = SpeedProfile(id=5, name="PAKET20", download_kbps=20000, upload_kbps=10000, olt_id=8)
    db, driver = FakeDb(profile), FakeDriver()
    monkeypatch.setattr(speed_profile_service, "log_activity", _noop_log)
    await speed_profile_service.push_to_olt(db, FakeJob({"speed_profile_id": 5}), driver)
    assert driver.calls == [("create_traffic_profiles", "PAKET20", 20000, 10000)]
    assert (profile.srv_profile_id, profile.line_profile_id) == ("PAKET20_UP", "PAKET20_DN")


async def _noop_log(*_a, **_kw):
    return None
