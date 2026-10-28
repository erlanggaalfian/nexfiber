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


# Potongan command+output yang dibawa ke result job supaya UI bisa menampilkan jejak CLI
# live setelah aksi push (bukan histori Logs). Dibatasi supaya JSONB result tidak membesar.
DEBUG_LOG_LIMIT = 4000


def debug_log(result: "DriverResult") -> dict:
    """Jejak CLI satu aksi push: command yang dikirim + respons mentah OLT."""
    return {
        "command": result.raw_command[:DEBUG_LOG_LIMIT],
        "output": result.raw_output[:DEBUG_LOG_LIMIT],
        "success": result.success,
    }


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
    # Info sistem SNMP standar (sysName/sysLocation) — dibaca di siklus health yang sama,
    # bukan endpoint/job sendiri.
    sys_name: str | None = None
    sys_location: str | None = None


@dataclass
class InterfaceStatus:
    """Satu port uplink fisik apa adanya dari perangkat (tab Interfaces, PRD 3.4.7 butir 2
    "edit port: auto-negotiation, speed, duplex"). Dibaca live, tidak disimpan ke DB.
    """

    name: str
    media: str | None = None
    pvid: int | None = None
    auto_nego: str | None = None  # "enable" | "disable"
    speed: str | None = None  # "auto" atau angka Mbps apa adanya
    duplex: str | None = None
    flow_ctrl: str | None = None
    admin_status: str | None = None
    link: str | None = None  # "up" | "down"



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
class OnuReport:
    """Satu panel output diagnostik ONU (tombol Status / Running config / Info SW).

    `output` = teks final siap tampil (blok + judul), dirakit di backend supaya tidak ada
    formatter kedua di frontend. `view` = nama tombolnya.
    """

    view: str  # "status" | "running" | "software"
    output: str
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
    # Nama profile di perangkat, dengan arah yang eksplisit (bukan line/srv lama):
    # upload -> tcont, download -> gemport traffic-limit, sama seperti authorize.
    upload_profile: str | None = None
    download_profile: str | None = None
    vlan_id: int | None = None

@dataclass
class OnuSnapshot:
    slot: int
    port: int
    onu_id: int
    serial_number: str
    status: str
    # `name`/`description` = dua field metadata yang MEMANG ada di interface ONU perangkat
    # (ZTE: baris `name ...` dan `description ...` di running-config). Diteruskan apa adanya;
    # pemetaan ke nama pelanggan/alamat/zone TIDAK ditebak di driver.
    name: str | None = None
    description: str | None = None
    onu_type: str | None = None
    admin_state: str | None = None  # "enabled" | "disabled" (nilai enum onus.admin_state)
    # Dari stanza `pon-onu-mng` running-config; None = ONU tanpa PPPoE di perangkat.
    pppoe_username: str | None = None
    pppoe_password: str | None = None
    # VLAN WAN nyata dari `flow 1 ... vlan N` di stanza `pon-onu-mng`; None = tidak dilaporkan.
    wan_vlan: int | None = None
    # Semua kandidat flow ber-ip-host; layer service memilih VLAN bertipe management.
    management_ips: list[tuple[int, str, str | None]] | None = None


@dataclass
class OltInventory:
    """Isi nyata OLT yang dibaca read-only dalam satu sesi CLI: ONU yang sudah
    terdaftar (configured) + VLAN yang ada di perangkat.
    """

    onus: list[OnuSnapshot]
    vlan_ids: list[int]

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
class OnuProvisioning:
    """Provisioning satu ONU yang dibaca lewat SNMP (bukan CLI): profil kecepatan per arah,
    VLAN layanan, dan jarak. Nama profil dikembalikan APA ADANYA seperti di perangkat.
    """

    slot: int
    port: int
    onu_id: int
    upload_profile: str | None = None
    download_profile: str | None = None
    vlan_ids: list[int] = field(default_factory=list)
    distance_m: int | None = None


@dataclass
class OltProvisioning:
    """Satu kali baca SNMP untuk seluruh OLT: katalog profil perangkat + provisioning
    tiap ONU. Dipakai rantai onboarding supaya tidak ada walk per-PON berulang.
    """

    profiles: list["TrafficProfile"]
    onus: list[OnuProvisioning]


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
