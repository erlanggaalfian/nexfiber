"""Tes putaran fix lifecycle berikutnya (tanpa perangkat, tanpa Postgres):
deteksi error ZTE generik, pengiriman config satu-per-satu (berhenti pada error
pertama, prompt konfirmasi dibatalkan bukan dilaporkan sukses), pembedaan scan
unconfigured gagal vs kosong, dan gate enqueue bersama (replace dari failed).
"""

import pytest

from app.core.exceptions import ConflictError, DriverError, ValidationAppError
from app.drivers.errors import ZTE_ERROR_PATTERNS, is_error_output
from app.drivers.zte_c320 import ZteC320Driver
from app.services.onu_service import _check_onu_job_gate, normalize_customer_id


class FakeCli:
    """send_command per perintah; outputs dipetakan per perintah, sisanya prompt kosong."""

    def __init__(self, outputs: dict[str, str]):
        self.outputs = outputs
        self.sent: list[str] = []

    async def send_command(self, command: str) -> str:
        self.sent.append(command)
        return self.outputs.get(command, "")


def _driver(cli: FakeCli) -> ZteC320Driver:
    driver = ZteC320Driver(host="192.0.2.1", cli_username="u", cli_password="p",
                           cli_protocol="ssh", cli_port=22, snmp_community="c",
                           snmp_port=161)
    driver._open_cli = lambda: _Ctx(cli)  # type: ignore[method-assign]
    return driver


class _Ctx:
    def __init__(self, cli: FakeCli):
        self.cli = cli

    async def __aenter__(self):
        return self.cli

    async def __aexit__(self, *_exc):
        return False


def test_error_patterns_cover_repo_error_texts():
    # Teks error yang benar-benar ada di repo (fixture, docstring driver/aksi).
    for text in (
        "%Error 20202: Invalid input detected at '^' marker.",
        "%Error 20203: Incomplete command",
        "%Error 20206: Unrecognized command",
        "%Code 63953-GPONRM : Flow does not exist.",
        "%Error 20200: Operation failed",
    ):
        assert is_error_output(text, ZTE_ERROR_PATTERNS), text
    assert not is_error_output("ZXA10 C320\nZXAN#", ZTE_ERROR_PATTERNS)


async def test_send_config_stops_on_first_error():
    cli = FakeCli({
        "interface gpon-onu_1/1/1:1": "",
        "no service-port 1": "%Error 20206: Unrecognized command",
        "service-port 1 vport 1 user-vlan 100 vlan 100": "",
    })
    driver = _driver(cli)
    result = await driver.set_onu_vlan(1, 1, 1, 10, 100)
    assert result.success is False
    # Perintah setelah error TIDAK dikirim; exit penutup tetap dikirim.
    assert "service-port 1 vport 1" not in cli.sent
    assert "no service-port 1" in result.raw_command
    assert "service-port 1 vport 1" not in result.raw_command


async def test_send_config_success_sends_all_and_exits():
    cli = FakeCli({})
    driver = _driver(cli)
    result = await driver.set_onu_vlan(1, 1, 1, None, 100)
    assert result.success is True
    assert cli.sent[0] == "configure terminal"
    # Tulis konfigurasi kini di-persist: `write` adalah perintah terakhir,
    # setelah keluar dari mode config (bukan lagi `exit` penutup).
    assert cli.sent[-1] == "write"
    assert "exit" in cli.sent
    assert "flow 1 pri 0 vlan 100" in result.raw_command


async def test_send_config_confirmation_prompt_aborted_not_success():
    cli = FakeCli({
        "no onu 3": "Are you sure to delete? (y/n)",
    })
    driver = _driver(cli)
    result = await driver.delete(1, 1, 3)
    assert result.success is False
    assert "n" in cli.sent  # dibatalkan, bukan dijawab "y" diam-diam
    assert "konfirmasi" in result.message


async def test_list_unconfigured_error_raises_but_empty_marker_ok():
    driver = _driver(FakeCli({"show gpon onu uncfg": "%Error 20206: Unrecognized command"}))
    with pytest.raises(DriverError):
        await driver.list_unconfigured()
    driver2 = _driver(FakeCli({
        "show gpon onu uncfg": "%Code 62310-GPONSRV : No related information to show",
    }))
    assert await driver2.list_unconfigured() == []


class _Onu:
    def __init__(self, config_state, onu_index=1):
        self.config_state = config_state
        self.onu_index = onu_index
        self.id = 1


async def test_gate_replace_allowed_from_failed_like_resync():
    await _check_onu_job_gate(None, _Onu("failed"), "replace_onu")  # type: ignore[arg-type]
    await _check_onu_job_gate(None, _Onu("failed"), "resync_onu")  # type: ignore[arg-type]
    await _check_onu_job_gate(None, _Onu("success"), "replace_onu")  # type: ignore[arg-type]


async def test_gate_replace_blocked_from_initial_and_configuring():
    for state in ("initial", "configuring"):
        with pytest.raises(ConflictError):
            await _check_onu_job_gate(None, _Onu(state), "replace_onu")  # type: ignore[arg-type]


def test_normalize_customer_id_all_spaces_is_empty():
    assert normalize_customer_id("   ") == ""


async def test_update_info_rejects_port_without_splitter(monkeypatch):
    """Aturan baru update_info: port splitter tanpa splitter tidak bermakna."""
    import app.services.onu_service as svc
    from app.models.onu import Onu
    from app.schemas.onu import OnuInfoBody

    onu = Onu(id=1, olt_id=8, pon_port_id=3, serial_number="ZTEGC1234567", onu_index=11,
              status="online", config_state="success", admin_state="enabled",
              splitter_id=None, splitter_port=None)

    async def fake_get_row(_db, _serial, _user):
        return (onu, "OLT", 4, 1, None, None, None, None, None, None, None)

    async def fake_log(_db, **kw):
        return None

    async def fake_get_onu(_db, serial, _user):
        return serial

    monkeypatch.setattr(svc, "_get_row", fake_get_row)
    monkeypatch.setattr(svc, "log_activity", fake_log)
    monkeypatch.setattr(svc, "get_onu", fake_get_onu)

    class Db:
        async def get(self, model, pk):
            return None

        async def commit(self):
            return None

    class U:
        id = 1
        role = "admin"
        admin_id = None

    with pytest.raises(ValidationAppError):
        await svc.update_info(Db(), "ZTEGC1234567", OnuInfoBody(splitter_port=3), U())  # type: ignore[arg-type]
