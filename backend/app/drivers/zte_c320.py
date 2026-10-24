"""ZTE ZXA10 C300/C320 driver (PRD 4.3). MVP's only vendor implementation.

Command templates for authorize/modify/backup_config were built from real running-config
transcripts captured off a production ZTE C320 (gpon-onu interface blocks). Parsers for
list_unconfigured, show card, show processor, show version-running, and pon power
attenuation were VERIFIED against a real live device (OLT "SBI", C300, read-only CLI
session, 2026-10-24) -- confirmed and corrected multiple parser bugs found this way (card
rows with missing RealType, processor column order, version-running multi-row format).
CLI transport also fixed: netmiko device_type="generic_termserver" never logs in to ZXA10
(stuck at Username:/Password: prompt forever) -- switched to "zte_zxros"/"zte_zxros_telnet".
Still mark delete/set_state/reboot CLI syntax as UNVERIFIED
until confirmed against a live device (only read-only commands were run against SBI).
fetch_inventory + optical (Rx ONU/OLT) sekarang TERVERIFIKASI terhadap OLT SBI
(read-only 2026-10-24) — lihat tests/test_olt_inventory_sync.py.
"""

import re

from app.drivers import onu_report
from app.drivers.base import OltDriver
from app.drivers.errors import ZTE_ERROR_PATTERNS, is_error_output
from app.drivers.transport.snmp import SnmpTransport
from app.drivers.transport.ssh import SshTransport
from app.drivers.transport.telnet import TelnetTransport
from app.drivers.types import (
    AuthorizeRequest,
    ConnectionCheck,
    DriverResult,
    InterfaceStatus,
    ModifyRequest,
    OltCard,
    OltHealth,
    OltInventory,
    OnuLiveDetail,
    OnuReport,
    OnuSnapshot,
    OnuStatusSample,
    OpticalSample,
    PonPortInfo,
    TrafficProfile,
    UnconfiguredOnu,
)

# SNMP OIDs (standard GPON ifTable + ZTE enterprise MIB). Not vendor-secret; pulled from
# public ZTE MIB documentation. ifindex is pon_ports.ifindex, resolved by the caller.
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus: 1=up, 2=down
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr, e.g. "gpon-olt_1/3/6"

# Kesehatan OLT (NEXFIBER-SNMP-OID.md, ditandai terverifikasi di sana).
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3"  # sysUpTime, satuan 1/100 detik
OID_OLT_TEMPERATURE = "1.3.6.1.4.1.3902.1015.2.1.3.2"
OID_SYS_NAME = "1.3.6.1.2.1.1.5"  # sysName
OID_SYS_LOCATION = "1.3.6.1.2.1.1.6"  # sysLocation
# Nama interface uplink ZTE di ifDescr: gei_1/5/1 (GE), xgei_1/5/1 (10GE).
UPLINK_PREFIXES = ("gei_", "xgei_", "gei-", "xgei-")
# Nama port uplink yang sah: gei_<rack>/<slot>/<port> atau xgei_... (dipakai validasi push).
UPLINK_PORT_RE = re.compile(r"^(x?gei)_(\d+)/(\d+)/(\d+)$", re.I)
PORT_SPEEDS = ("10", "100", "1000", "10000")
DUPLEXES = ("full", "half")

# Optical power OIDs (ZTE enterprise MIB). TERVERIFIKASI di OLT SBI (read-only
# 2026-10-24) dengan silang CLI `show pon power onu-rx|olt-rx gpon-olt_1/6/1`:
#   - ONU Rx (downstream power at the ONU): table indexed by <pon_ifindex>.<onu_index>.1;
#     raw is signed 16-bit, dBm = (raw - 65536 if raw >= 32768 else raw) * 0.002 - 30.0.
#     This decode repeats identically in 3 independent branches of the source script.
#   - OLT Rx (upstream power as received at the OLT, i.e. this ONU's Tx as seen by the
#     OLT): table indexed by <pon_ifindex>.<onu_index>. The source script's own scaling
#     is inconsistent across branches (/100 vs /1000) and its own worked example fails
#     its own sanity-range check — kept anyway per explicit instruction, but the
#     "-60..10 dBm" range filter below rejects obviously-wrong readings like that example.
OID_ONU_RX_POWER = "1.3.6.1.4.1.3902.1082.500.20.2.2.2.1.10"
OID_OLT_RX_POWER = "1.3.6.1.4.1.3902.1082.500.1.2.4.2.1.2"

# ONU phase-state + PON ifindex layout.
#   - phase-state table indexed by <pon_ifindex>.<onu_index>.
#   - pon_ifindex = BASE + slot * SLOT_MUL + port * PORT_MUL (gpon-olt_1/1/1 -> 268501248).
#   - nilai enum: NEXFIBER-SNMP-OID.md "Nilai phase state ZTE" (0 logging, 1 los,
#     2 syncMib, 3 working, 4 dyingGasp, 5 authFailed, 6 offline). BUG NYATA (OLT SBI
#     C300, read-only, 2026-10-24): peta lama {2:los,4:online,5:dying_gasp,7:offline}
#     bergeser satu nilai, jadi SEMUA ONU working (SNMP=3) dibaca "unknown" dan ONU
#     DyingGasp (SNMP=4) dibaca "online". Dibuktikan silang dengan
#     `show gpon onu state gpon-olt_1/6/1`: 1/6/1:7 DyingGasp = SNMP 4, sisanya
#     working = SNMP 3.
#   - logging/syncMib/authFailed transisional -> "unknown".
OID_ONU_PHASE_STATE = "1.3.6.1.4.1.3902.1012.3.28.2.1.4"
PON_IFINDEX_BASE = 268435456
PON_IFINDEX_SLOT_MUL = 65536
PON_IFINDEX_PORT_MUL = 256
PHASE_STATE_TO_STATUS = {1: "los", 3: "online", 4: "dying_gasp", 6: "offline"}

# `show gpon onu state` kolom "Phase State" (teks) -> enum onus.status. Dipakai
# fetch_inventory; peta teks dan peta SNMP di atas harus setuju (sama-sama device nyata).
PHASE_TEXT_TO_STATUS = {
    "working": "online",
    "dyinggasp": "dying_gasp",
    "los": "los",
    "offline": "offline",
    "logging": "unknown",
    "syncmib": "unknown",
    "authfailed": "unknown",
}

def decode_pon_ifindex(ifindex: int) -> tuple[int, int]:
    rest = ifindex - PON_IFINDEX_BASE
    return rest // PON_IFINDEX_SLOT_MUL, (rest % PON_IFINDEX_SLOT_MUL) // PON_IFINDEX_PORT_MUL

def encode_pon_ifindex(slot: int, port: int) -> int:
    """Kebalikan decode_pon_ifindex. Dipakai saat ifDescr SNMP kosong (C300 produksi):
    ifindex dihitung, bukan dibaca. Terverifikasi di OLT SBI — PON 1/6/1 -> 268828928 dan
    1/6/2 -> 268829184 sama dengan index yang dibalas walk phase-state.
    """
    return PON_IFINDEX_BASE + slot * PON_IFINDEX_SLOT_MUL + port * PON_IFINDEX_PORT_MUL

def phase_state_to_status(value: object) -> str:
    try:
        return PHASE_STATE_TO_STATUS.get(int(value), "unknown")
    except (TypeError, ValueError):
        return "unknown"

