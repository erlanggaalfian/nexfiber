"""Uji LANGSUNG ke OLT pada ONU uji — SKIP kecuali `NEXFIBER_LIVE_TEST=1`.

Izin uji dari pemilik HANYA untuk ONU `gpon-onu_1/4/1:11` di OLT TGR. ONU lain, SN
ZTEGDDBFFDCA, OLT id=13 (avani), dan OLT 'SBI' id=31 TIDAK boleh disentuh.

Pola tiap uji: snapshot running-config -> jalankan satu kind -> baca balik -> KEMBALIKAN
ke nilai semula -> bandingkan dengan snapshot. Kind yang berisiko memutus
(reboot/delete/restore-factory/move/replace-sn) TIDAK dijalankan di sini.

Kredensial dibaca dari `olts` lewat `build_driver` (vault/konfigurasi yang sudah ada) —
tidak pernah ditulis di file ini maupun di output test.

Jalankan:
  cd backend && NEXFIBER_LIVE_TEST=1 NEXFIBER_CONFIG=/etc/nexfiber/config.ini \
    PYTHONPATH=. /opt/nexfiber/venv/bin/python -m pytest tests/test_live_onu_actions.py -q -s
"""

import os
import re

import pytest

from app.drivers import zte_onu_actions as za
from app.services.onu_action_service import redact_commands

pytestmark = pytest.mark.skipif(
    os.environ.get("NEXFIBER_LIVE_TEST") != "1",
    reason="Uji live ke OLT hanya jalan bila NEXFIBER_LIVE_TEST=1",
)

# ONU uji ada di OLT "TGR". Di DB Nexfiber id barisnya bisa berbeda dari id SmartOLT
# (yang bernomor 8), jadi OLT dicari lewat NAMA, bukan id yang di-hardcode.
OLT_NAME = os.environ.get("NEXFIBER_LIVE_OLT", "TGR")
SLOT, PORT, IDX = 4, 1, 11
IFACE = za.onu_iface(SLOT, PORT, IDX)
FORBIDDEN_NAMES = {"avani", "sbi"}  # jangan pernah dipakai untuk uji tulis


def _redact(text: str) -> str:
    return re.sub(r"\b(key|password|pass|secret)\s+(?!default\b)\S+", r"\1 <REDACTED>", text)


