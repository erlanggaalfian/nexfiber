"""`GET /api/onus/{serial}/traffic` — snapshot counter LIVE per ONU (SNMP read-only).

Router terpisah dari `onus.py` supaya track ini tidak bentrok dengan agent diagnostics
yang sedang memegang file itu. Prefix sama (`/api/onus`), jadi path tetap satu keluarga.

Semua role boleh (counter saja, bukan kredensial) tapi **tetap dibatasi scope OLT**:
ONU milik Admin lain -> 404 (ditegakkan di service lewat `rbac.scope_olt_ids`).
Response `no-store`: angka live tidak boleh nyangkut di cache browser/proxy.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.onu_traffic import OnuTrafficPoint, OnuTrafficSample
from app.services import onu_traffic_service
from app.services import onu_traffic_history_service as history_service

router = APIRouter(prefix="/api/onus", tags=["onus"])


@router.get("/{serial}/traffic/history", response_model=list[OnuTrafficPoint])
async def onu_traffic_history(
    serial: str,
    range: Literal["24h", "7d", "30d"] = "24h",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    """Titik grafik `Traffic history` dari sampel yang sudah tersimpan (tanpa menyentuh
    OLT). Rentang mengikuti endpoint sinyal (`/{serial}/signal`). Daftar kosong = sampler
    memang belum punya sampel untuk ONU ini, bukan error."""
    return await history_service.history(db, serial, range, user)


@router.get("/{serial}/traffic", response_model=OnuTrafficSample)
async def onu_traffic(
    serial: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnuTrafficSample:
    response.headers["Cache-Control"] = "no-store"
    return await onu_traffic_service.read_sample(db, serial, user)