def _decode_onu_rx_dbm(value: object) -> float | None:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    if raw == 2147483647:  # SNMP "not available" sentinel
        return None
    if raw >= 32768:
        raw -= 65536
    return round(raw * 0.002 - 30.0, 2)

def _decode_olt_rx_dbm(value: object) -> float | None:
    """Tabel 1082.500 melaporkan dBm * 1000 (nilai NEGATIF apa adanya).

    BUG NYATA (OLT SBI, read-only 2026-10-24): rumus lama `(10000 - raw//10)/100`
    mengubah raw -23768 menjadi +337.68 lalu ditolak batas -60..10 -> olt_rx SELALU NULL.
    Silang CLI `show pon power olt-rx gpon-olt_1/6/1`: 1/6/1:1 = -23.768 dBm, raw = -23768.
    """
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    if raw == 2147483647:
        return None
    dbm = round(raw / 1000, 2)
    return dbm if -60 <= dbm <= 10 else None

def decode_optical_ifindex(ifindex: int) -> tuple[int, int]:
    """Skema index KEDUA (NEXFIBER-SNMP-OID "Index ZTE" nomor 2), dipakai tabel
    1082.500.*: ifIndex = (1<<28)|(rack<<24)|(shelf<<16)|(slot<<8)|port.

    BUG NYATA (OLT SBI, read-only 2026-10-24): fetch_optical memakai
    decode_pon_ifindex (skema 1012.3.28) pada index tabel 1082.500 sehingga PON 6/1
    terbaca slot=257/port=6 -> tidak ada ONU yang cocok, rx_power_dbm tetap NULL
    untuk semua 39 ONU. ifindex nyata 285279745 = PON 1/6/1.
    """
    return (ifindex >> 8) & 0xFF, ifindex & 0xFF

