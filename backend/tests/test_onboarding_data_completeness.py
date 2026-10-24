"""Kelengkapan data sinkron OLT baru: parse SNMP provisioning + pengisian kolom ONU.

Semua pakai SNMP palsu / DB palsu — TIDAK pernah menyentuh perangkat nyata.
Nilai OID dan bentuk indexnya diambil dari hasil walk baca-saja OLT WNG (C320) dan
sudah disilang dengan `show running-config interface gpon-onu_...`.
"""

from datetime import UTC, datetime

import pytest

from app.drivers.zte_c320 import (
    OID_ONU_DISTANCE,
    OID_ONU_GEMPORT_DOWN_PROFILE_REF,
    OID_ONU_SERVICE_PORT_VLAN,
    OID_ONU_TCONT_PROFILE_REF,
    OID_TCONT_PROFILE_MAX_KBPS,
    OID_TCONT_PROFILE_NAME,
    OID_TRAFFIC_PROFILE_NAME,
    OID_TRAFFIC_PROFILE_PIR_KBPS,
    ZteC320Driver,
    decode_service_port_vlan,
    pick_profile,
)
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.speed_profile import SpeedProfile
from app.models.splitter import Splitter
from app.models.vlan import Vlan
from app.models.zone import Zone
from app.services import master_data_service, onboarding_sync, speed_profile_service

# --- dekoder murni ----------------------------------------------------------


def test_decode_service_port_vlan_masks_device_flag_bits():
    # 16484 = 0x4064; CLI membuktikan service-port itu `vlan 100` (185 ONU di WNG).
    assert decode_service_port_vlan(16484) == 100
    assert decode_service_port_vlan(15) == 15
    assert decode_service_port_vlan(2661) == 2661
    # 4095 setelah masking = reserved, 0 = tidak ada VLAN -> jujur kosong, bukan ditebak.
    assert decode_service_port_vlan(0) is None
    assert decode_service_port_vlan(4096) is None
    assert decode_service_port_vlan("bukan angka") is None


def test_pick_profile_takes_lowest_tcont_not_voip_management():
    # ONU 1/2/1:3 nyata: tcont 1 = paket pelanggan, tcont 2 = VoIP/manajemen.
    assert pick_profile({"2": "SMARTOLT-VOIPMNG-10M", "1": "SMARTOLT-HFA_Lite-UP"}) \
        == "SMARTOLT-HFA_Lite-UP"
    assert pick_profile({"1": None, "2": "SMARTOLT-VOIPMNG-10M"}) == "SMARTOLT-VOIPMNG-10M"
    assert pick_profile({}) is None


def test_strip_device_suffix_pairs_up_and_down_into_one_name():
    strip = speed_profile_service.strip_device_suffix
    assert strip("SMARTOLT-HFA_Lite-UP", "upload") == "SMARTOLT-HFA_Lite"
    assert strip("SMARTOLT-HFA_Lite-DOWN", "download") == "SMARTOLT-HFA_Lite"
    assert strip("PAKET20_DN", "download") == "PAKET20"
    # Profil tanpa suffix dipakai apa adanya, bukan dipotong sembarangan.
    assert strip("SMARTOLT-VOIPMNG-10M", "upload") == "SMARTOLT-VOIPMNG-10M"


# --- driver: fetch_provisioning dari tabel SNMP ------------------------------

PON_IFINDEX = 268566784  # gpon-olt_1/2/1
OPTICAL_IFINDEX = 285278721  # skema index kedua untuk slot/port yang sama

SNMP_ROWS = {
    OID_TCONT_PROFILE_NAME: [
        (f"{OID_TCONT_PROFILE_NAME}.1879048193", "default"),
        (f"{OID_TCONT_PROFILE_NAME}.1879048204", "SMARTOLT-HFA_Lite-UP"),
        (f"{OID_TCONT_PROFILE_NAME}.1879048195", "SMARTOLT-VOIPMNG-10M"),
    ],
    OID_TCONT_PROFILE_MAX_KBPS: [
        (f"{OID_TCONT_PROFILE_MAX_KBPS}.1879048193", 0),
        (f"{OID_TCONT_PROFILE_MAX_KBPS}.1879048204", 10240),
        (f"{OID_TCONT_PROFILE_MAX_KBPS}.1879048195", 11264),
    ],
    OID_TRAFFIC_PROFILE_NAME: [
        (f"{OID_TRAFFIC_PROFILE_NAME}.1879048204", "SMARTOLT-HFA_Lite-DOWN"),
    ],
    OID_TRAFFIC_PROFILE_PIR_KBPS: [
        (f"{OID_TRAFFIC_PROFILE_PIR_KBPS}.1879048204", 20480),
    ],
    OID_ONU_TCONT_PROFILE_REF: [
        # ONU :3 punya dua tcont -> yang dipakai tcont 1.
        (f"{OID_ONU_TCONT_PROFILE_REF}.{PON_IFINDEX}.3.1", 1879048204),
        (f"{OID_ONU_TCONT_PROFILE_REF}.{PON_IFINDEX}.3.2", 1879048195),
    ],
    OID_ONU_GEMPORT_DOWN_PROFILE_REF: [
        (f"{OID_ONU_GEMPORT_DOWN_PROFILE_REF}.{PON_IFINDEX}.3.1", 1879048204),
    ],
    OID_ONU_SERVICE_PORT_VLAN: [
        (f"{OID_ONU_SERVICE_PORT_VLAN}.{PON_IFINDEX}.3.1.15", 15),
        (f"{OID_ONU_SERVICE_PORT_VLAN}.{PON_IFINDEX}.3.2.16484", 16484),
    ],
    OID_ONU_DISTANCE: [
        (f"{OID_ONU_DISTANCE}.{OPTICAL_IFINDEX}.3", 6899),
    ],
}


