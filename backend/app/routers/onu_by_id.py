"""`GET /api/onus/by-id/{onu_id}` — Detail ONU berdasarkan **id internal DB**.

Alasan ada: URL UI tidak boleh memuat serial number (`/onu/BDCMB1E3F750`); rute
`/onu/:id` sekarang memakai `onus.id` yang stabil dan tidak berubah saat ONU
di-replace/di-rename. API operasional (job, info, signal, logs, traffic) TETAP berkunci
serial — endpoint ini hanya pintu masuk halaman detail, yang lalu memakai
`serial_number` dari responsnya untuk semua aksi.

Router terpisah dari `onus.py` (prefix sama, jadi tetap satu keluarga path) karena file
itu sedang dipegang track lain. Juga harus di-include SEBELUM `onus.router` supaya
`/by-id/...` tidak ketelan path parameter `/{serial}`.

Tidak ada logika scope/baris baru: pembacaannya memakai `onu_service.get_onu` lewat
resolver `onu_repo.get_row_by_serial` yang sama — ONU di luar scope OLT atau id yang
tidak ada = 404, sama seperti endpoint ONU lain.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.rbac import scope_olt_ids
from app.models.user import User
from app.repositories import onu_repo
from app.schemas.onu import OnuDetail
from app.services import onu_service

router = APIRouter(prefix="/api/onus", tags=["onus"])


@router.get("/by-id/{onu_id}", response_model=OnuDetail)
async def get_onu_by_id(onu_id: int, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)) -> OnuDetail:
    """id -> serial (dalam scope OLT), lalu detail dibaca lewat jalur yang sama dengan
    `GET /api/onus/{serial}`. Penerjemahan id sengaja eksplisit: ONU dengan serial
    berupa angka tidak boleh pernah tertukar dengan id ONU lain."""
    serial = await onu_repo.get_serial_by_id(db, onu_id, scope_olt_ids(user))
    if serial is None:
        raise NotFoundError(f"ONU {onu_id} not found")
    return await onu_service.get_onu(db, serial, user)