class ZteC320Driver(OltDriver):
    vendor = "zte"
    model = "C320"
    port_range = (1, 16)
    capabilities = {"cli_rx", "snmp_rx"}

    def __init__(
        self,
        host: str,
        cli_username: str,
        cli_password: str,
        cli_protocol: str,
        cli_port: int,
        snmp_community: str,
        snmp_port: int,
        cli_enable_password: str | None = None,
    ) -> None:
        self._host = host
        self._cli_username = cli_username
        self._cli_password = cli_password
        self._cli_protocol = cli_protocol
        self._cli_port = cli_port
        self._cli_enable_password = cli_enable_password
        self._snmp = SnmpTransport(host, snmp_community, snmp_port)

    def _open_cli(self) -> SshTransport | TelnetTransport:
        # BUG NYATA (ketemu read-only via OLT SBI, 2026-10-24): device_type default
        # "generic_termserver(_telnet)" netmiko tidak tahu login-prompt ZXA10 — tidak
        # pernah mengirim username/password, session macet di "Username:"/"Password:".
        # netmiko punya device_type khusus untuk ZTE ZXROS; pakai itu.
        if self._cli_protocol == "ssh":
            return SshTransport(
                host=self._host, username=self._cli_username, password=self._cli_password,
                port=self._cli_port, secret=self._cli_enable_password,
                device_type="zte_zxros",
            )
        return TelnetTransport(
            host=self._host, username=self._cli_username, password=self._cli_password,
            port=self._cli_port, secret=self._cli_enable_password,
            device_type="zte_zxros_telnet",
        )

    def _result(self, command: str, output: str) -> DriverResult:
        if is_error_output(output, ZTE_ERROR_PATTERNS):
            return DriverResult(success=False, raw_command=command, raw_output=output,
                                 message="OLT rejected command")
        return DriverResult(success=True, raw_command=command, raw_output=output)

    async def test_connection(self) -> ConnectionCheck:
        """CLI dan SNMP diuji sendiri-sendiri, dua boolean dari dua percobaan nyata.

        DECISIONS "Audit fitur SmartOLT": JANGAN tentukan status SNMP dari teks pesan CLI
        (atau sebaliknya) — bug nyata SmartOLT. Satu protokol gagal tidak membatalkan
        yang lain, jadi tiap percobaan punya try/except sendiri.
        """
        command = "show version-running"
        # "show version" ditolak sebagai ambiguous command di C300 (ketemu read-only
        # via OLT SBI, 2026-10-24) — "show version-running" selalu diterima.
        cli_ok, cli_message, raw_output = False, "", ""
        try:
            async with self._open_cli() as cli:
                raw_output = await cli.send_command(command)
        except Exception as exc:
            cli_message = f"CLI gagal: {exc}"
        else:
            if is_error_output(raw_output, ZTE_ERROR_PATTERNS):
                cli_message = "CLI menolak perintah"
            else:
                cli_ok, cli_message = True, "CLI menjawab"

        snmp_ok, snmp_message = False, ""
        try:
            rows = await self._snmp.bulkwalk(OID_SYS_UPTIME)
        except Exception as exc:
            snmp_message = f"SNMP gagal: {exc}"
        else:
            if rows:
                snmp_ok, snmp_message = True, "SNMP menjawab"
            else:
                snmp_message = "SNMP tidak mengembalikan data"

        return ConnectionCheck(cli_ok=cli_ok, snmp_ok=snmp_ok, cli_message=cli_message,
                               snmp_message=snmp_message, raw_command=command,
                               raw_output=raw_output)

    async def fetch_health(self) -> OltHealth:
        """`show card` + `show processor` + `show version-running` (semua terverifikasi di
        NEXFIBER-CLI-REFERENCE), suhu dan uptime lewat SNMP. Satu koneksi CLI untuk ketiga
        perintah — ini yang dibagi dengan optical di job sync_olt_metrics.
        """
        async with self._open_cli() as cli:
            cards_out = await cli.send_command("show card")
            processor_out = await cli.send_command("show processor")
            version_out = await cli.send_command("show version-running")
        cards = _merge_card_load(_parse_cards(cards_out), _parse_processor(processor_out))
        main = next((c for c in cards if c.cpu_pct is not None), None)
        return OltHealth(
            cpu_pct=main.cpu_pct if main else None,
            ram_pct=main.ram_pct if main else None,
            temperature_c=await self._snmp_first_float(OID_OLT_TEMPERATURE),
            uptime_seconds=await self._snmp_uptime_seconds(),
            software_version=_parse_software_version(version_out),
            cards=cards,
            uplink_ports=await self._list_uplink_ports(),
            sys_name=await self._snmp_first_str(OID_SYS_NAME),
            sys_location=await self._snmp_first_str(OID_SYS_LOCATION),
        )

    async def _list_uplink_ports(self) -> list[str]:
        """Nama port uplink dari ifDescr (SNMP), bukan parsing CLI: tabel yang sama sudah
        dipakai list_pon_ports, dan nama interface uplink ZTE berawalan gei/xgei.
        """
        try:
            rows = await self._snmp.bulkwalk(OID_IF_DESCR)
        except Exception:
            return []
        return sorted({str(v) for _oid, v in rows if str(v).startswith(UPLINK_PREFIXES)})

    async def _snmp_first_str(self, oid: str) -> str | None:
        """Nilai pertama satu OID skalar sebagai teks (sysName/sysLocation).

        Best-effort sama seperti _snmp_first_float: OID tidak dijawab != job gagal.
        """
        try:
            rows = await self._snmp.bulkwalk(oid)
        except Exception:
            return None
        value = str(rows[0][1]).strip() if rows else ""
        return value or None

    async def _snmp_first_float(self, oid: str) -> float | None:
        try:
            rows = await self._snmp.bulkwalk(oid)
        except Exception:
            return None  # kesehatan bersifat best-effort: OID tak ada != job gagal
        try:
            return float(str(rows[0][1])) if rows else None
        except ValueError:
            return None

    async def _snmp_uptime_seconds(self) -> int | None:
        ticks = await self._snmp_first_float(OID_SYS_UPTIME)
        return int(ticks // 100) if ticks is not None else None  # TimeTicks = 1/100 detik

    async def set_vlan_ports(self, vlan_id: int, ports: dict[str, str]) -> DriverResult:
        """Tagged/untagged VLAN di port uplink (NEXFIBER-CLI-REFERENCE "Ubah — VLAN dan
        uplink", status produksi). `ports` = {nama_port: "tagged"|"untagged"}.
        """
        commands: list[str] = []
        for port_name, mode in sorted(ports.items()):
            commands.append(f"interface {port_name}")
            if mode == "untagged":
                # Kode 60584: `untag` ditolak selama port masih trunk — hybrid dulu.
                commands += ["switchport mode hybrid", f"switchport vlan {vlan_id} untag"]
            else:
                commands += ["switchport mode trunk", f"switchport vlan {vlan_id} tag"]
            commands.append("exit")
        if not commands:
            return DriverResult(success=True, raw_command="", raw_output="",
                                message="Tidak ada port uplink yang dipilih")
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def fetch_interfaces(self) -> list[InterfaceStatus]:
        """Status live port uplink lewat `show interface port-status <nama>`.

        BUG NYATA (OLT SBI, 2026-10-24): `show interface port-status` TIDAK punya bentuk
        massal — tanpa nama port dijawab "Incomplete command", dan `all` / `xgei_1/19` /
        rentang `1-4` ditolak; hanya `1-2` (sub-rentang yang benar-benar ada) diterima.
        Jadi satu command per port, tidak bisa satu command untuk semua.

        Nama port juga tidak bisa diandalkan dari ifDescr: di perangkat itu seluruh
        ifDescr kosong, jadi `_list_uplink_ports()` (SNMP) dipakai kalau terisi, dan kalau
        kosong nama port ditebak dari `show card` lalu divalidasi ke perangkat — port yang
        dijawab error (mis. xgei_1/19/3 walau kartu melaporkan 4 port) otomatis hilang
        karena baris statusnya tidak pernah ada di output.
        """
        names = await self._list_uplink_ports()
        async with self._open_cli() as cli:
            if names:
                output = "\n".join([
                    await cli.send_command(f"show interface port-status {n}") for n in names
                ])
                return _parse_port_status(output)
            return await self._probe_uplink_ports(cli)

    async def _probe_uplink_ports(self, cli) -> list[InterfaceStatus]:
        """Cari port uplink dari `show card` saat ifDescr kosong.

        Per kartu: coba port 1 dengan awalan xgei lalu gei; awalan yang dijawab dipakai
        untuk sisa port kartu itu. Kartu PON/kontrol otomatis terlewat karena nama
        gei/xgei-nya ditolak perangkat.
        """
        rows: list[InterfaceStatus] = []
        cards = _parse_cards(await cli.send_command("show card"))
        for card in cards:
            if not card.port_count:
                continue
            for prefix in ("xgei", "gei"):
                first = _parse_port_status(
                    await cli.send_command(f"show interface port-status {prefix}_1/{card.slot}/1")
                )
                if not first:
                    continue
                rows += first
                for port in range(2, card.port_count + 1):
                    rows += _parse_port_status(await cli.send_command(
                        f"show interface port-status {prefix}_1/{card.slot}/{port}"
                    ))
                break
        return rows

    async def set_port_config(self, port: str, auto_nego: str, speed: str | None,
                              duplex: str | None) -> DriverResult:
        """Auto-negotiation / speed / duplex satu port uplink.

        Sintaks ZXROS (mode config-if): `negotiation auto` / `no negotiation auto` +
        `speed <mbps>` + `duplex <full|half>`. Validasi dilakukan di sini supaya tidak ada
        command setengah jadi yang terkirim ke perangkat.
        """
        commands = build_port_config_commands(port, auto_nego, speed, duplex)
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def list_unconfigured(self) -> list[UnconfiguredOnu]:
        command = "show gpon onu uncfg"
        async with self._open_cli() as cli:
            output = await cli.send_command(command)
        return _parse_unconfigured(output)

    async def authorize(self, req: AuthorizeRequest) -> DriverResult:
        commands = build_authorize_commands(req)
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def modify(self, req: ModifyRequest) -> DriverResult:
        # PRD 4.2: ZTE needs delete-then-recreate for active VLAN changes; plain attribute
        # edits (name/profile) can apply in-place via the onu interface block.
        onu_iface = f"gpon-onu_1/{req.slot}/{req.port}:{req.onu_id}"
        commands = [f"interface {onu_iface}"]
        if req.name:
            commands.append(f"name {req.name}")
        if req.line_profile_id:
            commands.append(f"tcont 1 profile {req.line_profile_id}")
        if req.srv_profile_id:
            commands.append(f"tcont 2 profile {req.srv_profile_id}")
        commands.append("exit")
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def delete(self, slot: int, port: int, onu_id: int) -> DriverResult:
        # UNVERIFIED: public syntax.
        iface = f"gpon-olt_1/{slot}/{port}"
        commands = [f"interface {iface}", f"no onu {onu_id}", "exit"]
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def set_state(self, slot: int, port: int, onu_id: int, enabled: bool) -> DriverResult:
        # UNVERIFIED: public syntax.
        onu_iface = f"gpon-onu_1/{slot}/{port}:{onu_id}"
        state_cmd = "no shutdown" if enabled else "shutdown"
        commands = [f"interface {onu_iface}", state_cmd, "exit"]
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def reboot(self, slot: int, port: int, onu_id: int) -> DriverResult:
        # UNVERIFIED: public syntax.
        command = f"pon-onu-mng gpon-onu_1/{slot}/{port}:{onu_id} reset"
        async with self._open_cli() as cli:
            output = await cli.send_command(command)
        return self._result(command, output)

    async def fetch_inventory(self) -> OltInventory:
        """ONU terdaftar + VLAN perangkat dalam SATU sesi CLI (read-only).

        Terverifikasi di OLT SBI (C300, read-only, 2026-10-24):
        - `show gpon onu state` TANPA argumen memang jalan dan mengembalikan seluruh PON
          (39 baris) — ini sumber posisi + phase state.
        - `show gpon onu baseinfo` tanpa argumen DITOLAK (`%Error 20203: Incomplete
          command`), jadi SN/tipe harus diambil per PON yang benar-benar punya ONU.
        - `show vlan summary` memberi daftar VLAN id perangkat.
        - `show running-config` (satu kali, ~11 detik, 83 KB) memuat stanza
          `interface gpon-onu_<pon>:<id>` dengan baris `name` dan `description` —
          SATU-SATUNYA metadata pelanggan yang ada di perangkat ini (39/39 ONU punya
          keduanya). Dibaca massal supaya tidak ada 39 perintah per-ONU.
        """
        async with self._open_cli() as cli:
            state_out = await cli.send_command("show gpon onu state")
            vlan_out = await cli.send_command("show vlan summary")
            config_out = await cli.send_command("show running-config")
            states = _parse_onu_state(state_out)
            baseinfo: dict[tuple[int, int, int], tuple[str | None, str | None]] = {}
            for slot, port in sorted({(s.slot, s.port) for s in states}):
                out = await cli.send_command(
                    f"show gpon onu baseinfo gpon-olt_1/{slot}/{port}"
                )
                baseinfo.update(_parse_onu_baseinfo(out))
        metadata = _parse_onu_metadata(config_out)
        onus = []
        for snap in states:
            serial, onu_type = baseinfo.get((snap.slot, snap.port, snap.onu_id), (None, None))
            if not serial:
                continue  # tanpa SN tidak bisa jadi baris onus (kunci uq_onu_olt_serial)
            snap.serial_number, snap.onu_type = serial, onu_type
            snap.name, snap.description = metadata.get(
                (snap.slot, snap.port, snap.onu_id), (None, None)
            )
            onus.append(snap)
        return OltInventory(onus=onus, vlan_ids=_parse_vlan_summary(vlan_out))

    async def fetch_onu_status(self) -> list[OnuStatusSample]:
        samples: list[OnuStatusSample] = []
        for oid, value in await self._snmp.bulkwalk(OID_ONU_PHASE_STATE):
            suffix = oid[len(OID_ONU_PHASE_STATE) + 1 :].split(".")
            if len(suffix) != 2:
                continue
            slot, port = decode_pon_ifindex(int(suffix[0]))
            samples.append(OnuStatusSample(slot=slot, port=port, onu_id=int(suffix[1]),
                                           status=phase_state_to_status(value)))
        return samples

    async def fetch_optical(self, slot: int | None, port: int | None) -> list[OpticalSample]:
        # SNMP bulkwalk is the primary path per capabilities; CLI fallback not implemented
        # since "snmp_rx" is declared for this model (PRD 4.3: probe capability, don't guess).
        # slot/port None = all PONs; otherwise rows are filtered to that PON.
        onu_rx_raw = await self._snmp.bulkwalk(OID_ONU_RX_POWER)
        olt_rx_raw = await self._snmp.bulkwalk(OID_OLT_RX_POWER)

        olt_rx_by_index: dict[tuple[int, int], float | None] = {}
        for oid, value in olt_rx_raw:
            suffix = oid[len(OID_OLT_RX_POWER) + 1 :].split(".")
            if len(suffix) != 2:
                continue
            pon_ifindex, onu_index = int(suffix[0]), int(suffix[1])
            olt_rx_by_index[(pon_ifindex, onu_index)] = _decode_olt_rx_dbm(value)

        samples: list[OpticalSample] = []
        for oid, value in onu_rx_raw:
            suffix = oid[len(OID_ONU_RX_POWER) + 1 :].split(".")
            if len(suffix) != 3:  # expected "<pon_ifindex>.<onu_index>.1"
                continue
            pon_ifindex, onu_index = int(suffix[0]), int(suffix[1])
            row_slot, row_port = decode_optical_ifindex(pon_ifindex)
            if slot is not None and port is not None and (row_slot, row_port) != (slot, port):
                continue
            samples.append(OpticalSample(
                slot=row_slot,
                port=row_port,
                onu_id=onu_index,
                rx_power_dbm=_decode_onu_rx_dbm(value),
                olt_rx_power_dbm=olt_rx_by_index.get((pon_ifindex, onu_index)),
            ))
        return samples

    async def backup_config(self) -> str:
        async with self._open_cli() as cli:
            return await cli.send_command("show running-config")

    async def create_vlan(self, vlan_id: int, description: str | None) -> DriverResult:
        # NEXFIBER-CLI-REFERENCE "Ubah — VLAN dan uplink" (status: produksi). Uplink
        # tagged/untagged belongs to Detail OLT tab VLANs, not to this create.
        commands = [f"vlan {vlan_id}"]
        if description:
            commands.append(f"description {description}")
        commands.append("exit")
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def delete_vlan(self, vlan_id: int) -> DriverResult:
        commands = [f"no vlan {vlan_id}"]
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def create_traffic_profile(
        self, name: str, direction: str, kbps: int
    ) -> DriverResult:
        # NEXFIBER-CLI-REFERENCE "Ubah — Profile kecepatan / Buat profile baru".
        if direction == "upload":
            commands = ["gpon", f"profile tcont {name}_UP type 5 fixed 64 assured 64 maximum {kbps}", "exit"]
        else:
            commands = ["gpon", f"profile traffic {name}_DN sir {kbps} pir {kbps}", "exit"]
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def list_traffic_profiles(self) -> list[TrafficProfile]:
        command = "show running-config | include profile tcont"
        command_dn = "show running-config | include profile traffic"
        async with self._open_cli() as cli:
            up = await cli.send_command(command)
            dn = await cli.send_command(command_dn)
        return _parse_traffic_profiles(up) + _parse_traffic_profiles(dn)

    async def list_pon_ports(self) -> list[PonPortInfo]:
        ports: list[PonPortInfo] = []
        for oid, value in await self._snmp.bulkwalk(OID_IF_DESCR):
            descr = str(value)
            if not descr.startswith("gpon-olt_"):
                continue
            slot, port = _parse_slot_port(descr)
            ports.append(PonPortInfo(slot=slot, port=port, ifindex=int(oid.rsplit(".", 1)[1])))
        if ports:
            return ports
        # BUG NYATA (OLT SBI C300, read-only 2026-10-24): seluruh ifDescr kosong, jadi
        # tak satu pun PON terbaca lewat SNMP dan pon_ports tidak pernah terisi. Fallback
        # CLI: posisi PON dari `show gpon onu state`, ifindex dihitung (encode_pon_ifindex).
        async with self._open_cli() as cli:
            state_out = await cli.send_command("show gpon onu state")
        return [
            PonPortInfo(slot=slot, port=port, ifindex=encode_pon_ifindex(slot, port))
            for slot, port in sorted({(s.slot, s.port) for s in _parse_onu_state(state_out)})
        ]

    async def list_onu_ids(self, slot: int, port: int) -> list[int]:
        # "onu <id> type <t> sn <sn>" lines match the real running-config transcripts;
        # the per-interface "show running-config interface" form itself is UNVERIFIED.
        command = f"show running-config interface gpon-olt_1/{slot}/{port}"
        async with self._open_cli() as cli:
            output = await cli.send_command(command)
        return _parse_onu_ids(output)

    # --- Detail ONU (PRD 3.4.6) ---------------------------------------------------

    async def fetch_onu_detail(self, slot: int, port: int, onu_id: int) -> OnuLiveDetail:
        """Baca live satu ONU untuk tab Status/Running config/Info software.

        Keempat perintah ✅ terverifikasi di NEXFIBER-CLI-REFERENCE.md ("Baca — ONU").
        `detail-info` & `attenuation` punya fallback regex yang dikonfirmasi lewat driver
        produksi ZTE C320 lain (2026-10-24); field yang masih tak cocok tetap None, bukan
        bikin job gagal.
        Satu sesi CLI untuk semua perintah (PRD 4.3: satu koneksi per OLT).
        """
        iface = f"gpon-onu_1/{slot}/{port}:{onu_id}"
        commands = [
            f"show gpon onu detail-info {iface}",
            f"show pon power attenuation {iface}",
            f"show gpon remote-onu equip {iface}",
            f"show running-config interface {iface}",
        ]
        async with self._open_cli() as cli:
            detail_out = await cli.send_command(commands[0])
            power_out = await cli.send_command(commands[1])
            equip_out = await cli.send_command(commands[2])
            config_out = await cli.send_command(commands[3])
        detail = _parse_onu_detail_info(detail_out)
        detail.rx_power_dbm, detail.tx_power_dbm, detail.olt_rx_power_dbm = _parse_attenuation(
            power_out, detail.rx_power_dbm, detail.tx_power_dbm, detail.olt_rx_power_dbm
        )
        detail.software_version, detail.software_version_standby, detail.hardware_version = (
            _parse_equip(equip_out, detail.hardware_version)
        )
        detail.running_config = config_out.strip()
        detail.raw_command = " ; ".join(commands)
        return detail

    # --- Diagnostik Detail ONU: tombol Status / Running config / Info SW -------------
    # Semua READ-ONLY. Satu sesi CLI per laporan (PRD 4.3). Perakitan teks di
    # drivers/onu_report.py (satu formatter, tidak ada versi kedua di frontend).

    async def fetch_onu_status_report(self, slot: int, port: int, onu_id: int) -> OnuReport:
        """9 blok tombol `Status`, urutan seperti kontrak output.

        Command ip-host / interface eth / `show mac gpon onu` dipakai (bukan wan-info /
        eth-status / `show mac gpon-onu_…` seperti aplikasi referensi) karena bentuk
        referensi terdaftar DITOLAK di NEXFIBER-CLI-REFERENCE §"Ditolak".
        `remote-onu catv|vlan|voip` belum tercatat di CLI-REFERENCE: kalau perangkat
        menolak, pesan errornya ditampilkan apa adanya, tidak diganti data contoh.
        """
        iface = f"gpon-onu_1/{slot}/{port}:{onu_id}"
        commands = [
            f"show pon power attenuation {iface}",
            f"show gpon remote-onu catv {iface}",
            f"show gpon onu detail-info {iface}",
            f"show gpon remote-onu ip-host {iface}",
            f"show gpon remote-onu interface eth {iface}",
            f"show gpon remote-onu vlan {iface}",
            f"show gpon remote-onu voip {iface}",
            f"show mac gpon onu {iface}",
        ]
        async with self._open_cli() as cli:
            outputs = [await cli.show(command) for command in commands]
        attenuation, catv, detail_info, ip_host, eth, vlan, voip, macs = outputs
        return OnuReport(
            view="status",
            output=onu_report.status_report(
                attenuation=attenuation, catv=catv, detail_info=detail_info,
                ip_host=ip_host, eth=eth, vlan=vlan, voip=voip, macs=macs,
            ),
            raw_command=" ; ".join(commands),
        )

    async def fetch_onu_running_config(self, slot: int, port: int, onu_id: int) -> OnuReport:
        """3 blok tombol `Show running-config`, dipisah `!`.

        Output UTUH tanpa penyamaran (keputusan eksplisit user). Pemanggil wajib sudah
        memastikan role berwenang; isi blok tidak boleh ditulis ke log/DB.
        """
        pon = f"1/{slot}/{port}"
        iface = f"gpon-onu_{pon}:{onu_id}"
        commands = [
            f"show gpon onu detail-info {iface}",
            f"show running-config interface {iface}",
            f"show onu running config {iface}",
        ]
        async with self._open_cli() as cli:
            detail = await cli.show(commands[0])
            onu_cfg = await cli.show(commands[1])
            mng_cfg = await cli.show(commands[2])
        return OnuReport(
            view="running",
            output=onu_report.running_config_report(
                detail_info=detail, onu_iface_config=onu_cfg,
                onu_mng_config=mng_cfg, pon=pon, onu_id=onu_id,
            ),
            raw_command=" ; ".join(commands),
        )

    async def fetch_onu_software_report(self, slot: int, port: int, onu_id: int) -> OnuReport:
        """2 blok tombol `Info SW` + baris Region 1/2 (tidak tersedia via CLI, ditulis
        apa adanya sebagai "tidak dilaporkan perangkat", bukan angka tebakan).
        """
        iface = f"gpon-onu_1/{slot}/{port}:{onu_id}"
        commands = [
            f"show gpon remote-onu equip {iface}",
            f"show gpon remote-onu capability {iface}",
        ]
        async with self._open_cli() as cli:
            equip = await cli.show(commands[0])
            capability = await cli.show(commands[1])
        return OnuReport(
            view="software",
            output=onu_report.software_report(equip=equip, capability=capability),
            raw_command=" ; ".join(commands),
        )

    async def set_onu_vlan(self, slot: int, port: int, onu_id: int, old_vlan: int | None,
                           new_vlan: int) -> DriverResult:
        """NEXFIBER-CLI-REFERENCE "Ubah — VLAN ONU" (status: 🔧 produksi).
        # UNVERIFIED: uji di ONU test — urutannya dari driver produksi lain, belum pernah
        # dijalankan dari Nexfiber. JANGAN dieksekusi ke OLT produksi oleh agent manapun.
        """
        onu_iface = f"gpon-onu_1/{slot}/{port}:{onu_id}"
        commands = [
            f"interface {onu_iface}",
            "no service-port 1",
            f"service-port 1 vport 1 user-vlan {new_vlan} vlan {new_vlan}",
            "exit",
            f"pon-onu-mng {onu_iface}",
        ]
        if old_vlan is not None:
            commands += [f"no flow 1 pri 0 vlan {old_vlan}",
                         f"no vlan-filter iphost 1 pri 0 vlan {old_vlan}"]
        commands += [f"flow 1 pri 0 vlan {new_vlan}",
                     f"vlan-filter iphost 1 pri 0 vlan {new_vlan}", "exit"]
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

    async def restore_factory(self, slot: int, port: int, onu_id: int) -> DriverResult:
        """# UNVERIFIED: uji di ONU test.

        Tidak ada perintah restore-factory ZTE di NEXFIBER-CLI-REFERENCE.md (yang tercatat
        `ont restore-factory` itu milik CDATA, sintaks berbeda). Bentuk di bawah mengikuti
        pola `pon-onu-mng` yang sama dengan reboot. JANGAN dipakai ke perangkat nyata
        sebelum ada transkrip asli dari ONU test.
        """
        onu_iface = f"gpon-onu_1/{slot}/{port}:{onu_id}"
        commands = [f"pon-onu-mng {onu_iface}", "restore factory", "exit"]
        async with self._open_cli() as cli:
            output = await cli.send_config_set(commands)
        return self._result(" ; ".join(commands), output)

# Baris `show interface port-status <nama>` (format nyata ZXROS):
#      Port      hybrid  Native Negotiation  Speed  Duplex Flow-   Admin      Link
#                Status  VLAN     auto       (Mbps)        Ctrl    Status
#     gei_1/3/1      optical  1       enable     auto    full  disable activate   down
PORT_STATUS_RE = re.compile(
    r"^[ \t]*(x?gei_\d+/\d+/\d+)[ \t]+(\S+)[ \t]+(\d+)[ \t]+(\S+)[ \t]+(\S+)"
    r"[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\S+)[ \t\r]*$",
    re.M | re.I,
)


def _parse_port_status(output: str) -> list[InterfaceStatus]:
    """Satu baris per port uplink; baris header dan error per-port diabaikan."""
    return [
        InterfaceStatus(
            name=m.group(1).lower(), media=m.group(2).lower(), pvid=int(m.group(3)),
            auto_nego=m.group(4).lower(), speed=m.group(5).lower(), duplex=m.group(6).lower(),
            flow_ctrl=m.group(7).lower(), admin_status=m.group(8).lower(), link=m.group(9).lower(),
        )
        for m in PORT_STATUS_RE.finditer(output)
    ]


def build_port_config_commands(port: str, auto_nego: str, speed: str | None,
                               duplex: str | None) -> list[str]:
    """Command auto-nego/speed/duplex satu port uplink; ValueError kalau input tak sah.

    Port gei tidak bisa dipaksa 10000 Mbps — perangkat menolak diam-diam, jadi ditolak
    di sini supaya tidak ada command yang terkirim.
    """
    match = UPLINK_PORT_RE.match((port or "").strip())
    if match is None:
        raise ValueError("Format port tidak valid; gunakan gei_R/S/P atau xgei_R/S/P")
    name = port.strip().lower()
    if auto_nego not in ("enable", "disable"):
        raise ValueError("Auto negotiation harus enable atau disable")
    if auto_nego == "enable":
        return [f"interface {name}", "negotiation auto", "exit"]
    speed = (speed or "").strip()
    duplex = (duplex or "").strip().lower()
    if speed not in PORT_SPEEDS:
        raise ValueError("Speed harus 10, 100, 1000, atau 10000 Mbps")
    if match.group(1).lower() == "gei" and speed == "10000":
        raise ValueError(f"Port {name} maksimal 1000 Mbps; pakai port xgei untuk 10000 Mbps")
    if duplex not in DUPLEXES:
        raise ValueError("Duplex harus full atau half")
    return [f"interface {name}", "no negotiation auto", f"speed {speed}",
            f"duplex {duplex}", "exit"]


def build_authorize_commands(req: AuthorizeRequest) -> list[str]:
    """Scope MVP otorisasi (DECISIONS "Scope authorize_onu"): onu + type + sn + tcont +
    gemport + service-port. Blok `pon-onu-mng` (flow/switchport-bind/PPPoE) sengaja TIDAK
    dikirim di sini — domainnya Detail ONU. Urutan mengikuti NEXFIBER-CLI-REFERENCE
    "Ubah — Otorisasi ONU": T-CONT dan gemport wajib sebelum `service-port`.

    Pure function supaya bisa diuji tanpa device (fixture test, bukan OLT nyata).
    """
    onu_iface = f"gpon-onu_1/{req.slot}/{req.port}:{req.onu_id}"
    commands = [
        f"interface gpon-olt_1/{req.slot}/{req.port}",
        f"onu {req.onu_id} type {req.onu_type} sn {req.serial_number}",
        "exit",
        f"interface {onu_iface}",
    ]
    if req.name:
        commands.append(f"name {req.name}")
    if req.description:
        commands.append(f"description {req.description}")
    if req.upload_profile:
        commands.append(f"tcont 1 profile {req.upload_profile}")
        commands.append("gemport 1 tcont 1")
    if req.download_profile:
        commands.append(f"gemport 1 traffic-limit downstream {req.download_profile}")
    if req.vlan_id:
        commands.append(
            f"service-port 1 vport 1 user-vlan {req.vlan_id} vlan {req.vlan_id}"
        )
    commands.append("exit")
    return commands

def _parse_slot_port(iface: str) -> tuple[int, int]:
    # "gpon-olt_1/3/6" -> rack is always 1 in these transcripts; slot=3, port=6.
    rack_slot_port = iface.split("_", 1)[1]
    _rack, slot, port = rack_slot_port.split("/")
    return int(slot), int(port)

_UNCFG_ROW_RE = re.compile(r"(?:gpon-onu_)?(\d+/\d+/\d+):\d+\s+(\S+)(?:\s+(\S+))?")
# Format asli (verifikasi live, driver SmartOLT): "gpon-onu_1/2/1:1  <SN>  <type>" —
# prefiks "gpon-onu_", bukan "gpon-olt_" seperti dugaan lama (parser lama tidak pernah
# match apa pun dari device nyata; Rx tidak ada di baris ini, ONU belum punya SNMP index).

def _parse_unconfigured(output: str) -> list[UnconfiguredOnu]:
    onus: list[UnconfiguredOnu] = []
    for line in output.splitlines():
        m = _UNCFG_ROW_RE.search(line)
        if m:
            slot, port = _parse_slot_port(f"gpon-onu_{m.group(1)}")
            onus.append(UnconfiguredOnu(slot=slot, port=port, serial_number=m.group(2),
                                         onu_type=m.group(3)))
    return onus

# Baris `show gpon onu state`: "1/6/1:7     enable       disable      DyingGasp    1(GPON)"
# (transkrip nyata OLT SBI C300, read-only 2026-10-24).
_ONU_STATE_ROW_RE = re.compile(
    r"^\s*(\d+)/(\d+)/(\d+):(\d+)\s+(\S+)\s+\S+\s+(\S+)", re.M
)
# Baris `show gpon onu baseinfo gpon-olt_<pon>`:
# "gpon-onu_1/6/1:2    HG8145V5    sn      SN:HWTC2FB2BAB2         ready"
_ONU_BASEINFO_ROW_RE = re.compile(
    r"^\s*gpon-onu_(\d+)/(\d+)/(\d+):(\d+)\s+(\S+)\s+\S+\s+SN:(\S+)", re.M
)
# Stanza `interface gpon-onu_<rack>/<slot>/<port>:<id>` di `show running-config`, isinya
# baris-baris berindentasi sampai baris tak berindentasi berikutnya (transkrip nyata
# OLT SBI C300, read-only 2026-10-24).
_ONU_IFACE_STANZA_RE = re.compile(
    r"^interface gpon-onu_(\d+)/(\d+)/(\d+):(\d+)[ \t]*\n((?:[ \t]+.*\n)*)", re.M
)
_ONU_CFG_NAME_RE = re.compile(r"^[ \t]+name[ \t]+(\S.*)$", re.M)
_ONU_CFG_DESCR_RE = re.compile(r"^[ \t]+description[ \t]+(\S.*)$", re.M)

def _parse_onu_state(output: str) -> list[OnuSnapshot]:
    """`show gpon onu state` (semua PON atau satu PON) -> posisi + status + admin state.
    serial_number diisi belakangan dari baseinfo; command ini tidak memuat SN.
    """
    snapshots: list[OnuSnapshot] = []
    for m in _ONU_STATE_ROW_RE.finditer(output):
        _rack, slot, port, onu_id, admin, phase = m.groups()
        snapshots.append(OnuSnapshot(
            slot=int(slot), port=int(port), onu_id=int(onu_id), serial_number="",
            status=PHASE_TEXT_TO_STATUS.get(phase.lower(), "unknown"),
            admin_state="enabled" if admin.lower() == "enable" else "disabled",
        ))
    return snapshots

def _parse_onu_baseinfo(output: str) -> dict[tuple[int, int, int], tuple[str, str | None]]:
    """`show gpon onu baseinfo gpon-olt_<pon>` -> {(slot, port, onu_id): (SN, tipe)}."""
    rows: dict[tuple[int, int, int], tuple[str, str | None]] = {}
    for m in _ONU_BASEINFO_ROW_RE.finditer(output):
        _rack, slot, port, onu_id, onu_type, serial = m.groups()
        rows[(int(slot), int(port), int(onu_id))] = (serial, onu_type)
    return rows

def _parse_onu_metadata(output: str) -> dict[tuple[int, int, int], tuple[str | None, str | None]]:
    """`show running-config` -> {(slot, port, onu_id): (name, description)}.

    Stanza nyata (OLT SBI C300, read-only 2026-10-24; 39/39 ONU punya kedua baris):

        interface gpon-onu_1/6/2:1
          name <teks bebas>
          description <teks bebas>
          tcont 1 profile ...

    Keduanya teks bebas yang diisi operator — TIDAK diparsing lebih jauh di sini.
    Pemetaan ke nama pelanggan/alamat ditentukan di layer sync, dan zone/splitter TIDAK
    diturunkan dari sini karena perangkat tidak punya field itu (lihat sync_service).
    """
    rows: dict[tuple[int, int, int], tuple[str | None, str | None]] = {}
    for m in _ONU_IFACE_STANZA_RE.finditer(output):
        _rack, slot, port, onu_id, body = m.groups()
        name = _ONU_CFG_NAME_RE.search(body)
        desc = _ONU_CFG_DESCR_RE.search(body)
        rows[(int(slot), int(port), int(onu_id))] = (
            name.group(1).strip() if name else None,
            desc.group(1).strip() if desc else None,
        )
    return rows

def _parse_vlan_summary(output: str) -> list[int]:
    """`show vlan summary`: "All created vlan num: 6" lalu baris id "1,15,19,68,100,3045".
    Rentang "10-12" juga diterima (format ZXROS yang sama saat id berurutan).
    """
    vlans: set[int] = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or ":" in line or line.startswith("%") or line.endswith("#"):
            continue
        if not re.fullmatch(r"[\d,\s-]+", line):
            continue
        for token in line.replace(" ", "").split(","):
            if not token:
                continue
            if "-" in token:
                lo, _, hi = token.partition("-")
                if lo.isdigit() and hi.isdigit():
                    vlans.update(range(int(lo), int(hi) + 1))
            elif token.isdigit():
                vlans.add(int(token))
    return sorted(v for v in vlans if 1 <= v <= 4094)

def _parse_onu_ids(output: str) -> list[int]:
    ids: list[int] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "onu" and parts[1].isdigit() and parts[2] == "type":
            ids.append(int(parts[1]))
    return ids

def _parse_onu_iface(iface: str) -> tuple[int, int, int]:
    # "gpon-onu_1/3/6:59" -> slot=3, port=6, onu_id=59.
    rack_slot_port, onu_id = iface.split("_", 1)[1].split(":")
    _rack, slot, port = rack_slot_port.split("/")
    return int(slot), int(port), int(onu_id)

def _kbps_after(parts: list[str], keyword: str) -> int | None:
    # "... maximum 100000" / "... pir 100000"; absent or non-numeric -> unknown, not 0.
    if keyword not in parts:
        return None
    value = parts[parts.index(keyword) + 1 :]
    return int(value[0]) if value and value[0].isdigit() else None

def _parse_traffic_profiles(output: str) -> list[TrafficProfile]:
    """Lines of `show running-config | include profile tcont|traffic`:
        profile tcont PAKET20_UP type 5 fixed 64 assured 64 maximum 20000
        profile traffic PAKET20_DN sir 1000 pir 20000
    """
    profiles: list[TrafficProfile] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] != "profile":
            continue
        if parts[1] == "tcont":
            profiles.append(TrafficProfile(parts[2], "upload", _kbps_after(parts, "maximum")))
        elif parts[1] == "traffic":
            profiles.append(TrafficProfile(parts[2], "download", _kbps_after(parts, "pir")))
    return profiles

