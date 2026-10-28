"""Regresi bug "inventory OLT selalu kosong" (OLT SBI, C300 nyata, 2026-10-24).

Semua fixture di tests/fixtures/cli/zte_show_* adalah transkrip read-only dari perangkat
nyata (serial disanitasi). Tiga bug yang ditutup di sini:

1. `PHASE_STATE_TO_STATUS` bergeser satu nilai -> seluruh ONU working (SNMP 3) dibaca
   "unknown" dan DyingGasp (4) dibaca "online".
2. `fetch_inventory()` memakai sintaks karangan (`show gpon onu state` dianggap memuat
   SN) dan tidak pernah mengembalikan VLAN.
3. `sync_olt_metrics` tidak pernah memanggil `fetch_inventory()`, jadi tidak ada baris
   ONU/VLAN yang pernah dibuat dari discovery.
"""

from pathlib import Path
from types import SimpleNamespace

from app.drivers.types import OltInventory, OnuSnapshot
from app.drivers.zte_c320 import (
    _parse_onu_baseinfo,
    _parse_onu_metadata,
    _parse_onu_state,
    _parse_vlan_summary,
    decode_optical_ifindex,
    decode_pon_ifindex,
    encode_pon_ifindex,
    phase_state_to_status,
)
from app.services import sync_service
from app.worker import handlers

FIXTURES = Path(__file__).parent / "fixtures" / "cli"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_phase_state_matches_device_transcript():
    """SNMP walk OLT SBI: 1/6/1:7 DyingGasp = 4, sisanya working = 3 (NEXFIBER-SNMP-OID)."""
    assert phase_state_to_status(3) == "online"
    assert phase_state_to_status(4) == "dying_gasp"
    assert phase_state_to_status(1) == "los"
    assert phase_state_to_status(6) == "offline"
    for transitional in (0, 2, 5):
        assert phase_state_to_status(transitional) == "unknown"


def test_phase_text_and_snmp_agree():
    states = _parse_onu_state(_fixture("zte_show_gpon_onu_state.txt"))
    by_pos = {(s.slot, s.port, s.onu_id): s.status for s in states}
    assert by_pos[(6, 1, 7)] == phase_state_to_status(4) == "dying_gasp"
    assert by_pos[(6, 1, 1)] == phase_state_to_status(3) == "online"


def test_parse_onu_state_reads_all_pons():
    states = _parse_onu_state(_fixture("zte_show_gpon_onu_state.txt"))
    assert len(states) == 5  # baris header/footer tidak ikut
    assert {(s.slot, s.port) for s in states} == {(6, 1), (6, 2)}
    assert all(s.admin_state == "enabled" for s in states)


def test_parse_onu_baseinfo_gives_serials():
    rows = _parse_onu_baseinfo(_fixture("zte_show_gpon_onu_baseinfo.txt"))
    assert rows[(6, 1, 2)] == ("TESTSN00000002", "HG8145V5")
    assert len(rows) == 3


def test_parse_onu_metadata_reads_name_and_description():
    """Satu-satunya metadata pelanggan yang ADA di perangkat: baris `name`/`description`
    di stanza `interface gpon-onu_...` pada `show running-config`."""
    rows = _parse_onu_metadata(_fixture("zte_show_running_config_inventory.txt"))
    assert rows[(6, 1, 1)] == ("Pelanggan Satu", "Alamat bebas tanpa pemisah")
    # ONU tanpa baris name -> None, bukan string kosong dan bukan tebakan dari description.
    assert rows[(6, 1, 7)] == (None, "zone_WILAYAHB")
    # ONU tanpa description -> None.
    assert rows[(6, 2, 1)] == ("Pelanggan Empat", None)
    # stanza `interface gpon-olt_...` (bukan ONU) tidak boleh ikut terparsing
    assert len(rows) == 5


def test_parse_onu_metadata_does_not_invent_zone_or_splitter():
    """`description` di perangkat nyata adalah teks bebas: 35/39 ONU OLT SBI tidak punya
    pemisah apa pun. Parser SENGAJA tidak memecah token zone_/odb_ jadi relasi."""
    rows = _parse_onu_metadata(_fixture("zte_show_running_config_inventory.txt"))
    assert rows[(6, 1, 2)][1] == "zone_WILAYAHA_descr_Alamat_Dua_authd_20260901"


