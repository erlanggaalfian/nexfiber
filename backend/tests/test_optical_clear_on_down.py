"""Bug "ONU down masih punya Rx -30 dBm palsu".

Nilai optik terakhir hanya boleh hidup di riwayat (onu_signal_history). Baris ONU harus
kosong begitu ONU tidak online, dan polling optik 15 menit tidak boleh menghidupkannya lagi.
DB nyata, tanpa menyentuh perangkat (driver dipalsukan).
"""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, text

from app.core.db import SessionLocal, engine
from app.drivers.types import OnuStatusSample, OpticalSample
from app.models.olt import Olt, PonPort
from app.models.onu import Onu, OnuSignalHistory
from app.models.user import User
from app.services import sync_service

OPTICAL = {"rx_power_dbm": -30.0, "tx_power_dbm": 2.1, "olt_rx_power_dbm": -24.5,
           "temperature_c": 45.0, "voltage_v": 3.3, "bias_current_ma": 12.0}


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


class _StatusDriver:
    def __init__(self, samples):
        self.samples = samples

    async def fetch_onu_status(self):
        return self.samples


class _OpticalDriver:
    def __init__(self, samples):
        self.samples = samples

    async def fetch_optical(self, slot, port):
        return self.samples


async def _fixture(tag: str):
    """OLT + PON + dua ONU (index 1 online, index 2 akan turun), keduanya punya nilai optik."""
    async with SessionLocal() as db:
        user = User(username=f"o_{tag}", full_name="o", password_hash="x", role="admin")
        db.add(user)
        await db.flush()
        olt = Olt(name=f"o_{tag}", host="192.0.2.50", vendor="zte", model="C320",
                  cli_username="x", cli_password_enc=b"x", snmp_community_enc=b"x",
                  owner_id=user.id, pon_port_count=8, cli_port=24000 + int(tag, 16) % 9000)
        db.add(olt)
        await db.flush()
        pon = PonPort(olt_id=olt.id, slot=1, port=1)
        db.add(pon)
        await db.flush()
        onus = [
            Onu(olt_id=olt.id, pon_port_id=pon.id, onu_index=i, serial_number=f"O{tag}{i}",
                status="online", config_state="success", **OPTICAL)
            for i in (1, 2)
        ]
        db.add_all(onus)
        await db.commit()
        return olt.id, user.id, onus[0].id, onus[1].id


async def _cleanup(olt_id: int, user_id: int) -> None:
    async with SessionLocal() as db:
        onu_ids = (await db.execute(select(Onu.id).where(Onu.olt_id == olt_id))).scalars().all()
        if onu_ids:
            await db.execute(delete(OnuSignalHistory).where(OnuSignalHistory.onu_id.in_(onu_ids)))
        await db.execute(delete(Onu).where(Onu.olt_id == olt_id))
        await db.execute(delete(PonPort).where(PonPort.olt_id == olt_id))
        await db.execute(delete(Olt).where(Olt.id == olt_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def test_down_onu_loses_optical_values_but_keeps_history() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_id, user_id, up_id, down_id = await _fixture(tag)
    try:
        samples = [
            OnuStatusSample(slot=1, port=1, onu_id=1, status="online"),
            OnuStatusSample(slot=1, port=1, onu_id=2, status="los"),
        ]
        async with SessionLocal() as db:
            olt = await db.get(Olt, olt_id)
            out = await sync_service.sync_onu_status(db, olt, _StatusDriver(samples))
            await db.commit()
        assert out["changed"] == 1  # hanya ONU 2 berubah status

        async with SessionLocal() as db:
            down = await db.get(Onu, down_id)
            up = await db.get(Onu, up_id)
            history = (await db.execute(select(OnuSignalHistory).where(
                OnuSignalHistory.onu_id == down_id
            ))).scalars().all()

        assert down.status == "los"
        for column in sync_service.OPTICAL_COLUMNS:
            assert getattr(down, column) is None, f"{column} ONU down masih terisi"
        # ONU online tidak disentuh.
        assert up.rx_power_dbm == OPTICAL["rx_power_dbm"] and up.status == "online"
        # Riwayat tetap menyimpan angka terakhir sebelum mati.
        assert len(history) == 1
        assert history[0].rx_power_dbm == OPTICAL["rx_power_dbm"]
        assert history[0].status == "los"
    finally:
        await _cleanup(olt_id, user_id)
        await engine.dispose()


async def test_optical_poll_does_not_revive_values_for_down_onu() -> None:
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    tag = uuid.uuid4().hex[:8]
    olt_id, user_id, up_id, down_id = await _fixture(tag)
    try:
        async with SessionLocal() as db:
            down = await db.get(Onu, down_id)
            down.status = "los"
            await db.commit()

        samples = [
            OpticalSample(slot=1, port=1, onu_id=1, rx_power_dbm=-21.0, tx_power_dbm=2.0,
                          olt_rx_power_dbm=-23.0),
            OpticalSample(slot=1, port=1, onu_id=2, rx_power_dbm=-30.0, tx_power_dbm=2.0,
                          olt_rx_power_dbm=-30.0),
        ]
        async with SessionLocal() as db:
            olt = await db.get(Olt, olt_id)
            out = await sync_service.sync_onu_optical(db, olt, _OpticalDriver(samples))
            await db.commit()
        assert out == {"updated": 1, "skipped_offline": 1}

        async with SessionLocal() as db:
            down = await db.get(Onu, down_id)
            up = await db.get(Onu, up_id)
            hist_down = await db.scalar(select(func.count()).select_from(OnuSignalHistory)
                                        .where(OnuSignalHistory.onu_id == down_id))
        for column in sync_service.OPTICAL_COLUMNS:
            assert getattr(down, column) is None, f"{column} ONU down dihidupkan lagi"
        assert hist_down == 0  # ONU mati tidak menambah sampel palsu ke riwayat
        assert up.rx_power_dbm == -21.0 and up.olt_rx_power_dbm == -23.0
    finally:
        await _cleanup(olt_id, user_id)
        await engine.dispose()
