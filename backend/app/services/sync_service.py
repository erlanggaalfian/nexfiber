"""Periodic OLT -> DB sync (PRD 4.4), called by the worker. Each function takes an open
session + built driver, does the work, and leaves committing to the caller.
"""

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_secret
from app.drivers.base import OltDriver
from app.drivers.onu_report import wan_vlan_not_management
from app.models.olt import Olt, OltConfigBackup, PonPort
from app.models.onu import Onu, OnuSignalHistory
from app.models.unconfigured_onu import UnconfiguredOnu
from app.models.vlan import Vlan
from app.services import onboarding_sync


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


async def _refresh_pon_oper_states(db: AsyncSession, olt: Olt, driver: OltDriver) -> int:
    """Tulis PonPort.oper_state dari SNMP ifOperStatus (driver ZTE).

    Dipanggil lewat getattr karena metodenya belum ada di interface OltDriver
    (types.py di luar kepemilikan Area 2): driver/fake yang tidak menyediakannya
    dilewati diam-diam. Dict kosong (SNMP gagal) membiarkan nilai lama, bukan
    menimpa dengan None — itu yang membuat semua port tampil offline selama ini.
    """
    fetch = getattr(driver, "fetch_pon_oper_states", None)
    if fetch is None:
        return 0
    states = await fetch()
    written = 0
    for (slot, port), state in sorted(states.items()):
        result = await db.execute(
            update(PonPort).where(PonPort.olt_id == olt.id, PonPort.slot == slot,
                                  PonPort.port == port).values(oper_state=state)
        )
        written += result.rowcount or 0
    return written

OPTICAL_COLUMNS = ("rx_power_dbm", "tx_power_dbm", "olt_rx_power_dbm",
                   "temperature_c", "voltage_v", "bias_current_ma")

def _clear_optical(onu: Onu) -> None:
    """ONU mati tidak punya nilai optik. Angka terakhir hanya boleh hidup di riwayat
    (onu_signal_history); dibiarkan di baris ONU, UI menampilkan Rx -30 dBm palsu
    untuk ONU yang sudah lama down."""
    for column in OPTICAL_COLUMNS:
        setattr(onu, column, None)

async def sync_onu_status(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """Write only on status change (PRD 4.4); unchanged online ONUs get one bulk
    last_seen_at touch instead of a per-row UPDATE every minute.
    """
    now = datetime.now(UTC)
    samples = await driver.fetch_onu_status()
    known = await _pon_ports_by_position(db, olt.id)
    missing = {(s.slot, s.port): None for s in samples if (s.slot, s.port) not in known}
    await _upsert_pon_ports(db, olt.id, missing, now)
    pon_oper_written = await _refresh_pon_oper_states(db, olt, driver)
    onus = await _onus_by_position(db, olt.id)
    changed, still_online = 0, []
    # Urut posisi: dua proses menulis baris dalam urutan sama -> tidak ada deadlock.
    for sample in sorted(samples, key=lambda s: (s.slot, s.port, s.onu_id)):
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
            source="status_change",
        ))
        # Riwayat sudah menyimpan angka terakhir di atas; baris ONU-nya dikosongkan
        # supaya ONU yang tidak online tidak lagi menampilkan Rx/Tx lama.
        if sample.status != "online":
            _clear_optical(onu)
        changed += 1
    if still_online:
        await db.execute(update(Onu).where(Onu.id.in_(still_online)).values(last_seen_at=now))
    absent_marked = 0
    if samples:
        # ONU yang hilang dari sampel perangkat tidak boleh tetap "online" di DB:
        # barisnya TIDAK dihapus, statusnya jadi offline dengan alasan hilang dari
        # tabel phase perangkat. Hanya ONU yang tadinya online yang ditandai —
        # ONU yang sudah offline/los mempertahankan status spesifiknya, dan walk
        # kosong (gagal baca sesaat) TIDAK menandai apa pun, supaya satu SNMP
        # gagal tidak mematikan seluruh OLT di UI.
        seen_keys = {(s.slot, s.port, s.onu_id) for s in samples}
        for (slot, port, onu_id), onu in sorted(onus.items()):
            if (slot, port, onu_id) in seen_keys or onu.status != "online":
                continue
            # Riwayat dulu (menyimpan angka terakhir), baru kosongkan kolom ONU.
            db.add(OnuSignalHistory(
                onu_id=onu.id, status="offline", sampled_at=now,
                rx_power_dbm=onu.rx_power_dbm, olt_rx_power_dbm=onu.olt_rx_power_dbm,
                source="status_change",
            ))
            onu.status = "offline"
            onu.last_down_at = now
            onu.last_down_reason = "absent_from_device_sample"
            _clear_optical(onu)
            absent_marked += 1
        _mark_olt_ok(olt, now)
    return {"changed": changed, "unchanged_online": len(still_online),
            "absent_marked_offline": absent_marked,
            "absent_skipped_empty_sample": not samples,
            "pon_oper_written": pon_oper_written}