def test_parse_vlan_summary():
    assert _parse_vlan_summary(_fixture("zte_show_vlan_summary.txt")) == [
        1, 15, 19, 68, 100, 3045
    ]
    assert _parse_vlan_summary("    10-12,20 \n") == [10, 11, 12, 20]
    # uncfg-style error / prompt bukan VLAN
    assert _parse_vlan_summary("%Code 62310-GPONSRV : No related information\nOLT#") == []


def test_encode_pon_ifindex_roundtrip():
    # ifDescr C300 kosong -> ifindex PON harus dihitung.
    assert encode_pon_ifindex(6, 1) == 268828928
    assert encode_pon_ifindex(6, 2) == 268829184


def test_decode_optical_ifindex_uses_second_index_scheme():
    """Index tabel 1082.500 (nilai nyata OLT SBI) bukan skema 1012.3.28.

    Dibuktikan silang: ONU-RX index 285279745 harus PON 6/1 — dengan decode_pon_ifindex
    lama hasilnya slot=257 sehingga tidak ada ONU yang cocok dan Rx tetap NULL.
    """
    assert decode_optical_ifindex(285279745) == (6, 1)
    assert decode_optical_ifindex(285279746) == (6, 2)
    assert decode_pon_ifindex(285279745) != (6, 1)


# --- adopsi inventory ke DB -------------------------------------------------

class _Olt:
    id = 31
    status = None
    last_sync_at = None
    last_error = None


class _Result:
    rowcount = 1

    def scalars(self):
        return iter(())

    def __iter__(self):
        return iter(())


class _Db:
    """Session minimal: PON port 6/1 sudah ada, 6/2 belum (uji skipped_unknown_port).

    `_adopt_inventory` membuat baris ONU baru lewat `INSERT ... ON CONFLICT DO NOTHING`
    (aman kalau dua proses sync menulis bersamaan), jadi fake ini mencatat nilai INSERT
    sebagai objek supaya tes tetap bisa memeriksa isi barisnya seperti dulu.
    """

    def __init__(self, pon_rows=((6, 1, 9),)):
        self.pon_rows = pon_rows
        self.added: list = []
        self.statements = 0

    async def execute(self, stmt):
        self.statements += 1
        text = str(stmt)
        if "pon_ports" in text and text.strip().lower().startswith("select"):
            return iter(self.pon_rows)
        if "INSERT INTO onus" in text:
            params = stmt.compile().params
            self.added.append(SimpleNamespace(**params))
        return _Result()

    def add(self, obj):
        self.added.append(obj)


class _InventoryDriver:
    def __init__(self, inv: OltInventory):
        self.inv = inv
        self.calls: list[str] = []

    async def fetch_inventory(self):
        self.calls.append("fetch_inventory")
        return self.inv


async def test_adopt_inventory_creates_onu_rows_and_vlans():
    from datetime import UTC, datetime

    inv = OltInventory(
        onus=[
            OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000001",
                        status="online", onu_type="ALL-ONT", admin_state="enabled"),
            OnuSnapshot(slot=6, port=1, onu_id=7, serial_number="TESTSN00000007",
                        status="dying_gasp", onu_type="ALL-ONT", admin_state="enabled"),
        ],
        vlan_ids=[1, 100],
    )
    db, driver = _Db(), _InventoryDriver(inv)
    out = await sync_service._adopt_inventory(db, _Olt(), driver, datetime.now(UTC))
    assert out["onus_added"] == 2
    assert out["onus_skipped_unknown_port"] == 0
    assert out["vlans_on_device"] == 2
    serials = sorted(o.serial_number for o in db.added)
    assert serials == ["TESTSN00000001", "TESTSN00000007"]
    assert {o.status for o in db.added} == {"online", "dying_gasp"}
    assert all(o.config_state == "success" and o.onu_index in (1, 7) for o in db.added)


async def test_adopt_inventory_fills_device_metadata_without_guessing_zone():
    """Nama/deskripsi perangkat masuk kolom onus.name/description; zone & splitter tetap
    NULL karena perangkat tidak punya field itu (dan description = teks bebas)."""
    from datetime import UTC, datetime

    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000001",
                          status="online", name="Pelanggan Satu",
                          description="zone_WILAYAHA_descr_Alamat")],
        vlan_ids=[],
    )
    db = _Db()
    out = await sync_service._adopt_inventory(db, _Olt(), _InventoryDriver(inv),
                                              datetime.now(UTC))
    row = db.added[0]
    assert row.name == "Pelanggan Satu"
    assert row.description == "zone_WILAYAHA_descr_Alamat"  # apa adanya, tidak dipecah
    assert getattr(row, "zone_id", None) is None
    assert getattr(row, "splitter_id", None) is None
    assert getattr(row, "customer_name", None) is None  # nama pelanggan tetap milik operator
    assert out["onus_with_device_name"] == 1
    assert out["onus_with_device_description"] == 1


