from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.signal import BUCKETS

# Bucket RX: nilainya dari app.core.signal (satu definisi untuk seluruh backend).
SignalBucket = Literal[BUCKETS]  # type: ignore[valid-type]
OnuStatus = Literal["online", "offline", "los", "dying_gasp", "power_off", "unknown"]
# Asal nilai mode ONU/WAN yang dikirim ke UI: "cli" = benar-benar terbaca dari
# running-config OLT, "default" = tidak ada di CLI sehingga dipakai default pemilik.
ModeSource = Literal["cli", "default"]
# Default pemilik saat mode tidak terbaca di CLI (DECISIONS.md): Routing + webpage.
# Hanya untuk tampilan/nilai awal modal; tidak pernah disimpan ke kolom `onus`.
DEFAULT_ONU_MODE = "routing"
DEFAULT_WAN_MODE = "webpage"


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
    download_profile_name: str | None
    upload_profile_name: str | None
    vlan_number: int | None
    zone_name: str | None
    splitter_name: str | None
    last_seen_at: datetime | None
    last_down_at: datetime | None
    last_down_reason: str | None

class OnuServiceVlan(BaseModel):
    """Satu VLAN layanan NYATA di perangkat (dari `service-port` ONU).

    `vlan_id` = nomor VLAN di perangkat (bukan id baris `vlans`) — sengaja beda dari
    `OnuDetail.vlan_id` yang FK master, karena VLAN perangkat belum tentu terdaftar.
    `in_master=False` = ada di perangkat tapi belum ada di master; tetap dikirim apa
    adanya, bukan dibuang. `is_management` HANYA dari `vlans.type == "management"` —
    tidak ada nomor VLAN yang di-hardcode sebagai management.
    """

    vlan_id: int
    name: str | None = None
    is_management: bool = False
    in_master: bool = False


class DeviceMetadataOut(BaseModel):
    zone: str | None = None
    address: str | None = None
    splitter: str | None = None
    contact: str | None = None
    external_id: str | None = None
    authorized_on: str | None = None
    structured: bool = False


class OnuDetail(OnuRow):
    pppoe_password: str | None = None  # hanya diisi untuk role manager
    pon_port_id: int
    auth_type: str
    loid: str | None
    match_state: str | None
    bias_current_ma: float | None
    last_sync_at: datetime | None
    preset_id: int | None
    preset_name: str | None
    onu_type_id: int | None
    registered_by_name: str | None
    description: str | None
    address: str | None
    phone: str | None
    contact: str | None
    external_id: str | None
    tx_power_dbm: float | None
    temperature_c: float | None
    voltage_v: float | None
    distance_m: int | None
    mac_address: str | None
    ip_address: str | None
    # IP WAN dari host laporan ip-host di VLAN NON-management (chip "Setup WAN");
    # None = belum terbaca/tidak bisa dipasangkan — bukan IP management.
    wan_ip_address: str | None = None
    vlan_id: int | None
    zone_id: int | None
    splitter_id: int | None
    splitter_port: int | None
    download_speed_profile_id: int | None
    upload_speed_profile_id: int | None
    line_profile_id: str | None
    srv_profile_id: str | None
    software_version: str | None
    hardware_version: str | None
    # Mode EFEKTIF yang dipakai UI: hasil baca CLI/running-config bila ada, kalau tidak
    # terbaca memakai default pemilik (routing + webpage). Default TIDAK pernah ditulis ke
    # DB sebagai hasil CLI palsu — hanya diisi di respons ini, dan `*_source` menyebut
    # asalnya ("cli" | "default"). Kelak sumber ketiga (TR-069) ikut lewat jalur yang sama.
    onu_mode: str | None
    wan_mode: str | None
    # VLAN WAN nyata perangkat (`flow 1 ... vlan N`), nomor VLAN apa adanya — bukan FK
    # master dan bukan diambil dari `service_vlans`. None = perangkat tidak melaporkannya.
    wan_vlan: int | None = None
    onu_mode_source: ModeSource = "cli"
    wan_mode_source: ModeSource = "cli"
    mgmt_ip_mode: str | None
    mgmt_vlan: int | None = None  # nomor VLAN management, bukan FK `onus.vlan_id`
    pppoe_username: str | None
    latitude: float | None
    longitude: float | None
    registered_at: datetime | None
    # VLAN layanan terpasang di perangkat, DAFTAR. `None` = belum pernah disinkron
    # (UI harus bilang "belum tersedia", bukan menampilkan daftar kosong karangan);
    # `[]` = ONU memang tidak punya service-port. Sumber centang awal modal
    # "Update attached VLANs" dan VLAN WAN "Update ONU mode".
    service_vlans: list[OnuServiceVlan] | None = None
    # Hasil parse `description` perangkat (read-only, sumber kedua saat kolom
    # master kosong; frontend sudah menampilkannya dengan label asal).
    device_metadata: DeviceMetadataOut | None = None
    # Konfigurasi port terakhir ditulis Nexfiber (lihat model Onu.port_configs).
    # None = belum pernah ditulis; UI melabelinya sebagai itu, bukan sebagai
    # hasil baca perangkat.
    port_configs: dict | None = None

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

