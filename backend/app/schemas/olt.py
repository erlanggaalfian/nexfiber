from datetime import datetime
from ipaddress import IPv4Address

from pydantic import BaseModel, Field


class OltCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: IPv4Address
    vendor: str = "zte"
    model: str = "C320"
    cli_protocol: str = Field("ssh", pattern="^(ssh|telnet)$")
    cli_port: int = Field(22, ge=1, le=65535)
    cli_username: str = Field(min_length=1, max_length=100)
    cli_password: str = Field(min_length=1)
    cli_enable_password: str | None = None
    snmp_community: str = Field(min_length=1)
    snmp_community_rw: str | None = None
    snmp_port: int = Field(161, ge=1, le=65535)
    pon_port_count: int = Field(16, ge=1, le=128)
    max_onu_per_port: int = Field(128, ge=1, le=256)
    location: str | None = Field(None, max_length=255)
    owner_id: int | None = None  # Superadmin only; Admin always owns what it creates (PRD 3.7)

class OltUpdate(BaseModel):
    """Omitted fields stay unchanged; secrets are only overwritten when sent non-empty
    (blank password field in the form = keep the stored credential, PRD 3.4.8)."""

    name: str | None = Field(None, min_length=1, max_length=100)
    host: IPv4Address | None = None
    cli_protocol: str | None = Field(None, pattern="^(ssh|telnet)$")
    cli_port: int | None = Field(None, ge=1, le=65535)
    cli_username: str | None = Field(None, min_length=1, max_length=100)
    cli_password: str | None = None
    cli_enable_password: str | None = None
    snmp_community: str | None = None
    snmp_community_rw: str | None = None
    snmp_port: int | None = Field(None, ge=1, le=65535)
    pon_port_count: int | None = Field(None, ge=1, le=128)
    max_onu_per_port: int | None = Field(None, ge=1, le=256)
    location: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    owner_id: int | None = None  # Superadmin only: pindah pemilik OLT (PRD 3.7 aturan 4)

class OltTestRequest(BaseModel):
    """Cek koneksi sebelum simpan (PRD 3.4.8). Tanpa id: pakai nilai di form."""

    host: IPv4Address
    snmp_community: str = Field(min_length=1)
    snmp_port: int = Field(161, ge=1, le=65535)

class OltTestResult(BaseModel):
    success: bool
    message: str

class OltOut(BaseModel):
    """Never exposes credentials, encrypted or not."""

    id: int
    name: str
    host: IPv4Address
    vendor: str
    model: str
    firmware_version: str | None
    cli_protocol: str
    cli_port: int
    cli_username: str
    snmp_port: int
    pon_port_count: int
    max_onu_per_port: int
    location: str | None
    status: str
    last_sync_at: datetime | None
    last_error: str | None
    is_active: bool
    owner_id: int

    model_config = {"from_attributes": True}

class OltRow(OltOut):
    """List row for OLT Management (PRD 3.4.8): adds owner name + ONU count."""

    owner_name: str
    onu_count: int

class PonPortOut(BaseModel):
    id: int
    slot: int
    port: int
    ifindex: int | None
    oper_state: str | None
    onu_count: int
    capacity: int
    last_sync_at: datetime | None

class OltCardOut(BaseModel):
    """Satu baris olts.cards (JSONB). Bentuknya mengikuti drivers.types.OltCard."""

    slot: int
    cfg_type: str | None = None
    real_type: str | None = None
    port_count: int | None = None
    hardware_version: str | None = None
    software_version: str | None = None
    status: str | None = None
    cpu_pct: float | None = None
    ram_pct: float | None = None

class OltDetail(OltOut):
    """Satu panggilan untuk seluruh halaman Detail OLT (PRD 3.4.7): identitas + kesehatan
    + PON + ringkasan ONU. Nama port uplink diambil dari pon_ports/cards yang sudah
    disinkron job sync_olt_metrics, bukan panggilan langsung ke perangkat.
    """

    owner_name: str
    onu_count: int
    onu_by_status: dict[str, int]
    cpu_pct: float | None
    ram_pct: float | None
    temperature_c: float | None
    uptime_seconds: int | None
    software_version: str | None
    cards: list[OltCardOut]
    pon_ports: list[PonPortOut]
    uplink_ports: list[str]

class JobAccepted(BaseModel):
    job_id: int