async def test_adopt_inventory_never_overwrites_operator_metadata():
    from datetime import UTC, datetime

    class _ExistingOnu:
        serial_number = "TESTSN00000001"
        pon_port_id = onu_index = None
        status = "unknown"
        last_sync_at = last_seen_at = None
        onu_type = None
        admin_state = "enabled"
        name = "Label diisi operator"
        description = "Alamat diisi operator"

    existing = _ExistingOnu()

    class _DbWithRow(_Db):
        async def execute(self, stmt):
            text = str(stmt)
            if "pon_ports" in text and text.strip().lower().startswith("select"):
                return iter(self.pon_rows)

            class _R(_Result):
                def scalars(self_inner):
                    return iter([existing])

            return _R()

    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000001",
                          status="online", name="Nama dari OLT",
                          description="Deskripsi dari OLT")],
        vlan_ids=[],
    )
    out = await sync_service._adopt_inventory(_DbWithRow(), _Olt(), _InventoryDriver(inv),
                                              datetime.now(UTC))
    assert out["onus_updated"] == 1
    assert existing.name == "Label diisi operator"
    assert existing.description == "Alamat diisi operator"
    assert existing.status == "online"  # status tetap ikut perangkat


async def test_adopt_inventory_writes_wan_vlan_from_device_to_existing_onu():
    """VLAN WAN perangkat (`flow 1 ... vlan N`) menimpa kolom DB: perangkat sumber kebenaran.

    Data uji SINTETIS (serial TESTSN..., bukan data pelanggan).
    """
    from datetime import UTC, datetime

    class _ExistingOnu:
        serial_number = "TESTSN00000002"
        pon_port_id = onu_index = None
        status = "unknown"
        last_sync_at = last_seen_at = None
        onu_type = None
        admin_state = "enabled"
        name = description = None
        wan_vlan = 999  # nilai lama, harus tergantikan

    existing = _ExistingOnu()

    class _DbWithRow(_Db):
        async def execute(self, stmt):
            text = str(stmt)
            if "pon_ports" in text and text.strip().lower().startswith("select"):
                return iter(self.pon_rows)

            class _R(_Result):
                def scalars(self_inner):
                    return iter([existing])

            return _R()

    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000002",
                          status="online", wan_vlan=15)],
        vlan_ids=[],
    )
    out = await sync_service._adopt_inventory(_DbWithRow(), _Olt(), _InventoryDriver(inv),
                                              datetime.now(UTC))
    assert existing.wan_vlan == 15
    assert out["onus_with_wan_vlan"] == 1


async def test_adopt_inventory_management_does_not_touch_primary_vlan():
    """VLAN management BUKAN VLAN utama: `onus.vlan_id` milik "Update VLAN", tidak boleh
    ditimpa sinkron management. Data uji SINTETIS (serial TESTSN..., bukan data pelanggan).
    """
    from datetime import UTC, datetime
    from types import SimpleNamespace

    class _ExistingOnu:
        serial_number = "TESTSN00000005"
        pon_port_id = onu_index = None
        status = "unknown"
        last_sync_at = last_seen_at = None
        onu_type = None
        admin_state = "enabled"
        name = description = None
        wan_vlan = None
        pppoe_username = None
        vlan_id = 42  # VLAN utama, TIDAK boleh berubah
        mgmt_ip_mode = None
        ip_address = None

    existing = _ExistingOnu()

    class _DbMgmt(_Db):
        async def execute(self, stmt):
            text = str(stmt)
            if "FROM vlans" in text:
                class _Rv(_Result):
                    def scalars(self_inner):
                        return iter([SimpleNamespace(id=7, vlan_id=15, type="management",
                                                    olt_id=None)])
                return _Rv()
            if "FROM onus" in text and text.strip().lower().startswith("select"):
                class _Ro(_Result):
                    def scalars(self_inner):
                        return iter([existing])
                return _Ro()
            return await super().execute(stmt)

    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000005",
                          status="online", management_ips=[(15, "dhcp", None)])],
        vlan_ids=[],
    )
    out = await sync_service._adopt_inventory(_DbMgmt(), _Olt(), _InventoryDriver(inv),
                                              datetime.now(UTC))
    assert existing.mgmt_ip_mode == "dhcp"
    assert existing.ip_address is None
    assert existing.vlan_id == 42  # VLAN utama tidak disentuh
    assert out["onus_with_management_ip"] == 1