ONU_MODES = "^(routing|bridging)$"
WAN_MODES = "^(webpage|dhcp|static|pppoe)$"


class AuthorizeBody(BaseModel):
    """Form Otorisasi (PRD 3.4.4). `vlan_id` = id baris tabel `vlans` (dropdown VLAN
    existing, DECISIONS "Scope authorize_onu"), bukan nomor VLAN."""

    olt_id: int
    serial_number: str = Field(min_length=4, max_length=32)
    customer_id: str = Field(min_length=1, max_length=50)
    customer_name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(None, max_length=500)
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=128)
    phone: str | None = Field(None, max_length=30)
    contact: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=50)
    onu_type: str | None = Field(None, max_length=50)
    onu_type_id: int | None = None
    vlan_id: int | None = None
    download_speed_profile_id: int | None = None
    upload_speed_profile_id: int | None = None
    line_profile_id: str | None = Field(None, max_length=50)
    srv_profile_id: str | None = Field(None, max_length=50)
    zone_id: int | None = None
    splitter_id: int | None = None
    splitter_port: int | None = Field(None, ge=1)
    preset_id: int | None = None
    onu_mode: str | None = Field(None, pattern=ONU_MODES)
    wan_mode: str | None = Field(None, pattern=WAN_MODES)
    pppoe_username: str | None = Field(None, max_length=100)
    pppoe_password: str | None = Field(None, max_length=100)  # disimpan terenkripsi
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    onu_index: int | None = Field(None, ge=1, description="Empty = smallest free ID on the OLT")

class StateBody(BaseModel):
    enabled: bool

class OnuInfoBody(BaseModel):
    """Edit data pelanggan/lokasi di Detail ONU (PRD 3.4.6 "bisa diedit lewat dialog kecil").

    Hanya kolom database — tidak ada perintah ke OLT, jadi bukan job. Field yang
    mengubah konfigurasi perangkat (speed, VLAN, SN) tetap lewat endpoint job masing-masing.
    """

    customer_name: str | None = Field(None, max_length=255)
    customer_id: str | None = Field(None, max_length=50)
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=128)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=30)
    contact: str | None = Field(None, max_length=100)
    external_id: str | None = Field(None, max_length=50)
    zone_id: int | None = None
    splitter_id: int | None = None
    splitter_port: int | None = Field(None, ge=1)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)

class SpeedProfileBody(BaseModel):
    """Body endpoint "Ubah speed" (PATCH .../speed-profile) — boleh ganti satu arah saja,
    download/upload independen, bukan paket gabungan lagi (Opsi A)."""

    download_speed_profile_id: int | None = None
    upload_speed_profile_id: int | None = None

class VlanBody(BaseModel):
    """`vlan_id` = id baris tabel `vlans`, bukan nomor VLAN (konsisten dengan AuthorizeBody)."""

    vlan_id: int

class ReplaceOnuBody(BaseModel):
    """Ganti ONU: SN baru menggantikan SN lama, data pelanggan di baris yang sama tetap."""

    serial_number: str = Field(min_length=4, max_length=32)
    onu_type: str | None = Field(None, max_length=50)

class DiagnosticBody(BaseModel):
    """Tombol diagnostik Detail ONU. Satu endpoint, tiga view read-only.

    `running` memuat kredensial pelanggan → dibatasi role manager di service.
    """

    view: Literal["status", "running", "software"]

BULK_ACTIONS = ("reboot_onu", "resync_onu", "set_state", "apply_speed_profile",
                "set_onu_vlan", "delete_onu")

class BulkActionBody(BaseModel):
    """Aksi massal tabel Configured (PRD 3.4.5): satu job per ONU, bukan satu job gabungan."""

    serials: list[str] = Field(min_length=1, max_length=200)
    action: Literal[BULK_ACTIONS]  # type: ignore[valid-type]
    enabled: bool | None = None          # untuk set_state
    download_speed_profile_id: int | None = None  # untuk apply_speed_profile
    upload_speed_profile_id: int | None = None    # untuk apply_speed_profile
    vlan_id: int | None = None           # untuk set_onu_vlan

class BulkActionItem(BaseModel):
    serial_number: str
    job_id: int | None
    error: str | None

class BulkActionResult(BaseModel):
    """Per-serial, supaya UI bisa menunjukkan ONU mana yang gagal tanpa menebak."""

    items: list[BulkActionItem]
    queued: int
    failed: int

class SignalPoint(BaseModel):
    sampled_at: datetime
    rx_power_dbm: float | None
    tx_power_dbm: float | None
    olt_rx_power_dbm: float | None
    status: str
    source: str | None = None

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
    direction: Literal["download", "upload"]
    speed_kbps: int
    olt_id: int | None
    device_profile_id: str | None

    model_config = {"from_attributes": True}