class FakeSnmp:
    """bulkwalk berdasarkan tabel di atas; mencatat tiap base OID yang diminta."""

    def __init__(self, rows=None):
        self.rows = SNMP_ROWS if rows is None else rows
        self.calls: list[str] = []

    async def bulkwalk(self, base_oid):
        self.calls.append(base_oid)
        return self.rows.get(base_oid, [])


def _driver(snmp=None) -> ZteC320Driver:
    driver = ZteC320Driver(host="192.0.2.1", cli_username="u", cli_password="p",
                           cli_protocol="telnet", cli_port=23, snmp_community="c",
                           snmp_port=161)
    driver._snmp = snmp or FakeSnmp()  # noqa: SLF001 - test seam
    return driver


async def test_fetch_provisioning_reads_profiles_vlan_distance_via_snmp_only():
    snmp = FakeSnmp()
    driver = _driver(snmp)
    result = await driver.fetch_provisioning()

    assert len(result.onus) == 1
    onu = result.onus[0]
    assert (onu.slot, onu.port, onu.onu_id) == (2, 1, 3)
    assert onu.upload_profile == "SMARTOLT-HFA_Lite-UP"
    assert onu.download_profile == "SMARTOLT-HFA_Lite-DOWN"
    # VLAN 100 berasal dari nilai bertopeng 16484.
    assert onu.vlan_ids == [15, 100]
    assert onu.distance_m == 6899
    assert ("SMARTOLT-HFA_Lite-UP", "upload", 10240) in [
        (p.name, p.direction, p.kbps) for p in result.profiles
    ]
    # Satu kali baca untuk SELURUH OLT: tidak ada walk per-PON/per-ONU.
    # 4 katalog profil + 2 pemakaian profil per ONU + VLAN + jarak = 8 bulkwalk, tetap
    # 8 walau ONU-nya 246 (bukti WNG).
    assert len(snmp.calls) == 8
    assert len(snmp.calls) == len(set(snmp.calls))


async def test_fetch_provisioning_tolerates_empty_tables():
    """OLT yang tidak menjawab tabel provisioning -> kosong, bukan nilai karangan."""
    result = await _driver(FakeSnmp({})).fetch_provisioning()
    assert (result.onus, result.profiles) == ([], [])


# --- pengisian kolom ONU ----------------------------------------------------


class FakeDb:
    """DB in-memory secukupnya: select(Model) -> daftar objek, db.add menampung baru."""

    def __init__(self, objects):
        self.objects = list(objects)
        self.added: list[object] = []
        self._next_id = 900

    async def execute(self, stmt):
        model = stmt.column_descriptions[0]["entity"]
        rows = [o for o in self.objects if isinstance(o, model)]
        cols = [c["name"] for c in stmt.column_descriptions]
        if len(cols) == 1 and cols[0] == model.__name__:
            return _Result([(o,) for o in rows])
        return _Result([tuple(getattr(o, c) for c in cols) for o in rows])

    async def scalar(self, stmt):
        result = await self.execute(stmt)
        rows = [r for r in result._rows if _matches(stmt, r[0])]
        return rows[0][0] if rows else None

    def add(self, obj):
        self.added.append(obj)
        self.objects.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1