from datetime import UTC, datetime  # noqa: E402  (blok tes management di bawah)


class _ExistingOnu(SimpleNamespace):
    """Baris ONU existing minimal untuk jalur update management (data sintetis)."""

    def __init__(self, serial, ip=None):
        super().__init__(serial_number=serial, pon_port_id=None, onu_index=None,
                         status="unknown", last_sync_at=None, last_seen_at=None,
                         onu_type=None, admin_state="enabled", name=None,
                         description=None, wan_vlan=None, pppoe_username=None,
                         vlan_id=42, mgmt_ip_mode=None, ip_address=ip)


def _mgmt_db(existing, mgmt_vlan_ids):
    """`_Db` + master VLAN management (angka bebas, bukan tetap 100); existing=None = insert."""
    class _DbMgmt(_Db):
        async def execute(self, stmt):
            text = str(stmt)
            if "FROM vlans" in text:
                class _Rv(_Result):
                    def scalars(self_inner):
                        return iter([SimpleNamespace(id=i, vlan_id=v, type="management",
                                                    olt_id=None)
                                     for i, v in enumerate(mgmt_vlan_ids, 1)])
                return _Rv()
            if (existing is not None and "FROM onus" in text
                    and text.strip().lower().startswith("select")):
                class _Ro(_Result):
                    def scalars(self_inner):
                        return iter([existing])
                return _Ro()
            return await super().execute(stmt)
    return _DbMgmt()


async def test_adopt_inventory_insert_fills_ip_from_management_vlan():
    """1 IP management -> `ip_address` terisi di jalur insert (dulu hanya bila tepat satu)."""
    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000021",
                          status="online", management_ips=[(23, "static", "10.23.0.9")])],
        vlan_ids=[])
    db = _mgmt_db(None, [23])
    out = await sync_service._adopt_inventory(db, _Olt(), _InventoryDriver(inv),
                                              datetime.now(UTC))
    assert out["onus_added"] == 1
    assert db.added[0].ip_address == "10.23.0.9"
    assert db.added[0].mgmt_ip_mode == "static"


async def test_adopt_inventory_many_management_ips_takes_first_reported():
    """2+ IP management -> kandidat pertama urutan dilaporkan perangkat, deterministik."""
    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000022",
                          status="online",
                          management_ips=[(2310, "static", "10.31.0.2"),
                                          (23, "static", "10.23.0.8"),
                                          (2310, "static", "10.31.0.3")])],
        vlan_ids=[])
    db = _mgmt_db(None, [23, 2310])
    await sync_service._adopt_inventory(db, _Olt(), _InventoryDriver(inv), datetime.now(UTC))
    assert db.added[0].ip_address == "10.31.0.2"


async def test_adopt_inventory_update_takes_first_management_ip():
    """Jalur update sama aturannya: 2+ IP management -> yang pertama, menimpa nilai lama."""
    existing = _ExistingOnu("TESTSN00000005", ip="10.50.0.7")
    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000005",
                          status="online",
                          management_ips=[(231, "static", "10.21.0.2"),
                                          (231, "static", "10.21.0.3")])],
        vlan_ids=[])
    out = await sync_service._adopt_inventory(_mgmt_db(existing, [231]), _Olt(),
                                              _InventoryDriver(inv), datetime.now(UTC))
    assert existing.ip_address == "10.21.0.2"
    assert out["onus_updated"] == 1


async def test_adopt_inventory_no_management_ip_never_clears_ip():
    """0 IP management -> ip_address tidak disentuh (tidak dikosongkan/ditebak)."""
    existing = _ExistingOnu("TESTSN00000005", ip="10.50.0.7")
    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000005",
                          status="online", management_ips=[(77, "static", "192.0.2.7")])],
        vlan_ids=[])
    await sync_service._adopt_inventory(_mgmt_db(existing, [231]), _Olt(),
                                        _InventoryDriver(inv), datetime.now(UTC))
    assert existing.ip_address == "10.50.0.7"  # IP non-management tidak menimpa

    existing2 = _ExistingOnu("TESTSN00000005", ip="10.50.0.7")
    inv2 = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000005",
                          status="online", management_ips=[(231, "dhcp", None)])],
        vlan_ids=[])
    await sync_service._adopt_inventory(_mgmt_db(existing2, [231]), _Olt(),
                                        _InventoryDriver(inv2), datetime.now(UTC))
    assert existing2.ip_address == "10.50.0.7"  # tanpa IP dilaporkan -> dibiarkan apa adanya