async def _driver():
    """Driver OLT uji dari baris `olts` (kredensial lewat build_driver, tidak pernah di sini)."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.drivers.factory import build_driver
    from app.models.olt import Olt

    assert OLT_NAME.lower() not in FORBIDDEN_NAMES, f"OLT {OLT_NAME} dilarang untuk uji tulis"
    async with SessionLocal() as db:
        olt = (await db.execute(select(Olt).where(Olt.name == OLT_NAME))).scalar_one_or_none()
        if olt is None:
            pytest.skip(f"OLT {OLT_NAME!r} belum terdaftar di DB Nexfiber")
        return build_driver(olt)


async def _snapshot(driver) -> tuple[str, str]:
    async with driver._open_cli() as cli:
        return (await cli.show(f"show running-config interface {IFACE}"),
                await cli.show(f"show onu running config {IFACE}"))


@pytest.mark.asyncio
async def test_eth_port_bolak_balik():
    """eth_0/1: hybrid + allowed VLAN + DHCP from-internet, lalu kembalikan ke semula.

    Nilai ujinya sengaja NON-default (`from-internet`, bukan `no-ctrl`): C320 tidak
    menuliskan nilai default ke running-config, jadi uji dengan default tidak bisa
    dibedakan dari "perintah tidak berefek".
    """
    driver = await _driver()
    before_if, before_mng = await _snapshot(driver)
    assert "dhcp-ip ethuni eth_0/1 from-onu" in before_mng, "nilai awal berubah; batalkan uji"

    cmds = za.build_eth_port(SLOT, PORT, IDX, eth_port=1, enabled=True, mode="hybrid",
                             vlan_id=15, allowed_vlans=[15, 100], dhcp="isp")
    result = await driver.run_onu_commands(cmds)
    print("CMD:", " ; ".join(redact_commands(cmds)))
    assert result.success, _redact(result.raw_output)

    _, mid = await _snapshot(driver)
    assert "vlan port eth_0/1 mode hybrid def-vlan 15" in mid
    assert "vlan port eth_0/1 vlan 15,100" in mid
    assert "dhcp-ip ethuni eth_0/1 from-internet" in mid

    # Kembalikan: `no vlan port ...` wajib lengkap sampai sub-kata (mode/vlan).
    assert (await driver.run_onu_commands([
        f"pon-onu-mng {IFACE}", "no vlan port eth_0/1 vlan 15,100",
        "no vlan port eth_0/1 mode", "dhcp-ip ethuni eth_0/1 from-onu",
        "interface eth eth_0/1 state unlock", "exit"])).success
    after_if, after_mng = await _snapshot(driver)
    assert "dhcp-ip ethuni eth_0/1 from-onu" in after_mng
    assert after_if == before_if
    assert after_mng == before_mng


@pytest.mark.asyncio
async def test_voip_bolak_balik():
    """voip protocol sip -> none -> sip (nilai semula di ONU uji = sip)."""
    driver = await _driver()
    _, before = await _snapshot(driver)
    assert "voip protocol sip" in before

    assert (await driver.run_onu_commands(
        za.build_voip(SLOT, PORT, IDX, enabled=False))).success
    _, mid = await _snapshot(driver)
    assert "voip protocol sip" not in mid

    assert (await driver.run_onu_commands(
        za.build_voip(SLOT, PORT, IDX, enabled=True))).success
    _, after = await _snapshot(driver)
    assert "voip protocol sip" in after


@pytest.mark.asyncio
async def test_attached_vlans_idempotent():
    """Kirim ulang pasangan VLAN yang SAMA harus diterima OLT (bukan "already exists").

    Sengaja tidak mengurangi jumlah VLAN: `no service-port` pada ONU hidup memutus
    trafik pelanggan, dan ONU uji ini dipakai bersama service lain.
    """
    driver = await _driver()
    before_if, before_mng = await _snapshot(driver)
    assert "user-vlan 15 vlan 15" in before_if and "user-vlan 100 vlan 100" in before_if

    result = await driver.run_onu_commands(za.build_attached_vlans(SLOT, PORT, IDX, [15, 100]))
    assert result.success, _redact(result.raw_output)
    after_if, after_mng = await _snapshot(driver)
    assert after_if == before_if
    assert after_mng == before_mng


@pytest.mark.asyncio
async def test_perintah_salah_ditolak_bukan_dilaporkan_sukses():
    """Driver tidak boleh melaporkan success untuk perintah yang ditolak OLT."""
    driver = await _driver()
    result = await driver.run_onu_commands(
        [f"pon-onu-mng {IFACE}", "perintah-yang-tidak-ada 1", "exit"])
    assert not result.success


@pytest.mark.asyncio
async def test_config_akhir_sama_dengan_snapshot_awal():
    """Dijalankan terakhir: pastikan ONU uji kembali seperti sebelum seluruh uji."""
    driver = await _driver()
    cfg_if, cfg_mng = await _snapshot(driver)
    for wajib in ("tcont 1 profile", "service-port 1 vport 1 user-vlan 15 vlan 15",
                  "service-port 2 vport 2 user-vlan 100 vlan 100"):
        assert wajib in cfg_if, f"hilang dari running-config: {wajib}"
    for wajib in ("voip protocol sip", "dhcp-ip ethuni eth_0/1 from-onu",
                  "switchport-bind switch_0/1 veip 1", "tr069-mgmt 1 state unlock"):
        assert wajib in cfg_mng, f"hilang dari pon-onu-mng: {wajib}"