# --- Kesehatan OLT -----------------------------------------------------------------
# Format kolom dikonfirmasi lewat driver produksi ZTE C320 lain (/var/www/smartolt.*,
# 2026-10-24), bukan dugaan dokumentasi publik lagi. `show version-running` masih belum
# punya sumber verifikasi kedua, tetap toleran: baris yang tak cocok dilewati saja.

def _as_float(token: str) -> float | None:
    try:
        return float(token.rstrip("%"))
    except ValueError:
        return None

_CARD_ROW_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S.*\S)\s*$")
# Transkrip nyata (OLT SBI, 2026-10-24, read-only, lihat NEXFIBER-CLI-REFERENCE.md):
# kolom RealType/HardVer/SoftVer masing-masing BISA kosong SENDIRI-SENDIRI (tidak
# selalu bareng), dan Port tetap ada walau RealType kosong. Makanya diparse dari token
# tengah secara posisional, bukan regex kolom tetap seperti dugaan sebelumnya.

def _parse_cards(output: str) -> list[OltCard]:
    """`show card`, kolom: Rack Shelf Slot CfgType [RealType] Port [HardVer] [SoftVer] Status."""
    cards: list[OltCard] = []
    for line in output.splitlines():
        m = _CARD_ROW_RE.match(line)
        if not m:
            continue
        rack, shelf, slot, rest = m.groups()
        if not (rack.isdigit() and shelf.isdigit() and slot.isdigit()):
            continue
        tokens = rest.split()
        if len(tokens) < 2:
            continue
        status = tokens[-1]
        mid = tokens[:-1]
        cfg_type = mid[0]
        port_idx = next((i for i, t in enumerate(mid[1:], start=1) if t.isdigit()), None)
        if port_idx is None:
            continue
        real_type = mid[1] if port_idx == 2 else None
        port_count = int(mid[port_idx])
        versions = mid[port_idx + 1:]
        hardware_version = versions[0] if versions else None
        software_version = versions[1] if len(versions) > 1 else None
        cards.append(OltCard(
            slot=int(slot), cfg_type=cfg_type, real_type=real_type or cfg_type,
            port_count=port_count, hardware_version=hardware_version,
            software_version=software_version, status=status.lower(),
        ))
    return cards

