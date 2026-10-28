"""Settings -> Graph Data: retensi otomatis + hapus manual data graph per ONU."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

GraphKind = Literal["traffic", "signal"]


class GraphStat(BaseModel):
    kind: GraphKind
    rows: int
    oldest_at: datetime | None
    newest_at: datetime | None
    # Ukuran tabel + indexnya (pg_total_relation_size): selalu seluruh tabel, bukan
    # per cakupan OLT — satu tabel dipakai semua Admin.
    size_bytes: int | None


class GraphRetention(BaseModel):
    """Hari sampel disimpan; 0 = retensi otomatis nonaktif."""

    traffic: int
    signal: int


class GraphDeleteRequest(BaseModel):
    kinds: list[GraphKind] = Field(min_length=1)
    # Tanggal dibaca zona WIB, inklusif seluruh hari (lihat graph_data_service).
    date_from: date
    date_to: date
    olt_id: int | None = None


class GraphDeleteByOlt(BaseModel):
    """Satu baris rincian per OLT: nama OLT (None bila OLT sudah terhapus dan
    namanya tidak lagi terbaca) + jumlah per jenis + totalnya."""

    olt_id: int
    olt_name: str | None
    deleted: dict[str, int]
    total: int


class GraphDeleteResult(BaseModel):
    """Jumlah baris per jenis + totalnya (dipakai pratinjau maupun hapus),
    plus rincian per OLT untuk pratinjau "Semua OLT" (dan untuk hapus,
    rincian yang benar-benar terhapus per OLT)."""

    deleted: dict[str, int]
    total: int
    by_olt: list[GraphDeleteByOlt] = []
