"""Kelengkapan data setelah OLT baru terhubung: isi kolom ONU yang masih kosong dari
isi NYATA perangkat, tanpa input manual.

BUG NYATA (OLT WNG, C320, 246 ONU, 2026-10-25): `sync_olt_metrics` sukses membaca 246
`name` + 246 `description` ke DB, tapi SEMUA kolom turunannya tetap kosong —
`zone_id` 0/246, `splitter_id` 0/246, `address` 0/246, `download_speed_profile_id` 0/246,
`upload_speed_profile_id` 0/246, `vlan_id` 0/246, `distance_m` 0/246. Sebabnya dua:
  1. `onu_device_metadata.parse_device_description()` sudah benar tapi TIDAK PERNAH
     DIPANGGIL dari mana pun (grep kosong) — jadi zone/alamat/ODP/tanggal otorisasi
     tidak pernah diurai dari `description` yang sudah ada di DB;
  2. profil kecepatan + VLAN per-ONU memang belum punya langkah sinkron sama sekali
     (`fetch_inventory` tidak membacanya). Sekarang dibaca lewat SNMP
     (`driver.fetch_provisioning()`, 7 bulkwalk untuk seluruh OLT) — bukan sesi CLI,
     sesuai preferensi terkunci user.

Idempoten: aman dipanggil berulang. Nilai yang SUDAH terisi tidak pernah ditimpa, jadi
isian manual operator menang (kecuali `distance_m`, murni telemetri perangkat).

Izin pembuatan master data: untuk Zone dan Splitter/ODP, nama yang ditemukan di
`description` dibuat sebagai baris master baru bila belum ada. User BELUM memberi izin
eksplisit untuk ini, jadi default `create_master=True` hanya dipakai pemanggil onboarding
OLT baru; pemanggil lain bisa mengirim `create_master=False` untuk hanya memasangkan ke
master yang sudah ada.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers.base import OltDriver
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.vlan import Vlan
from app.services import master_data_service, speed_profile_service
from app.services.onu_device_metadata import parse_device_description


async def sync_onu_metadata(db: AsyncSession, olt: Olt, driver: OltDriver,
                            *, create_master: bool = True) -> dict:
    """Lengkapi metadata + provisioning semua ONU satu OLT. Commit diserahkan pemanggil.

    Kontrak untuk rantai onboarding: dijalankan SETELAH inventory ONU masuk DB
    (`sync_olt_metrics`), karena bekerja dari kolom `onus.description` yang sudah terisi.
    """
    now = datetime.now(UTC)
    onus = list((await db.execute(
        select(Onu).where(Onu.olt_id == olt.id, Onu.deleted_at.is_(None))
    )).scalars())
    stats = await _metadata_from_description(db, olt, onus, create_master=create_master)
    stats.update(await _provisioning_from_snmp(db, olt, driver, onus, now))
    stats["onus"] = len(onus)
    return stats


async def _metadata_from_description(db: AsyncSession, olt: Olt, onus: list[Onu],
                                     *, create_master: bool) -> dict:
    """zone/alamat/ODP/kontak/extid/tanggal otorisasi dari `onus.description`."""
    structured = free_text = empty = 0
    filled = {"zone": 0, "splitter": 0, "address": 0, "registered_at": 0, "contact": 0,
              "external_id": 0}
    # Cache per nama supaya 246 ONU dengan 3 zone tidak jadi 246 query.
    zones: dict[str, int | None] = {}
    splitters: dict[tuple, int | None] = {}

    for onu in onus:
        meta = parse_device_description(onu.description)
        if not onu.description:
            empty += 1
        elif meta.structured:
            structured += 1
        else:
            free_text += 1

        zone_id = onu.zone_id
        if meta.zone and onu.zone_id is None:
            key = master_data_service.normalize_master_name(meta.zone)
            if key not in zones:
                zone = await master_data_service.get_or_create_zone(
                    db, olt.owner_id, meta.zone, create=create_master
                )
                zones[key] = zone.id if zone else None
            zone_id = zones[key]
            if zone_id is not None:
                onu.zone_id = zone_id
                filled["zone"] += 1

        if meta.splitter and onu.splitter_id is None:
            key = master_data_service.splitter_key(meta.splitter, zone_id)
            if key not in splitters:
                splitter = await master_data_service.get_or_create_splitter(
                    db, meta.splitter, zone_id=zone_id, olt_id=olt.id, create=create_master
                )
                splitters[key] = splitter.id if splitter else None
            if splitters[key] is not None:
                onu.splitter_id = splitters[key]
                filled["splitter"] += 1

        # `descr_` kalau terstruktur; kalau description teks bebas, teks itu sendiri
        # adalah alamat (bentuk yang dipakai sebagian OLT) — bukan zone/ODP karangan.
        address = meta.address or meta.free_text
        if address and not onu.address:
            onu.address = address[:500]
            filled["address"] += 1
        if meta.contact and not onu.contact:
            onu.contact = meta.contact[:100]
            filled["contact"] += 1
        if meta.external_id and not onu.external_id:
            onu.external_id = meta.external_id[:50]
            filled["external_id"] += 1
        # `_authd_` = tanggal otorisasi NYATA dari perangkat. `registered_at` sebelumnya
        # diisi sync_service dengan waktu sync (bukan tanggal otorisasi); kalau perangkat
        # menyebut tanggalnya, nilai itu yang benar.
        if meta.authorized_on is not None:
            authorized = datetime.combine(meta.authorized_on, datetime.min.time(), tzinfo=UTC)
            if onu.registered_at is None or onu.registered_at != authorized:
                onu.registered_at = authorized
                filled["registered_at"] += 1

    return {"description_structured": structured, "description_free_text": free_text,
            "description_empty": empty, **{f"filled_{k}": v for k, v in filled.items()}}


async def _provisioning_from_snmp(db: AsyncSession, olt: Olt, driver: OltDriver,
                                  onus: list[Onu], now: datetime) -> dict:
    """Profil kecepatan per arah, VLAN layanan, dan jarak — semuanya dari SNMP."""
    provisioning = await driver.fetch_provisioning()
    by_position = await _onus_by_position(db, olt.id, onus)
    kbps = {(p.name, p.direction): p.kbps for p in provisioning.profiles}
    vlan_rows = {v.vlan_id: v for v in (await db.execute(
        select(Vlan).where(Vlan.olt_id == olt.id)
    )).scalars()}
    profile_cache: dict[tuple[str, str], int | None] = {}
    filled = {"download": 0, "upload": 0, "vlan": 0, "distance": 0}
    matched = 0

    for item in provisioning.onus:
        onu = by_position.get((item.slot, item.port, item.onu_id))
        if onu is None:
            continue
        matched += 1
        for device_name, direction, column in (
            (item.download_profile, "download", "download_speed_profile_id"),
            (item.upload_profile, "upload", "upload_speed_profile_id"),
        ):
            if not device_name or getattr(onu, column) is not None:
                continue
            key = (device_name, direction)
            if key not in profile_cache:
                profile = await speed_profile_service.get_or_create_from_device(
                    db, olt.id, device_name, direction, kbps.get(key)
                )
                profile_cache[key] = profile.id if profile else None
            if profile_cache[key] is not None:
                setattr(onu, column, profile_cache[key])
                filled[direction] += 1
                # Nama profile di device dipakai lagi saat push/modify; simpan apa adanya.
                if direction == "download" and not onu.line_profile_id:
                    onu.line_profile_id = device_name[:50]
                if direction == "upload" and not onu.srv_profile_id:
                    onu.srv_profile_id = device_name[:50]

        if onu.vlan_id is None:
            vlan = _primary_vlan(item.vlan_ids, vlan_rows)
            if vlan is not None:
                onu.vlan_id = vlan.id
                filled["vlan"] += 1
        if item.distance_m is not None:
            onu.distance_m = item.distance_m
            filled["distance"] += 1
        onu.last_sync_at = now

    return {"provisioning_rows": len(provisioning.onus), "provisioning_matched": matched,
            "device_profiles": len(provisioning.profiles),
            **{f"filled_{k}": v for k, v in filled.items()}}


def _primary_vlan(vlan_ids: list[int], master: dict[int, Vlan]) -> Vlan | None:
    """VLAN layanan utama ONU = VLAN pertama yang BUKAN management.

    Aturan terkunci user: VLAN dari service-port, kecuali yang ditandai management di
    master (`vlans.type`). Tidak ada nomor yang di-hardcode sebagai management, dan VLAN
    yang belum ada di master tidak dipaksa dibuat di sini (itu tugas inventory).
    Semua VLAN ONU bertanda management -> None (jujur kosong).
    """
    for vlan_id in vlan_ids:
        row = master.get(vlan_id)
        if row is not None and row.type != "management":
            return row
    return None


async def _onus_by_position(db: AsyncSession, olt_id: int,
                            onus: list[Onu]) -> dict[tuple[int, int, int], Onu]:
    """(slot, port, onu_index) -> baris ONU, tanpa query ulang baris ONU-nya."""
    ports = {pon_id: (slot, port) for pon_id, slot, port in (await db.execute(
        select(PonPort.id, PonPort.slot, PonPort.port).where(PonPort.olt_id == olt_id)
    ))}
    result: dict[tuple[int, int, int], Onu] = {}
    for onu in onus:
        position = ports.get(onu.pon_port_id)
        if position is not None and onu.onu_index is not None:
            result[(position[0], position[1], onu.onu_index)] = onu
    return result