_PROCESSOR_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)\s+(\d+)%"
)
# Transkrip nyata (OLT SBI, 2026-10-24, read-only): Rack Shelf Slot CPU(5s) CPU(1m)
# CPU(5m) PhyMem(MB) Memory(%) — CPU "sekarang" = CPU(5s), RAM = kolom Memory terakhir.

def _parse_processor(output: str) -> dict[int, tuple[float | None, float | None]]:
    """`show processor` -> {slot: (cpu_pct, ram_pct)}."""
    load: dict[int, tuple[float | None, float | None]] = {}
    for line in output.splitlines():
        m = _PROCESSOR_ROW_RE.match(line)
        if not m:
            continue
        load[int(m.group(3))] = (_as_float(m.group(4)), _as_float(m.group(8)))
    return load

def _merge_card_load(
    cards: list[OltCard], load: dict[int, tuple[float | None, float | None]]
) -> list[OltCard]:
    for card in cards:
        card.cpu_pct, card.ram_pct = load.get(card.slot, (None, None))
    # Slot yang hanya muncul di `show processor` tetap ditampilkan, biar CPU/RAM main
    # control tidak hilang kalau parsing `show card` meleset.
    known = {c.slot for c in cards}
    for slot, (cpu, ram) in sorted(load.items()):
        if slot not in known:
            cards.append(OltCard(slot=slot, cpu_pct=cpu, ram_pct=ram))
    return sorted(cards, key=lambda c: c.slot)

