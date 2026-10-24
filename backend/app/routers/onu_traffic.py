"""`GET /api/onus/{serial}/traffic` — snapshot counter LIVE per ONU (SNMP read-only).

Router terpisah dari `onus.py` supaya track ini tidak bentrok dengan agent diagnostics
yang sedang memegang file itu. Prefix sama (`/api/onus`), jadi path tetap satu keluarga.

Semua role boleh (counter saja, bukan kredensial) tapi **tetap dibatasi scope OLT**:
ONU milik Admin lain -> 404 (ditegakkan di service lewat `rbac.scope_olt_ids`).
Response `no-store`: angka live tidak boleh nyangkut di cache browser/proxy.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.onu_traffic import OnuTrafficSample
from app.services import onu_traffic_service

router = APIRouter(prefix="/api/onus", tags=["onus"])


@router.get("/{serial}/traffic", response_model=OnuTrafficSample)
async def onu_traffic(
    serial: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnuTrafficSample:
    response.headers["Cache-Control"] = "no-store"
    return await onu_traffic_service.read_sample(db, serial, user)
