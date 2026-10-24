"""Speed Profile payloads (PRD 3.4.12). Shape list = `app.schemas.onu.SpeedProfileOut`,
dipakai GET /api/speed-profiles; di sini hanya create/update + detail halaman Settings.

Opsi A (TODO Speed Profile pisah Download/Upload): satu baris = satu arah lewat
`direction`, `speed_kbps` menggantikan pasangan download_kbps/upload_kbps lama.
"""

from typing import Literal

from pydantic import BaseModel, Field

KBPS = Field(ge=64, le=10_000_000)
Direction = Literal["download", "upload"]


class SpeedProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    direction: Direction
    speed_kbps: int = KBPS
    olt_id: int | None = None  # NULL = berlaku semua OLT
    vlan_db_id: int | None = None  # id baris tabel vlans (dropdown, read-only di halaman ini)
    description: str | None = Field(None, max_length=255)


class SpeedProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    speed_kbps: int | None = Field(None, ge=64, le=10_000_000)
    olt_id: int | None = None
    vlan_db_id: int | None = None
    description: str | None = Field(None, max_length=255)
    is_active: bool | None = None


class SpeedProfileRow(BaseModel):
    """Baris tabel Settings → Speed Profile: data profile + VLAN terpilih + jumlah ONU."""

    id: int
    name: str
    direction: Direction
    speed_kbps: int
    olt_id: int | None
    olt_name: str | None
    vlan_db_id: int | None
    vlan_id: int | None
    vlan_name: str | None
    device_profile_id: str | None
    description: str | None
    is_active: bool
    onu_count: int
