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
    DriverResult,
    ModifyRequest,
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

    async def test_connection(self) -> DriverResult:
        async with self._open_cli() as cli:
            output = await cli.send_command("show version")
            return self._result("show version", output)

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
        iface = f"gpon-olt_1/{req.slot}/{req.port}"
        onu_iface = f"gpon-onu_1/{req.slot}/{req.port}:{req.onu_id}"
        commands = [
            f"interface {iface}",
            f"onu {req.onu_id} type {req.onu_type} sn {req.serial_number}",
            "exit",
            f"interface {onu_iface}",
        ]
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
