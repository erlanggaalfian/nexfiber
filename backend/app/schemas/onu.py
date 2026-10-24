from datetime import datetime

from pydantic import BaseModel, Field


class OnuRow(BaseModel):
    id: int
    serial_number: str
    name: str | None
    customer_name: str | None
    customer_id: str | None
    olt_id: int
    olt_name: str
    slot: int
    port: int
    onu_index: int | None
    onu_type: str | None
    status: str
    config_state: str
    admin_state: str
    rx_power_dbm: float | None
    olt_rx_power_dbm: float | None
    speed_profile_name: str | None
    last_seen_at: datetime | None
    last_down_at: datetime | None
    last_down_reason: str | None

class OnuDetail(OnuRow):
    pon_port_id: int
    description: str | None
    address: str | None
    phone: str | None
    tx_power_dbm: float | None
    temperature_c: float | None
    distance_m: int | None
    mac_address: str | None
    ip_address: str | None
    vlan_id: int | None
    speed_profile_id: int | None
    line_profile_id: str | None
    srv_profile_id: str | None
    software_version: str | None
    registered_at: datetime | None

class OnuPage(BaseModel):
    items: list[OnuRow]
    total: int
    page: int
    size: int

class PendingOnu(BaseModel):
    id: int
    olt_id: int
    olt_name: str
    pon_port_id: int
    slot: int
    port: int
    serial_number: str
    onu_type: str | None
    first_seen_at: datetime
    last_seen_at: datetime

class AuthorizeBody(BaseModel):
    olt_id: int
    serial_number: str = Field(min_length=4, max_length=32)
    customer_id: str = Field(min_length=1, max_length=50)
    customer_name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(None, max_length=500)
    name: str | None = Field(None, max_length=100)
    onu_type: str | None = Field(None, max_length=50)
    vlan_id: int | None = None
    speed_profile_id: int | None = None
    line_profile_id: str | None = Field(None, max_length=50)
    srv_profile_id: str | None = Field(None, max_length=50)
    onu_index: int | None = Field(None, ge=1, description="Empty = smallest free ID on the OLT")

class StateBody(BaseModel):
    enabled: bool

class SpeedProfileBody(BaseModel):
    speed_profile_id: int

class SignalPoint(BaseModel):
    sampled_at: datetime
    rx_power_dbm: float | None
    tx_power_dbm: float | None
    olt_rx_power_dbm: float | None
    status: str

    model_config = {"from_attributes": True}

class OnuLog(BaseModel):
    id: int
    created_at: datetime
    username: str | None
    action: str
    success: bool
    job_id: int | None
    raw_command: str | None
    raw_output: str | None


class VlanOut(BaseModel):
    id: int
    olt_id: int | None
    vlan_id: int
    name: str
    type: str
    description: str | None
    gemport: int | None = None
    tag_action: str = "tag"
    user_vlan: int | None = None
    # {"<nama port uplink>": "tagged"|"untagged"} — tab VLANs Detail OLT (PRD 3.4.7).
    uplink_ports: dict[str, str] = {}
    is_active: bool = True

    model_config = {"from_attributes": True}

class SpeedProfileOut(BaseModel):
    id: int
    name: str
    download_kbps: int
    upload_kbps: int
    olt_id: int | None
    line_profile_id: str | None
    srv_profile_id: str | None

    model_config = {"from_attributes": True}
