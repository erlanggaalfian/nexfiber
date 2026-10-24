"""Zone / ONU type / Splitter payloads (PRD 3.4.10, 3.4.11, 4.6). One module: the three
entities share validation vocabulary (ratio, koordinat) and are edited from the same pages.
"""

from pydantic import BaseModel, Field

PON_TYPES = "^(gpon|epon|xgpon|xgspon)$"
CAPABILITIES = "^(bridging|bridging_routing)$"
SPLITTER_TYPES = "^(odc|odp)$"
RATIOS = ("1:2", "1:4", "1:8", "1:16", "1:32", "1:64")
RATIO_PATTERN = "^1:(2|4|8|16|32|64)$"

LAT = Field(None, ge=-90, le=90)
LON = Field(None, ge=-180, le=180)


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    external_id: str | None = Field(None, max_length=50)
    latitude: float | None = LAT
    longitude: float | None = LON


class ZoneUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    external_id: str | None = Field(None, max_length=50)
    latitude: float | None = LAT
    longitude: float | None = LON


class ZoneOut(BaseModel):
    id: int
    owner_id: int
    name: str
    external_id: str | None
    latitude: float | None
    longitude: float | None
    splitter_count: int
    onu_count: int


class OnuTypeCreate(BaseModel):
    pon_type: str = Field("gpon", pattern=PON_TYPES)
    name: str = Field(min_length=1, max_length=100)
    eth_ports: int = Field(1, ge=0, le=32)
    wifi_ssids: int = Field(0, ge=0, le=32)
    voip_ports: int = Field(0, ge=0, le=32)
    catv: bool = False
    capability: str = Field("bridging", pattern=CAPABILITIES)
    allow_custom_profiles: bool = False
    is_active: bool = True


class OnuTypeUpdate(BaseModel):
    pon_type: str | None = Field(None, pattern=PON_TYPES)
    name: str | None = Field(None, min_length=1, max_length=100)
    eth_ports: int | None = Field(None, ge=0, le=32)
    wifi_ssids: int | None = Field(None, ge=0, le=32)
    voip_ports: int | None = Field(None, ge=0, le=32)
    catv: bool | None = None
    capability: str | None = Field(None, pattern=CAPABILITIES)
    allow_custom_profiles: bool | None = None
    is_active: bool | None = None


class OnuTypeOut(BaseModel):
    id: int
    pon_type: str
    name: str
    eth_ports: int
    wifi_ssids: int
    voip_ports: int
    catv: bool
    capability: str
    allow_custom_profiles: bool
    is_active: bool
    onu_count: int


class SplitterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field("odp", pattern=SPLITTER_TYPES)
    ratio: str = Field("1:8", pattern=RATIO_PATTERN)
    zone_id: int  # zone menentukan pemilik splitter (PRD 3.4.11)
    parent_id: int | None = None  # ODC -> ODP
    olt_id: int | None = None
    pon_port_id: int | None = None
    code: str | None = Field(None, max_length=50)
    location: str | None = Field(None, max_length=255)
    latitude: float | None = LAT
    longitude: float | None = LON
    insertion_loss_db: float | None = Field(None, ge=0, le=99)
    notes: str | None = Field(None, max_length=500)


class SplitterUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    type: str | None = Field(None, pattern=SPLITTER_TYPES)
    ratio: str | None = Field(None, pattern=RATIO_PATTERN)
    zone_id: int | None = None
    parent_id: int | None = None
    olt_id: int | None = None
    pon_port_id: int | None = None
    code: str | None = Field(None, max_length=50)
    location: str | None = Field(None, max_length=255)
    latitude: float | None = LAT
    longitude: float | None = LON
    insertion_loss_db: float | None = Field(None, ge=0, le=99)
    notes: str | None = Field(None, max_length=500)


class SplitterOut(BaseModel):
    id: int
    name: str
    code: str | None
    type: str
    ratio: str | None
    capacity: int | None
    zone_id: int | None
    zone_name: str | None
    parent_id: int | None
    parent_name: str | None
    olt_id: int | None
    pon_port_id: int | None
    location: str | None
    latitude: float | None
    longitude: float | None
    insertion_loss_db: float | None
    notes: str | None
    onu_count: int


class SplitterOnu(BaseModel):
    id: int
    serial_number: str
    name: str | None
    customer_name: str | None
    splitter_port: int | None


class SplitterDetail(SplitterOut):
    onus: list[SplitterOnu]