def _matches(stmt, obj) -> bool:
    """Evaluasi WHERE sederhana (kolom == nilai / lower(kolom) == nilai) di Python."""
    import sqlalchemy as sa

    for clause in stmt.whereclause.clauses if hasattr(stmt.whereclause, "clauses") \
            else [stmt.whereclause]:
        left, right = clause.left, clause.right
        value = right.value if isinstance(right, sa.sql.elements.BindParameter) else right
        if isinstance(left, sa.sql.functions.Function):  # lower(col) / lower(regexp_replace(col))
            inner = left.clauses.clauses[0]
            if isinstance(inner, sa.sql.functions.Function):  # regexp_replace(col, ...)
                column = inner.clauses.clauses[0]
                actual = master_data_service.normalize_master_name(
                    getattr(obj, column.name, None) or ""
                )
            else:
                actual = (getattr(obj, inner.name, None) or "").lower()
            if clause.operator is sa.sql.operators.in_op:
                if actual not in {v.lower() for v in value}:
                    return False
            elif actual != value:
                return False
        elif isinstance(left, sa.Column):
            actual = getattr(obj, left.name, None)
            if clause.operator is sa.sql.operators.is_:
                if actual is not None:
                    return False
            elif actual != value:
                return False
    return True


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def scalars(self):
        return [r[0] for r in self._rows]


class StubDriver:
    def __init__(self, provisioning):
        self._provisioning = provisioning

    async def fetch_provisioning(self):
        return self._provisioning


DESC = ("zone_Ngadirojo_descr_Terminal ngadirojo"
        "_odb_WNG-01B0313-depan pasar ngadirojo_authd_20260330")


def _scenario(description=DESC, **onu_kwargs):
    olt = Olt(name="WNG", owner_id=1)
    olt.id = 158
    pon = PonPort(olt_id=158, slot=2, port=1)
    pon.id = 500
    onu = Onu(olt_id=158, pon_port_id=500, onu_index=3, serial_number="SN3",
              description=description, **onu_kwargs)
    onu.id = 1
    vlan15 = Vlan(olt_id=158, vlan_id=15, name="VLAN15", type="internet")
    vlan15.id = 70
    vlan100 = Vlan(olt_id=158, vlan_id=100, name="VLAN100", type="management")
    vlan100.id = 71
    db = FakeDb([olt, pon, onu, vlan15, vlan100])
    return db, olt, onu


async def test_sync_onu_metadata_fills_zone_odp_address_speed_vlan():
    db, olt, onu = _scenario()
    provisioning = (await _driver().fetch_provisioning())
    stats = await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))

    zone = next(o for o in db.added if isinstance(o, Zone))
    splitter = next(o for o in db.added if isinstance(o, Splitter))
    assert zone.name == "Ngadirojo" and zone.owner_id == 1
    assert splitter.name == "WNG-01B0313-depan pasar ngadirojo"
    assert (splitter.type, splitter.zone_id, splitter.olt_id) == ("odp", zone.id, 158)
    assert (onu.zone_id, onu.splitter_id) == (zone.id, splitter.id)
    assert onu.address == "Terminal ngadirojo"
    assert onu.registered_at == datetime(2026, 3, 30, tzinfo=UTC)
    # VLAN layanan = 15; VLAN 100 ditandai management di master, jadi tidak dipilih.
    assert onu.vlan_id == 70
    assert onu.distance_m == 6899

    profiles = {(p.direction, p.name, p.speed_kbps, p.device_profile_id)
                for p in db.added if isinstance(p, SpeedProfile)}
    # Kolom `name` = nama tampilan (token SmartOLT dibuang, lihat app.core.profile_name);
    # `device_profile_id` tetap nama di perangkat apa adanya karena dipakai di command CLI.
    assert profiles == {
        ("upload", "HFA_Lite", 10240, "SMARTOLT-HFA_Lite-UP"),
        ("download", "HFA_Lite", 20480, "SMARTOLT-HFA_Lite-DOWN"),
    }
    assert onu.upload_speed_profile_id is not None
    assert onu.download_speed_profile_id is not None
    assert onu.srv_profile_id == "SMARTOLT-HFA_Lite-UP"
    assert onu.line_profile_id == "SMARTOLT-HFA_Lite-DOWN"
    assert stats["description_structured"] == 1
    assert stats["filled_zone"] == stats["filled_splitter"] == 1
    assert stats["provisioning_matched"] == 1


async def test_sync_onu_metadata_is_idempotent_and_keeps_manual_values():
    db, olt, onu = _scenario()
    provisioning = await _driver().fetch_provisioning()
    await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))
    masters_after_first = len(db.added)
    zone_id, splitter_id, vlan_id = onu.zone_id, onu.splitter_id, onu.vlan_id

    stats = await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))

    # Tidak ada baris master kedua, tidak ada kolom yang berubah.
    assert len(db.added) == masters_after_first
    assert (onu.zone_id, onu.splitter_id, onu.vlan_id) == (zone_id, splitter_id, vlan_id)
    assert stats["filled_zone"] == stats["filled_splitter"] == stats["filled_vlan"] == 0


