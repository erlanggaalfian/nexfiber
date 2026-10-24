"""Periodic OLT -> DB sync (PRD 4.4), called by the worker. Each function takes an open
session + built driver, does the work, and leaves committing to the caller.
"""

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers.base import OltDriver
from app.models.olt import Olt, OltConfigBackup, PonPort
from app.models.onu import Onu, OnuSignalHistory
from app.models.unconfigured_onu import UnconfiguredOnu


async def _onus_by_position(db: AsyncSession, olt_id: int) -> dict[tuple[int, int, int], Onu]:
    rows = await db.execute(
        select(PonPort.slot, PonPort.port, Onu)
        .join(Onu, Onu.pon_port_id == PonPort.id)
        .where(Onu.olt_id == olt_id, Onu.deleted_at.is_(None))
    )
    return {(slot, port, onu.onu_index): onu for slot, port, onu in rows}

async def _pon_ports_by_position(db: AsyncSession, olt_id: int) -> dict[tuple[int, int], int]:
    rows = await db.execute(
        select(PonPort.slot, PonPort.port, PonPort.id).where(PonPort.olt_id == olt_id)
    )
    return {(slot, port): pon_id for slot, port, pon_id in rows}

async def _upsert_pon_ports(
    db: AsyncSession, olt_id: int, ports: dict[tuple[int, int], int | None], now: datetime
) -> None:
    """Auto-register PON ports seen on the OLT; never deletes (user decision)."""
    if not ports:
        return
    stmt = insert(PonPort).values([
        {"olt_id": olt_id, "slot": slot, "port": port, "ifindex": ifindex, "last_sync_at": now}
        for (slot, port), ifindex in sorted(ports.items())
    ])
    await db.execute(stmt.on_conflict_do_update(
        constraint="uq_ponport_olt_slot_port",
        set_={"ifindex": func.coalesce(stmt.excluded.ifindex, PonPort.ifindex),
              "last_sync_at": now},
    ))

def _mark_olt_ok(olt: Olt, now: datetime) -> None:
    olt.status = "online"
    olt.last_sync_at = now
    olt.last_error = None

async def sync_onu_status(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """Write only on status change (PRD 4.4); unchanged online ONUs get one bulk
    last_seen_at touch instead of a per-row UPDATE every minute.
    """
    now = datetime.now(UTC)
    samples = await driver.fetch_onu_status()
    known = await _pon_ports_by_position(db, olt.id)
    missing = {(s.slot, s.port): None for s in samples if (s.slot, s.port) not in known}
    await _upsert_pon_ports(db, olt.id, missing, now)
    onus = await _onus_by_position(db, olt.id)
    changed, still_online = 0, []
    for sample in samples:
        onu = onus.get((sample.slot, sample.port, sample.onu_id))
        if onu is None:
            continue
        if onu.status == sample.status:
            if sample.status == "online":
                still_online.append(onu.id)
            continue
        if onu.status == "online":
            onu.last_down_at = now
            onu.last_down_reason = sample.status
        if sample.status == "online":
            onu.last_seen_at = now
        onu.status = sample.status
        db.add(OnuSignalHistory(
            onu_id=onu.id, status=sample.status, sampled_at=now,
            rx_power_dbm=onu.rx_power_dbm, olt_rx_power_dbm=onu.olt_rx_power_dbm,
        ))
        changed += 1
    if still_online:
        await db.execute(update(Onu).where(Onu.id.in_(still_online)).values(last_seen_at=now))
    _mark_olt_ok(olt, now)
    return {"changed": changed, "unchanged_online": len(still_online)}

async def sync_onu_optical(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    now = datetime.now(UTC)
    onus = await _onus_by_position(db, olt.id)
    updated = 0
    for sample in await driver.fetch_optical(None, None):
        onu = onus.get((sample.slot, sample.port, sample.onu_id))
        if onu is None:
            continue
        onu.rx_power_dbm = sample.rx_power_dbm
        onu.tx_power_dbm = sample.tx_power_dbm
        onu.olt_rx_power_dbm = sample.olt_rx_power_dbm
        onu.last_sync_at = now
        db.add(OnuSignalHistory(onu_id=onu.id, status=onu.status, sampled_at=now,
                                rx_power_dbm=sample.rx_power_dbm, tx_power_dbm=sample.tx_power_dbm,
                                olt_rx_power_dbm=sample.olt_rx_power_dbm))
        updated += 1
    _mark_olt_ok(olt, now)
    return {"updated": updated}

async def sync_olt_metrics(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """Optical ONU + kesehatan OLT dalam SATU job per OLT (DECISIONS "Job & scheduling":
    gabung ke job optical, jangan bikin sync_olt_health terpisah) — satu siklus koneksi ke
    OLT tiap 15 menit, bukan dua.
    """
    optical = await sync_onu_optical(db, olt, driver)
    now = datetime.now(UTC)
    health = await driver.fetch_health()
    olt.cpu_pct = health.cpu_pct
    olt.ram_pct = health.ram_pct
    olt.temperature_c = health.temperature_c
    olt.uptime_seconds = health.uptime_seconds
    olt.software_version = health.software_version
    olt.cards = [asdict(card) for card in health.cards]
    olt.uplink_ports = health.uplink_ports
    await _upsert_pon_ports(
        db, olt.id, {(p.slot, p.port): p.ifindex for p in await driver.list_pon_ports()}, now
    )
    _mark_olt_ok(olt, now)
    return {**optical, "cards": len(health.cards), "uplink_ports": health.uplink_ports}

async def sync_unconfigured(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """UPSERT what the scan saw, then drop rows it didn't. Only reached when the scan
    succeeded — a driver exception skips this, so a failed scan never wipes old data.
    """
    now = datetime.now(UTC)
    found = await driver.list_unconfigured()
    ports: dict[tuple[int, int], int | None] = {(i.slot, i.port): None for i in found}
    ports.update({(p.slot, p.port): p.ifindex for p in await driver.list_pon_ports()})
    await _upsert_pon_ports(db, olt.id, ports, now)
    pon_ports = await _pon_ports_by_position(db, olt.id)
    seen, skipped = [], 0
    for item in found:
        pon_port_id = pon_ports.get((item.slot, item.port))
        if pon_port_id is None:
            skipped += 1  # PON port not registered in DB yet
            continue
        stmt = insert(UnconfiguredOnu).values(
            olt_id=olt.id, pon_port_id=pon_port_id, serial_number=item.serial_number,
            onu_type=item.onu_type, first_seen_at=now, last_seen_at=now,
        )
        await db.execute(stmt.on_conflict_do_update(
            constraint="uq_unconfigured_olt_serial",
            set_={"pon_port_id": pon_port_id, "onu_type": item.onu_type, "last_seen_at": now},
        ))
        seen.append(item.serial_number)
    await db.execute(
        delete(UnconfiguredOnu).where(UnconfiguredOnu.olt_id == olt.id,
                                      UnconfiguredOnu.serial_number.not_in(seen))
    )
    _mark_olt_ok(olt, now)
    return {"found": len(seen), "skipped_unknown_port": skipped}

async def backup_olt_config(
    db: AsyncSession, olt: Olt, driver: OltDriver, triggered_by: str
) -> dict:
    now = datetime.now(UTC)
    config = await driver.backup_config()
    data = config.encode()
    backup = OltConfigBackup(
        olt_id=olt.id, config_text=config, checksum=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data), taken_at=now, triggered_by=triggered_by,
    )
    db.add(backup)
    await db.flush()
    _mark_olt_ok(olt, now)
    return {"backup_id": backup.id, "size_bytes": backup.size_bytes}