def _parse_software_version(output: str) -> str | None:
    """`show version-running`: kolom nyata PhyLoc FileType VerType VerTag BuildTime
    VerLength (transkrip OLT SBI, 2026-10-24, read-only) — bukan satu baris "Version
    full name:" seperti dugaan lama. Ambil VerTag dari baris VerType=MVR pertama
    (firmware utama slot); kalau tidak ada format itu, coba pola lama sebagai fallback.
    """
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "MVR":
            return parts[3][:100]
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or "#" in stripped:  # "#" = prompt CLI, bukan baris data
            continue
        lowered = stripped.lower()
        if "version" in lowered or stripped.startswith("ZXA10"):
            value = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped
            if value:
                return value[:100]
    return None

# --- Detail ONU: parser keluaran CLI ------------------------------------------------
# UNVERIFIED: perintahnya ✅ terverifikasi di NEXFIBER-CLI-REFERENCE.md, tapi `detail-info`
# dan `attenuation` masih belum ada transkrip nyata di repo ini (equip SUDAH, lihat
# tests/fixtures/cli/zte_show_gpon_remote_onu_equip.txt, OLT SBI 2026-10-24). Parser di
# bawah mencari "Label : value" apa adanya dan melewati baris yang tidak cocok — ganti
# dengan parsing berdasarkan transkrip nyata dari ONU test sebelum dipercaya penuh.