async def sync_onu_optical(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """ONU yang tidak online dilewati (nilai optiknya dikosongkan): polling 15 menit
    tidak boleh menghidupkan lagi Rx/Tx lama untuk ONU yang sudah down."""
    now = datetime.now(UTC)
    onus = await _onus_by_position(db, olt.id)
    updated = skipped_offline = 0
    optical_samples = await driver.fetch_optical(None, None)
    for sample in sorted(optical_samples,
                         key=lambda s: (s.slot, s.port, s.onu_id)):
        onu = onus.get((sample.slot, sample.port, sample.onu_id))
        if onu is None:
            continue
        if onu.status != "online":
            _clear_optical(onu)
            onu.last_sync_at = now
            skipped_offline += 1
            continue
        # Guard None per kolom (sama seperti guard health): satu sampel dengan
        # field None tidak boleh menimpa nilai baik sebelumnya dengan kosong.
        # Sebelumnya semua kolom ditulis apa adanya, termasuk None.
        for column, value in (
            ("rx_power_dbm", sample.rx_power_dbm),
            ("tx_power_dbm", sample.tx_power_dbm),
            ("olt_rx_power_dbm", sample.olt_rx_power_dbm),
            ("temperature_c", sample.temperature_c),
            ("voltage_v", sample.voltage_v),
            ("bias_current_ma", sample.bias_current_ma),
        ):
            if value is not None:
                setattr(onu, column, value)
        onu.last_sync_at = now
        if any(v is not None for v in (sample.rx_power_dbm, sample.tx_power_dbm,
                                       sample.olt_rx_power_dbm)):
            db.add(OnuSignalHistory(onu_id=onu.id, status=onu.status, sampled_at=now,
                                    rx_power_dbm=sample.rx_power_dbm,
                                    tx_power_dbm=sample.tx_power_dbm,
                                    olt_rx_power_dbm=sample.olt_rx_power_dbm,
                                    source="optical"))
        updated += 1
    # SNMP-only sync tidak boleh menghidupkan status OLT dari walk kosong: walk
    # kosong = tidak ada bukti perangkat terbaca, jadi status dibiarkan apa adanya
    # (bukan "online"). Bila ada sampel, pembacaan SNMP berhasil -> tandai ok.
    # Batasan yang tersisa: sukses SNMP saja tetap menandai online walau CLI mati;
    # status "online" di sini berarti "terjangkau lewat SNMP", bukan "CLI sehat" —
    # kesehatan CLI hanya dibuktikan job test_connection / aksi CLI.
    if optical_samples:
        _mark_olt_ok(olt, now)
    return {"updated": updated, "skipped_offline": skipped_offline,
            "olt_marked_ok": bool(optical_samples)}

def _clip(value: str | None, limit: int) -> str | None:
    """Teks bebas dari perangkat bisa lebih panjang dari kolomnya; potong, jangan gagalkan
    seluruh job sync karena satu description panjang."""
    if value is None:
        return None
    value = value.strip()
    return value[:limit] or None

async def _adopt_inventory(db: AsyncSession, olt: Olt, driver: OltDriver, now: datetime) -> dict:
    """Adopsi isi NYATA OLT ke DB dari pembacaan read-only (PRD 3.1 poin 7: ONU existing
    masuk lewat discovery, metadata pelanggan diisi manual kemudian).

    BUG NYATA (OLT SBI, 2026-10-24): `fetch_inventory()` punya handler/driver tapi TIDAK
    PERNAH dipanggil job apa pun, jadi 39 ONU terdaftar dan 6 VLAN di perangkat tidak
    pernah masuk DB; Detail OLT selalu "Belum ada ...". sync_onu_status hanya meng-update
    baris yang sudah ada, tidak pernah membuat.

    Metadata yang ADA di perangkat cuma dua baris teks bebas per interface ONU:
    `name` dan `description` (39/39 ONU di OLT SBI punya keduanya). Keduanya diisi ke
    kolom `onus.name` / `onus.description` HANYA kalau kolomnya masih kosong — isian
    operator tidak pernah ditimpa. Nama pelanggan tetap dirender dari
    `customer_name ?? name`, jadi label perangkat langsung terlihat tanpa mengarang.

    TIDAK ADA di perangkat: zone dan splitter/ODP. ZTE C300/C320 tidak punya field untuk
    itu dan `description` di OLT ini bukan format terstruktur (35/39 teks alamat bebas,
    hanya 3 memuat token `zone_`, 0 memuat ODB/ODP). Karena itu `zone_id`/`splitter_id`
    DIBIARKAN NULL — relasinya harus dibuat operator lewat Detail ONU > Pelanggan > Ubah,
    bukan ditebak dari teks.

    Aman untuk dua proses menulis bersamaan: baris ONU baru dibuat dengan
    `INSERT ... ON CONFLICT DO NOTHING` pada unique (olt_id, serial_number) — kalau proses
    lain sudah membuatnya, kita lewati (siklus berikutnya yang meng-update), tidak ada
    baris ganda dan tidak ada job yang gagal karena IntegrityError. Urutan iterasi
    diurutkan serial supaya dua proses mengunci baris dalam urutan sama (anti-deadlock).

    Hanya INSERT/UPDATE: tidak ada delete ONU/VLAN supaya data pelanggan aman kalau suatu
    saat perangkat membalas sebagian.
    """
    inv = await driver.fetch_inventory()
    await _upsert_pon_ports(db, olt.id, {(s.slot, s.port): None for s in inv.onus}, now)
    pon_ports = await _pon_ports_by_position(db, olt.id)
    existing = {onu.serial_number: onu for onu in (await db.execute(
        select(Onu).where(Onu.olt_id == olt.id, Onu.deleted_at.is_(None))
    )).scalars()}
    management_vlans = {}
    if any(s.management_ips is not None for s in inv.onus):
        for vlan in (await db.execute(select(Vlan).where(
            Vlan.type == "management", or_(Vlan.olt_id == olt.id, Vlan.olt_id.is_(None))
        ).order_by(Vlan.olt_id.nulls_first()))).scalars():
            management_vlans[vlan.vlan_id] = vlan
    added = updated = skipped = 0
    with_name = with_descr = with_pppoe = with_wan_vlan = with_management = 0
    for snap in sorted(inv.onus, key=lambda s: s.serial_number):
        if snap.name:
            with_name += 1
        if snap.description:
            with_descr += 1
        pon_port_id = pon_ports.get((snap.slot, snap.port))
        if pon_port_id is None:
            skipped += 1
            continue
        # Hanya kandidat VLAN management (aturan keras: chip "Mgmt IP" tidak boleh pernah
        # menampilkan IP di luar VLAN management). Pilih deterministik: kandidat pertama
        # yang membawa IP, urutan seperti dilaporkan perangkat; tanpa kandidat ber-IP,
        # mode kandidat pertama tetap dipakai dan kolom IP dibiarkan apa adanya.
        management = [row for row in snap.management_ips or [] if row[0] in management_vlans]
        mgmt = next((row for row in management if row[2]), management[0] if management else None)
        # Kebalikannya: IP WAN = kandidat PERTAMA di luar VLAN management yang membawa IP
        # (aturan keras: `ip_address` dan `wan_ip_address` tidak pernah saling mewakili).
        # Master tanpa VLAN management = tidak ada dasar memastikan "non-management" -> None.
        wan_ip = next((row[2] for row in snap.management_ips or []
                       if row[0] not in management_vlans and row[2]), None) \
            if management_vlans else None
        if mgmt:
            with_management += 1
        onu = existing.get(snap.serial_number)
        if onu is None:
            # Bentrok posisi PON yang dipakai ulang: serial baru menempati posisi
            # yang masih diklaim baris DB lain (serial lama) — DO NOTHING diam-diam
            # akan membuat ONU baru ini tidak pernah teradopsi. Baris lama yang
            # sudah tidak ada di perangkat ditandai offline + posisinya dilepas
            # (onu_index=None) supaya INSERT baru bisa jalan; kalau baris lama
            # ternyata masih ada di perangkat (konflik nyata), lewati dengan
            # alasan, bukan diam.
            position_owner = next(
                (o for o in existing.values()
                 if o.pon_port_id == pon_port_id and o.onu_index == snap.onu_id), None)
            if position_owner is not None:
                if any(s.serial_number == position_owner.serial_number for s in inv.onus):
                    skipped += 1
                    continue
                position_owner.status = "offline"
                position_owner.last_down_at = now
                position_owner.last_down_reason = "position_reused_by_new_serial"
                position_owner.onu_index = None
                _clear_optical(position_owner)
            stmt = insert(Onu).values(
                olt_id=olt.id, pon_port_id=pon_port_id, onu_index=snap.onu_id,
                serial_number=snap.serial_number, auth_type="sn", onu_type=snap.onu_type,
                name=_clip(snap.name, 100), description=_clip(snap.description, 128),
                status=snap.status, config_state="success",
                admin_state=snap.admin_state or "enabled",
                mgmt_ip_mode=mgmt[1] if mgmt else None,
                ip_address=mgmt[2] if mgmt else None,
                wan_ip_address=wan_ip,
                last_seen_at=now if snap.status == "online" else None,
                last_sync_at=now, registered_at=now,
            )
            # Serial per OLT masih DO NOTHING (balapan antar proses adopsi yang
            # sama); posisi sudah dibersihkan di atas, jadi DO NOTHING di sini
            # hanya menutupi balapan persis, bukan konflik posisi yang dibiarkan.
            res = await db.execute(stmt.on_conflict_do_nothing())
            added += res.rowcount or 0
            continue
        onu.pon_port_id, onu.onu_index = pon_port_id, snap.onu_id
        onu.status, onu.last_sync_at = snap.status, now
        onu.onu_type = onu.onu_type or snap.onu_type
        # Isian operator menang: hanya tulis kalau kolomnya masih kosong.
        onu.name = onu.name or _clip(snap.name, 100)
        onu.description = onu.description or _clip(snap.description, 128)
        if snap.admin_state:
            onu.admin_state = snap.admin_state
        if snap.pppoe_username:
            # Perangkat = sumber kebenaran WAN: PPPoE di running-config menimpa kolom DB.
            onu.wan_mode, onu.onu_mode = "pppoe", "routing"
            onu.pppoe_username = snap.pppoe_username[:100]
            if snap.pppoe_password:
                onu.pppoe_password_enc = encrypt_secret(snap.pppoe_password)
            with_pppoe += 1
        if snap.wan_vlan is not None:
            # Sama alasannya: VLAN WAN di `flow 1` perangkat menimpa kolom DB.
            # Aturan: WAN = VLAN yang BUKAN ditandai management.
            onu.wan_vlan = wan_vlan_not_management(
                snap.wan_vlan, snap.management_ips, set(management_vlans))
            with_wan_vlan += 1
        if mgmt:
            # Perangkat + master VLAN = sumber kebenaran management; timpa hasil aksi manual.
            # `onus.vlan_id` TIDAK disentuh: itu VLAN utama (kolom "Update VLAN"), bukan
            # milik management. Nomor VLAN management tampil dari `service_vlans`
            # (is_management) di detail, lihat `OnuDetail.mgmt_vlan`.
            onu.mgmt_ip_mode = mgmt[1]
            if mgmt[2]:  # tanpa IP dilaporkan -> dibiarkan apa adanya, tidak dikosongkan
                onu.ip_address = mgmt[2]
        if wan_ip:
            # IP non-management hanya masuk kolom WAN; tanpa kandidat kolom tidak disentuh.
            onu.wan_ip_address = wan_ip
        # TIDAK ADA pengosongan di sini (temuan 15, diputuskan setelah tes gagal):
        # snapshot perangkat tidak cukup setia untuk membuktikan penghapusan —
        # parse_management_ip mengembalikan None untuk seluruh stanza bila satu
        # baris ambigu, dan kolom-kolom ini juga menampung isian operator. Tes
        # yang ada ("tanpa kandidat: kolom tidak disentuh, tidak dikosongkan")
        # mengunci keputusan itu. Pengosongan yang aman butuh penanda per-field
        # (mis. "stanza perangkat terbaca penuh + field ini memang tidak ada") di
        # level snapshot/driver, bukan di adopsi — itu pekerjaan lanjutan, bukan
        # pengosongan diam-diam yang menghapus data operator.
        if snap.status == "online":
            onu.last_seen_at = now
        updated += 1
    vlans_added = 0
    for vid in inv.vlan_ids:
        stmt = insert(Vlan).values(olt_id=olt.id, vlan_id=vid, name=f"VLAN{vid}")
        # on_conflict_do_nothing: nama/tipe yang sudah diisi operator tidak ditimpa.
        res = await db.execute(stmt.on_conflict_do_nothing(constraint="uq_vlan_olt_vlanid"))
        vlans_added += res.rowcount or 0
    return {"onus_added": added, "onus_updated": updated,
            "onus_skipped_unknown_port": skipped, "vlans_added": vlans_added,
            "vlans_on_device": len(inv.vlan_ids),
            # Bukti seberapa banyak metadata yang MEMANG dibaca dari perangkat (bukan tebakan).
            "onus_with_device_name": with_name, "onus_with_device_description": with_descr,
            "onus_with_pppoe": with_pppoe, "onus_with_wan_vlan": with_wan_vlan,
            "onus_with_management_ip": with_management}

async def sync_olt_metrics(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """Optical ONU + kesehatan OLT + adopsi inventory dalam SATU job per OLT
    (DECISIONS "Job & scheduling": gabung ke job optical, jangan bikin job terpisah) —
    satu siklus koneksi ke OLT tiap 15 menit.
    """
    inventory = await _adopt_inventory(db, olt, driver, datetime.now(UTC))
    optical = await sync_onu_optical(db, olt, driver)
    # Provisioning per-ONU (VLAN layanan, profil kecepatan, jarak) — SNMP, 7 bulkwalk untuk
    # seluruh OLT. Tanpa langkah ini `onus.service_vlan_ids` tidak pernah terisi dan modal
    # "Update attached VLANs" selalu terbuka tanpa centang: `sync_onu_metadata` sudah ada
    # dan sudah diuji, tapi TIDAK PERNAH dipanggil dari job manapun (grep kosong).
    # `create_master=False`: job berkala tidak boleh membuat baris Zone/Splitter baru —
    # izin itu khusus onboarding OLT baru (DECISIONS).
    metadata = await onboarding_sync.sync_onu_metadata(db, olt, driver, create_master=False)
    now = datetime.now(UTC)
    health = await driver.fetch_health()
    # Jangan timpa data baik dengan None/[] saat SNMP gagal sesaat: fetch_health
    # mengembalikan None/[] bila walk gagal, dan nilai lama lebih berguna daripada
    # kosong. Hanya nilai yang benar-benar ada yang ditulis.
    if health.cpu_pct is not None:
        olt.cpu_pct = health.cpu_pct
    if health.ram_pct is not None:
        olt.ram_pct = health.ram_pct
    if health.temperature_c is not None:
        olt.temperature_c = health.temperature_c
    if health.uptime_seconds is not None:
        olt.uptime_seconds = health.uptime_seconds
    if health.software_version is not None:
        olt.software_version = health.software_version
    if health.sys_name is not None:
        olt.sys_name = health.sys_name
    if health.sys_location is not None:
        olt.sys_location = health.sys_location
    if health.cards:
        olt.cards = [asdict(card) for card in health.cards]
    if health.uplink_ports:
        olt.uplink_ports = health.uplink_ports
    await _upsert_pon_ports(
        db, olt.id, {(p.slot, p.port): p.ifindex for p in await driver.list_pon_ports()}, now
    )
    pon_oper_written = await _refresh_pon_oper_states(db, olt, driver)
    # _mark_olt_ok hanya bila minimal satu pembacaan mengembalikan data:
    # sebelumnya selalu ditandai online di akhir job ini, bahkan bila semua
    # pembacaan (optik, inventory, health) gagal/kosong — OLT yang tidak
    # terjangkau tampil online karena job-nya "selesai".
    has_data = bool(optical.get("olt_marked_ok")) or any(
        v is not None for v in (health.cpu_pct, health.ram_pct, health.temperature_c,
                                health.uptime_seconds, health.software_version,
                                health.sys_name, health.sys_location)
    ) or bool(health.cards) or bool(health.uplink_ports) \
        or bool(inventory.get("onus_added")) or bool(inventory.get("onus_updated"))
    if has_data:
        _mark_olt_ok(olt, now)
    return {**optical, **inventory, **metadata,
            "cards": len(health.cards), "uplink_ports": health.uplink_ports,
            "pon_oper_written": pon_oper_written, "olt_marked_ok": has_data}

async def sync_unconfigured(db: AsyncSession, olt: Olt, driver: OltDriver) -> dict:
    """UPSERT what the scan saw, then drop rows it didn't. Only reached when the scan
    succeeded — a driver exception skips this, so a failed scan never wipes old data.

    Tambahan: scan KOSONG tidak lagi menghapus semua pending. Scan kosong yang valid
    (OLT memang tidak punya ONU unconfigured) hanya terjadi bila daftar PON
    perangkat terbaca (list_pon_ports non-kosong) — bila PON pun tidak terbaca,
    hasil scan tidak bisa dipercaya dan penghapusan dilewati. Ini membedakan
    "kosong yang valid" dari "output error yang kebetulan kosong".
    """
    now = datetime.now(UTC)
    found = await driver.list_unconfigured()
    pon_ports_for_check = await driver.list_pon_ports()
    if not found and not pon_ports_for_check:
        # Tidak ada bukti perangkat benar-benar terbaca: jangan hapus pending lama,
        # dan jangan tandai OLT online dari hasil yang meragukan ini.
        return {"found": 0, "skipped_unknown_port": 0, "wipe_skipped_empty_untrusted": True}
    ports: dict[tuple[int, int], int | None] = {(i.slot, i.port): None for i in found}
    ports.update({(p.slot, p.port): p.ifindex for p in pon_ports_for_check})
    await _upsert_pon_ports(db, olt.id, ports, now)
    pon_ports = await _pon_ports_by_position(db, olt.id)
    seen, skipped = [], 0
    for item in sorted(found, key=lambda i: i.serial_number):
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
    # Anti-join: pending yang serialnya sudah terdaftar (mis. muncul lagi di scan
    # setelah restore-factory) dihapus dari pending walau masih terlihat di scan,
    # supaya Unconfigured tidak menawarkan authorize yang pasti ditolak.
    await db.execute(
        delete(UnconfiguredOnu).where(
            UnconfiguredOnu.olt_id == olt.id,
            UnconfiguredOnu.serial_number.in_(
                select(Onu.serial_number).where(
                    Onu.olt_id == olt.id, Onu.deleted_at.is_(None))),
        )
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