async def test_manual_values_not_overwritten():
    """Operator sudah mengisi alamat/zone sendiri -> sinkron tidak menimpanya."""
    db, olt, onu = _scenario(address="Alamat diisi operator", zone_id=42)
    provisioning = await _driver().fetch_provisioning()
    await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))
    assert onu.address == "Alamat diisi operator"
    assert onu.zone_id == 42


async def test_free_text_description_becomes_address_not_zone():
    db, olt, onu = _scenario(description="Jl. Diponegoro no 97 Wonogiri")
    provisioning = await _driver().fetch_provisioning()
    stats = await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))
    assert onu.address == "Jl. Diponegoro no 97 Wonogiri"
    assert (onu.zone_id, onu.splitter_id) == (None, None)
    assert not [o for o in db.added if isinstance(o, (Zone, Splitter))]
    assert stats["description_free_text"] == 1


async def test_create_master_false_only_links_existing_zone():
    db, olt, onu = _scenario()
    existing = Zone(owner_id=1, name="ngadirojo")  # beda huruf besar/kecil, harus cocok
    existing.id = 7
    db.objects.append(existing)
    provisioning = await _driver().fetch_provisioning()
    await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning),
                                            create_master=False)
    assert onu.zone_id == 7
    assert not [o for o in db.added if isinstance(o, (Zone, Splitter))]


async def test_reuses_speed_profile_written_by_read_from_olt_path():
    """`sync_speed_profiles` menyimpan device_profile_id + suffix (`..-UP_UP`).

    Baris itu harus DIPAKAI ULANG, bukan diduplikat (bug nyata: 78 baris profil WNG
    sudah ada dari jalur "Baca dari OLT" sebelum sinkron metadata jalan).
    """
    db, olt, onu = _scenario()
    existing = SpeedProfile(name="SMARTOLT-HFA_Lite", direction="upload", speed_kbps=10240,
                            olt_id=158, device_profile_id="SMARTOLT-HFA_Lite-UP_UP")
    existing.id = 55
    db.objects.append(existing)
    provisioning = await _driver().fetch_provisioning()
    await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))

    assert onu.upload_speed_profile_id == 55
    assert [p for p in db.added if isinstance(p, SpeedProfile)
            and p.direction == "upload"] == []


async def test_speed_profile_not_invented_when_device_omits_kbps():
    """Perangkat tidak melaporkan kecepatan -> jangan buat baris master dengan angka karangan."""
    rows = dict(SNMP_ROWS)
    rows[OID_TRAFFIC_PROFILE_PIR_KBPS] = []
    provisioning = await _driver(FakeSnmp(rows)).fetch_provisioning()
    db, olt, onu = _scenario()
    await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))
    assert onu.download_speed_profile_id is None
    assert not [p for p in db.added if isinstance(p, SpeedProfile)
                and p.direction == "download"]
    # Arah upload tetap terisi: satu arah gagal tidak menggagalkan yang lain.
    assert onu.upload_speed_profile_id is not None


async def test_zone_name_underscore_variant_does_not_duplicate_master():
    """OLT WNG nyata menulis zone yang SAMA dua gaya: `Kecamatan_Selogiri` + `Kecamatan Selogiri`.

    Keduanya harus menunjuk SATU baris Zone, dan nama tersimpan pakai spasi.
    """
    db, olt, onu_a = _scenario(description="zone_Kecamatan_Selogiri_descr_Jl A_authd_20250131")
    onu_b = Onu(olt_id=158, pon_port_id=500, onu_index=4, serial_number="SN4",
                description="zone_Kecamatan Selogiri_descr_Jl B_authd_20250201")
    onu_b.id = 2
    db.objects.append(onu_b)
    provisioning = await _driver().fetch_provisioning()
    await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))

    zones = [o for o in db.added if isinstance(o, Zone)]
    assert [z.name for z in zones] == ["Kecamatan Selogiri"]
    assert onu_a.zone_id == onu_b.zone_id == zones[0].id


async def test_normalize_master_name_treats_underscore_as_space():
    norm = master_data_service.normalize_master_name
    assert norm("Kecamatan_Selogiri") == norm("Kecamatan Selogiri") == "kecamatan selogiri"
    assert norm("WNG-01B0313-depan  pasar") == "wng-01b0313-depan pasar"


async def test_empty_description_counted_and_leaves_metadata_blank():
    db, olt, onu = _scenario(description=None)
    provisioning = await _driver().fetch_provisioning()
    stats = await onboarding_sync.sync_onu_metadata(db, olt, StubDriver(provisioning))
    assert stats["description_empty"] == 1
    assert (onu.zone_id, onu.splitter_id, onu.address) == (None, None, None)
    # Provisioning SNMP tetap terisi walau description kosong.
    assert onu.vlan_id == 70 and onu.download_speed_profile_id is not None