def _kv(line: str) -> tuple[str, str] | None:
    """"Phase state        : working" -> ("phase state", "working")."""
    if ":" not in line:
        return None
    label, _, value = line.partition(":")
    label, value = label.strip().lower(), value.strip()
    return (label, value) if label and value else None

def _dbm(value: str) -> float | None:
    # "-22.106(dbm)" / "-22.11 dBm" / "-22.11"
    token = value.split("(")[0].split()[0] if value else ""
    try:
        return round(float(token), 2)
    except ValueError:
        return None

def _meters(value: str) -> int | None:
    # "1832 m" / "1.83(km)"
    token = value.split("(")[0].split()[0] if value else ""
    try:
        number = float(token)
    except ValueError:
        return None
    return int(number * 1000) if "km" in value.lower() else int(number)

ONU_DETAIL_FIELDS = {
    "phase state": "phase_state",
    "onu state": "status",
    "run state": "status",
    "online duration": None,  # format jam:menit:detik tidak seragam, lihat _duration_seconds
}

def _duration_seconds(value: str) -> int | None:
    """"12 day 04:31:22" / "04:31:22" -> detik. Format lain -> None."""
    days = 0
    rest = value
    if "day" in value:
        head, _, rest = value.partition("day")
        try:
            days = int(head.strip())
        except ValueError:
            return None
    parts = rest.strip().split(":")
    if len(parts) != 3 or not all(p.strip().isdigit() for p in parts):
        return None
    h, m, s = (int(p) for p in parts)
    return days * 86400 + h * 3600 + m * 60 + s

