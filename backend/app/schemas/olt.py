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
    """Omitted fields stay unchanged; secrets are only overwritten when sent."""

    name: str | None = Field(None, min_length=1, max_length=100)
    host: IPv4Address | None = None
    cli_protocol: str | None = Field(None, pattern="^(ssh|telnet)$")
    cli_port: int | None = Field(None, ge=1, le=65535)
    cli_username: str | None = Field(None, min_length=1, max_length=100)
    cli_password: str | None = Field(None, min_length=1)
    cli_enable_password: str | None = None
    snmp_community: str | None = Field(None, min_length=1)
    snmp_community_rw: str | None = None
    snmp_port: int | None = Field(None, ge=1, le=65535)
    pon_port_count: int | None = Field(None, ge=1, le=128)
    max_onu_per_port: int | None = Field(None, ge=1, le=256)
    location: str | None = Field(None, max_length=255)
    is_active: bool | None = None

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

class PonPortOut(BaseModel):
    id: int
    slot: int
    port: int
    ifindex: int | None
    oper_state: str | None
    onu_count: int
    capacity: int
    last_sync_at: datetime | None

class JobAccepted(BaseModel):
    job_id: int
