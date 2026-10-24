"""Plain data objects passed between driver and service (PRD 4.3). Driver never touches
the DB; service maps these into/out of SQLAlchemy models.
"""

from dataclasses import dataclass, field


@dataclass
class DriverResult:
    success: bool
    raw_command: str
    raw_output: str
    message: str = ""


@dataclass
class ConnectionCheck:
    """Hasil tes koneksi: CLI dan SNMP diuji TERPISAH, masing-masing boolean sendiri.

    DECISIONS "Audit fitur SmartOLT": status satu protokol tidak boleh ditentukan dari
    mencocokkan teks pesan protokol lain — itu bug nyata di SmartOLT. Setiap field di
    sini berasal dari percobaan protokolnya sendiri.
    """

    cli_ok: bool
    snmp_ok: bool
    cli_message: str = ""
    snmp_message: str = ""
    raw_command: str = ""
    raw_output: str = ""


@dataclass
class OltCard:
    """Satu kartu/board seperti dilaporkan `show card` (disimpan apa adanya ke olts.cards)."""

    slot: int
    cfg_type: str | None = None
    real_type: str | None = None
    port_count: int | None = None
    hardware_version: str | None = None
    software_version: str | None = None
    status: str | None = None
    cpu_pct: float | None = None
    ram_pct: float | None = None


@dataclass
class OltHealth:
    """Kesehatan OLT untuk tab Monitoring (PRD 3.4.7). cpu/ram = kartu main control."""

    cpu_pct: float | None = None
    ram_pct: float | None = None
    temperature_c: float | None = None
    uptime_seconds: int | None = None
    software_version: str | None = None
    cards: list[OltCard] = field(default_factory=list)
    uplink_ports: list[str] = field(default_factory=list)



@dataclass
class OnuLiveDetail:
    """Hasil baca live satu ONU (PRD 3.4.6 tab Status / Running config / Info software).

    Semua field opsional: parser CLI sengaja toleran, field yang tidak ketemu tetap None
    supaya job "Cek ulang" tidak gagal hanya karena format keluaran berbeda sedikit.
    """

    phase_state: str | None = None
    status: str | None = None
    rx_power_dbm: float | None = None
    tx_power_dbm: float | None = None
    olt_rx_power_dbm: float | None = None
    temperature_c: float | None = None
    voltage_v: float | None = None
    distance_m: int | None = None
    software_version: str | None = None
    software_version_standby: str | None = None
    hardware_version: str | None = None
    online_duration_s: int | None = None
    running_config: str = ""
    raw_command: str = ""


@dataclass
class UnconfiguredOnu:
    slot: int
    port: int
    serial_number: str
    onu_type: str | None = None

@dataclass
class AuthorizeRequest:
    slot: int
    port: int
    onu_id: int
    serial_number: str
    auth_type: str  # "sn" | "loid" | "password"
    # ZTE "onu <id> type <X> sn <sn>" needs the ONU's model string, not a fixed value — real
    # transcripts show "ALL-ONT" (generic/auto), "ONU-type-eth-4-pots-2-catv-0", "HG8245H5".
    # "ALL-ONT" works as a safe default when the exact model is unknown (e.g. discovery
    # didn't report one), but callers should pass through UnconfiguredOnu.onu_type when set.
    onu_type: str = "ALL-ONT"
    name: str = ""
    description: str | None = None
    loid: str | None = None
    password: str | None = None
    # Nama profile di device: upload = T-CONT, download = traffic (speed_profile_service
    # menamainya <profile>_UP / <profile>_DN saat push ke OLT).
    upload_profile: str | None = None
    download_profile: str | None = None
    vlan_id: int | None = None  # nomor VLAN 1..4094, bukan id baris tabel vlans

@dataclass
class ModifyRequest:
    slot: int
    port: int
    onu_id: int
    name: str | None = None
    line_profile_id: str | None = None
    srv_profile_id: str | None = None
    vlan_id: int | None = None

@dataclass
class OnuSnapshot:
    slot: int
    port: int
    onu_id: int
    serial_number: str
    status: str
    description: str | None = None

@dataclass
class OnuStatusSample:
    slot: int
    port: int
    onu_id: int
    status: str  # one of onus.status enum values

@dataclass
class PonPortInfo:
    slot: int
    port: int
    ifindex: int | None = None


@dataclass
class TrafficProfile:
    """One upload (T-CONT) or download (traffic) profile as the OLT reports it."""

    name: str
    direction: str  # "upload" | "download"
    kbps: int | None = None


@dataclass
class OpticalSample:
    slot: int
    port: int
    onu_id: int
    rx_power_dbm: float | None = None
    tx_power_dbm: float | None = None
    olt_rx_power_dbm: float | None = None
    temperature_c: float | None = None
    voltage_v: float | None = None
    bias_current_ma: float | None = None
