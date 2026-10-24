"""Plain data objects passed between driver and service (PRD 4.3). Driver never touches
the DB; service maps these into/out of SQLAlchemy models.
"""

from dataclasses import dataclass


@dataclass
class DriverResult:
    success: bool
    raw_command: str
    raw_output: str
    message: str = ""


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
    loid: str | None = None
    password: str | None = None
    line_profile_id: str | None = None
    srv_profile_id: str | None = None
    vlan_id: int | None = None

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
