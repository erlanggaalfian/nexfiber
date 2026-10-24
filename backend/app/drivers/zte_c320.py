"""ZTE ZXA10 C300/C320 driver (PRD 4.3). MVP's only vendor implementation.

Command templates for authorize/modify/backup_config were built from real running-config
transcripts captured off a production ZTE C320 (gpon-onu interface blocks). Commands for
list_unconfigured/delete/set_state/reboot/fetch_inventory use the vendor's publicly
documented CLI syntax (ZXA10 C300/C320 command reference) because no real transcript was
available for those operations — mark as UNVERIFIED until confirmed against a live device,
and replace tests/fixtures/cli/zte_unconfigured.txt etc. with real output before production use.
"""

from app.drivers.base import OltDriver
from app.drivers.errors import ZTE_ERROR_PATTERNS, is_error_output
from app.drivers.transport.snmp import SnmpTransport
from app.drivers.transport.ssh import SshTransport
from app.drivers.transport.telnet import TelnetTransport
from app.drivers.types import (
    AuthorizeRequest,
    ConnectionCheck,
    DriverResult,
    ModifyRequest,
    OltCard,
    OltHealth,
    OnuLiveDetail,
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
# Nama interface uplink ZTE di ifDescr: gei_1/5/1 (GE), xgei_1/5/1 (10GE).
UPLINK_PREFIXES = ("gei_", "xgei_", "gei-", "xgei-")

# Optical power OIDs (ZTE enterprise MIB). UNVERIFIED like list_unconfigured/delete/
# set_state/reboot/fetch_inventory above — community-sourced (public GitHub monitoring
# script, not official ZTE MIB docs or a real transcript); confirm against a live SNMP
# walk before trusting the values in production.
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

# ONU phase-state + PON ifindex layout. UNVERIFIED (community-sourced, not official ZTE MIB);
# correct here once a real snmpwalk from the OLT is available — nothing else hardcodes these.
#   - phase-state table indexed by <pon_ifindex>.<onu_index>.
#   - pon_ifindex = BASE + slot * SLOT_MUL + port * PORT_MUL (gpon-olt_1/1/1 -> 268501248).
#   - unmapped values (logging, syncMib, authFailed) are transitional -> "unknown".
OID_ONU_PHASE_STATE = "1.3.6.1.4.1.3902.1012.3.28.2.1.4"
PON_IFINDEX_BASE = 268435456
PON_IFINDEX_SLOT_MUL = 65536
PON_IFINDEX_PORT_MUL = 256
PHASE_STATE_TO_STATUS = {2: "los", 4: "online", 5: "dying_gasp", 7: "offline"}

def decode_pon_ifindex(ifindex: int) -> tuple[int, int]:
    rest = ifindex - PON_IFINDEX_BASE
    return rest // PON_IFINDEX_SLOT_MUL, (rest % PON_IFINDEX_SLOT_MUL) // PON_IFINDEX_PORT_MUL

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
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    if raw == 2147483647:
        return None
    dbm = round((10000 - raw // 10) / 100, 2)
    return dbm if -60 <= dbm <= 10 else None

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
        cls = SshTransport if self._cli_protocol == "ssh" else TelnetTransport
        return cls(
            host=self._host,
            username=self._cli_username,
            password=self._cli_password,
            port=self._cli_port,
            secret=self._cli_enable_password,
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
        command = "show version"
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

    async def list_unconfigured(self) -> list[UnconfiguredOnu]:
        # UNVERIFIED: public syntax, no real transcript available (see module docstring).
        command = "show gpon onu uncfg"
        async with self._open_cli() as cli:
            output = await cli.send_command(command)
        onus: list[UnconfiguredOnu] = []
        for line in output.splitlines():
            parts = line.split()
            # Expected columns (public docs): gpon-olt_1/3/6  <sn>  [onu_type]
            if len(parts) >= 2 and parts[0].startswith("gpon-olt_"):
                slot, port = _parse_slot_port(parts[0])
                onus.append(UnconfiguredOnu(slot=slot, port=port, serial_number=parts[1],
                                             onu_type=parts[2] if len(parts) > 2 else None))
        return onus

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

    async def fetch_inventory(self) -> list[OnuSnapshot]:
        # UNVERIFIED: public syntax.
        command = "show gpon onu state"
        async with self._open_cli() as cli:
            output = await cli.send_command(command)
        snapshots: list[OnuSnapshot] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0].startswith("gpon-onu_"):
                slot, port, onu_id = _parse_onu_iface(parts[0])
                snapshots.append(OnuSnapshot(slot=slot, port=port, onu_id=onu_id,
                                              serial_number=parts[1], status=parts[2].lower()))
        return snapshots

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
            row_slot, row_port = decode_pon_ifindex(pon_ifindex)
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

    async def create_traffic_profiles(
        self, name: str, download_kbps: int, upload_kbps: int
    ) -> DriverResult:
        # NEXFIBER-CLI-REFERENCE "Ubah — Profile kecepatan / Buat profile baru".
        commands = [
            "gpon",
            f"profile tcont {name}_UP type 5 fixed 64 assured 64 maximum {upload_kbps}",
            f"profile traffic {name}_DN sir {download_kbps} pir {download_kbps}",
            "exit",
        ]
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
        return ports

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

        Keempat perintah ✅ terverifikasi di NEXFIBER-CLI-REFERENCE.md ("Baca — ONU");
        yang belum terverifikasi adalah *format keluarannya* — tidak ada satu pun
        transkrip `detail-info`/`attenuation`/`equip` di repo, jadi parser di bawah
        toleran: field yang tidak cocok tetap None, bukan bikin job gagal.
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
# UNVERIFIED: `show card`, `show processor` dan `show version-running` tercatat
# "terverifikasi" di NEXFIBER-CLI-REFERENCE.md sebagai perintah, tetapi tidak ada satu pun
# transkrip keluarannya di repo ini. Parser di bawah mengikuti format kolom ZXA10 yang
# terdokumentasi publik dan sengaja dibuat toleran: baris yang tidak cocok dilewati, bukan
# bikin job gagal. Ganti dengan parsing berdasarkan transkrip nyata sebelum dipercaya penuh.

def _as_float(token: str) -> float | None:
    try:
        return float(token.rstrip("%"))
    except ValueError:
        return None

def _parse_cards(output: str) -> list[OltCard]:
    """`show card`, kolom: Rack Shelf Slot CfgType RealType Port HardVer SoftVer Status."""
    cards: list[OltCard] = []
    for line in output.splitlines():
        parts = line.split()
        # Baris data diawali tiga angka (rack, shelf, slot); header/pemisah tidak.
        if len(parts) < 5 or not all(p.isdigit() for p in parts[:3]):
            continue
        port_count = next((int(p) for p in parts[5:6] if p.isdigit()), None)
        cards.append(OltCard(
            slot=int(parts[2]),
            cfg_type=parts[3],
            real_type=parts[4],
            port_count=port_count,
            hardware_version=parts[6] if len(parts) > 6 else None,
            software_version=parts[7] if len(parts) > 7 else None,
            status=parts[-1].lower() if len(parts) > 8 else None,
        ))
    return cards

def _parse_processor(output: str) -> dict[int, tuple[float | None, float | None]]:
    """`show processor`, kolom: Slot CPU(%) Peak Memory(%) ... -> {slot: (cpu, ram)}."""
    load: dict[int, tuple[float | None, float | None]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        numbers = [v for v in (_as_float(p) for p in parts[1:]) if v is not None]
        if not numbers:
            continue
        # Kolom kedua = CPU sekarang, kolom terakhir = memory; peak di antaranya diabaikan.
        load[int(parts[0])] = (numbers[0], numbers[-1] if len(numbers) > 1 else None)
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
    """`show version-running`: ambil token versi pertama, mis. "ZXA10 C320 V2.1.0".

    Baris gema prompt (`ZXAN#show version-running`) dilewati — kalau tidak, nilai yang
    tersimpan jadi teks perintah, bukan versi.
    """
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
# UNVERIFIED: perintahnya ✅ terverifikasi di NEXFIBER-CLI-REFERENCE.md, tapi tidak ada
# transkrip keluaran `detail-info` / `attenuation` / `equip` di repo ini. Parser di bawah
# mencari "Label : value" apa adanya dan melewati baris yang tidak cocok — ganti dengan
# parsing berdasarkan transkrip nyata dari ONU test sebelum dipercaya penuh.

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
    diterima ONU (rx). Nilai dari detail-info selalu menang.
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
    return rx, tx, olt_rx

def _parse_equip(output: str,
                 hardware: str | None) -> tuple[str | None, str | None, str | None]:
    """`show gpon remote-onu equip`: versi SW aktif/standby + versi HW (tab Info software)."""
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
        elif label in ("software version", "sw version") and active is None:
            active = value[:50]
        elif "hardware version" in label or label == "hw version":
            hardware = hardware or value[:50]
    return active, standby, hardware
