"""VLAN payloads (DECISIONS: fase ini backend-only; UI CRUD penuh nanti di Detail OLT).

`VlanOut` sengaja TIDAK didefinisikan di sini: shape list VLAN sudah ada di
`app.schemas.onu.VlanOut` dan dipakai GET /api/vlans (dropdown Speed Profile + Form
Otorisasi Fase C). Satu shape saja, jangan dua.
"""

from typing import Literal

from pydantic import BaseModel, Field

VLAN_TYPES = "^(internet|management|voip|iptv|other)$"
TAG_ACTIONS = "^(transparent|translate|tag)$"


class VlanCreate(BaseModel):
    olt_id: int | None = None  # NULL = VLAN global (semua OLT), tanpa push ke device
    vlan_id: int = Field(ge=1, le=4094)
    name: str = Field(min_length=1, max_length=100)
    type: str = Field("internet", pattern=VLAN_TYPES)
    description: str | None = Field(None, max_length=255)
    gemport: int | None = Field(None, ge=1)
    tag_action: str = Field("tag", pattern=TAG_ACTIONS)
    user_vlan: int | None = Field(None, ge=1, le=4094)


class VlanUpdate(BaseModel):
    """Edit VLAN dari tab VLANs Detail OLT. vlan_id dan olt_id tidak bisa diubah: itu
    identitas objek di perangkat — ganti berarti hapus lalu buat lagi.
    """

    name: str | None = Field(None, min_length=1, max_length=100)
    type: str | None = Field(None, pattern=VLAN_TYPES)
    description: str | None = Field(None, max_length=255)
    gemport: int | None = Field(None, ge=1)
    tag_action: str | None = Field(None, pattern=TAG_ACTIONS)
    user_vlan: int | None = Field(None, ge=1, le=4094)


class VlanPorts(BaseModel):
    """{nama_port_uplink: "tagged"|"untagged"}; port yang hilang dari map = tidak disentuh."""

    ports: dict[str, Literal["tagged", "untagged"]]