async def test_adopt_inventory_only_management_vlan_ip_is_stored():
    """IP non-management tidak pernah masuk `ip_address` — insert maupun update."""
    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000023",
                          status="online",
                          management_ips=[(77, "static", "192.0.2.7"),
                                          (2310, "static", "10.31.0.9")])],
        vlan_ids=[])
    db = _mgmt_db(None, [23, 2310])
    await sync_service._adopt_inventory(db, _Olt(), _InventoryDriver(inv), datetime.now(UTC))
    assert db.added[0].ip_address == "10.31.0.9"

    existing = _ExistingOnu("TESTSN00000024", ip="10.50.0.7")
    inv2 = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000024",
                          status="online",
                          management_ips=[(77, "static", "192.0.2.7"),
                                          (2310, "static", "10.31.0.9")])],
        vlan_ids=[])
    await sync_service._adopt_inventory(_mgmt_db(existing, [23, 2310]), _Olt(),
                                        _InventoryDriver(inv2), datetime.now(UTC))
    assert existing.ip_address == "10.31.0.9"


async def test_adopt_inventory_fills_wan_ip_from_non_management_candidate():
    """Kolom `wan_ip_address` = kandidat IP VLAN NON-management pertama (urutan
    `management_ips`); `ip_address` tetap hanya VLAN management — keduanya tidak boleh
    pernah tumpang tindih."""
    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000031",
                          status="online",
                          management_ips=[(77, "static", "192.0.2.7"),
                                          (2310, "static", "10.31.0.9")])],
        vlan_ids=[])
    db = _mgmt_db(None, [23, 2310])
    await sync_service._adopt_inventory(db, _Olt(), _InventoryDriver(inv), datetime.now(UTC))
    assert db.added[0].ip_address == "10.31.0.9"
    assert db.added[0].wan_ip_address == "192.0.2.7"

    existing = _ExistingOnu("TESTSN00000032", ip="10.50.0.7")
    existing.wan_ip_address = "10.60.0.7"
    inv2 = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000032",
                          status="online",
                          management_ips=[(77, "dhcp", None),
                                          (2310, "static", "10.31.0.9")])],
        vlan_ids=[])
    await sync_service._adopt_inventory(_mgmt_db(existing, [23, 2310]), _Olt(),
                                        _InventoryDriver(inv2), datetime.now(UTC))
    assert existing.ip_address == "10.31.0.9"
    # Tanpa kandidat non-management ber-IP: kolom tidak disentuh, tidak dikosongkan.
    assert existing.wan_ip_address == "10.60.0.7"

    kosong = _ExistingOnu("TESTSN00000033")
    inv3 = OltInventory(
        onus=[OnuSnapshot(slot=6, port=1, onu_id=1, serial_number="TESTSN00000033",
                          status="online", management_ips=[(231, "dhcp", None)])],
        vlan_ids=[])
    await sync_service._adopt_inventory(_mgmt_db(kosong, [231]), _Olt(),
                                        _InventoryDriver(inv3), datetime.now(UTC))
    assert getattr(kosong, "wan_ip_address", None) is None  # tidak pernah menebak


async def test_adopt_inventory_skips_unknown_pon_port():
    from datetime import UTC, datetime

    inv = OltInventory(
        onus=[OnuSnapshot(slot=6, port=2, onu_id=1, serial_number="TESTSN00000099",
                          status="online")],
        vlan_ids=[],
    )
    db = _Db(pon_rows=())  # tidak ada PON terdaftar
    out = await sync_service._adopt_inventory(db, _Olt(), _InventoryDriver(inv),
                                              datetime.now(UTC))
    assert out["onus_added"] == 0 and out["onus_skipped_unknown_port"] == 1
    assert db.added == []


def test_metrics_job_is_the_single_inventory_entrypoint():
    """Tidak ada job type baru: adopsi masuk sync_olt_metrics (DECISIONS job & scheduling)."""
    assert "sync_olt_metrics" in handlers.HANDLERS
    assert "sync_inventory" not in handlers.HANDLERS
    assert "_adopt_inventory" in sync_service.sync_olt_metrics.__code__.co_names