def _parse_onu_detail_info(output: str) -> OnuLiveDetail:
    """`show gpon onu detail-info gpon-onu_<pon>:<id>`."""
    detail = OnuLiveDetail()
    for line in output.splitlines():
        pair = _kv(line)
        if pair is None:
            continue
        label, value = pair
        if label in ("phase state", "onu state", "run state"):
            # phase_state = apa adanya dari OLT; status dipetakan terpisah oleh service.
            detail.phase_state = detail.phase_state or value
        elif "online duration" in label or label == "uptime":
            detail.online_duration_s = _duration_seconds(value)
        elif "rx optical power" in label or label == "onu rx power":
            detail.rx_power_dbm = _dbm(value)
        elif "tx optical power" in label or label == "onu tx power":
            detail.tx_power_dbm = _dbm(value)
        elif "olt rx" in label:
            detail.olt_rx_power_dbm = _dbm(value)
        elif "temperature" in label:
            detail.temperature_c = _dbm(value)
        elif "voltage" in label or "supply voltage" in label:
            detail.voltage_v = _dbm(value)
        elif label in ("onu distance", "distance", "fiber length"):
            detail.distance_m = _meters(value)
        elif "hardware version" in label:
            detail.hardware_version = value[:50]
        elif "software version" in label and detail.software_version is None:
            detail.software_version = value[:50]
    return detail

def _parse_attenuation(output: str, rx: float | None, tx: float | None,
                       olt_rx: float | None) -> tuple[float | None, float | None, float | None]:
    """`show pon power attenuation`: isi hanya yang masih kosong dari detail-info.

    Label ZTE: `OltRxOnuTx` = daya yang diterima OLT (olt_rx), `OnuRxOltTx` = daya yang
    diterima ONU (rx). Nilai dari detail-info selalu menang. Format baris alternatif
    (verifikasi live, driver SmartOLT): "1490nm Tx: <tx> Rx: <rx>" (arah ONU) dan
    "1310nm Rx: <olt_rx>" (arah OLT) — dicoba sebagai fallback kedua.
    """
    for line in output.splitlines():
        pair = _kv(line)
        if pair is None:
            continue
        label, value = pair
        label = label.replace(" ", "").replace("-", "").replace("_", "")
        if "oltrx" in label:
            olt_rx = olt_rx if olt_rx is not None else _dbm(value)
        elif "onurx" in label:
            rx = rx if rx is not None else _dbm(value)
        elif "onutx" in label or label.endswith("tx"):
            tx = tx if tx is not None else _dbm(value)
    if rx is None or tx is None:
        m = re.search(r"1490nm\s+Tx\s*:\s*(\S+)\s+Rx\s*:\s*([-]?\d+\.?\d*)", output, re.I)
        if m:
            tx = tx if tx is not None else _dbm(m.group(1))
            rx = rx if rx is not None else _dbm(m.group(2))
    if olt_rx is None:
        m = re.search(r"1310nm\s+Rx\s*:\s*([-]?\d+\.?\d*)", output, re.I)
        if m:
            olt_rx = _dbm(m.group(1))
    return rx, tx, olt_rx

def _parse_equip(output: str,
                 hardware: str | None) -> tuple[str | None, str | None, str | None]:
    """`show gpon remote-onu equip`: versi SW aktif + versi HW.

    Transkrip nyata OLT SBI (C300, 2026-10-24) tidak punya label "software version"/
    "standby version" sama sekali — field yang ada: "Version" (firmware aktif ONU) dan
    "Model"/"Equipment ID" (tipe hardware). OLT ini tidak melaporkan versi standby lewat
    command ini, jadi standby selalu None.
    """
    active = standby = None
    for line in output.splitlines():
        pair = _kv(line)
        if pair is None:
            continue
        label, value = pair
        if "standby" in label and "version" in label:
            standby = value[:50]
        elif ("active" in label or "running" in label) and "version" in label:
            active = value[:50]
        elif label in ("software version", "sw version", "version") and active is None:
            active = value[:50]
        elif "hardware version" in label or label == "hw version":
            hardware = hardware or value[:50]
        elif label == "model" and hardware is None:
            hardware = value[:50]
    return active, standby, hardware
