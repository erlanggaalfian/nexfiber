from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.olt import JobAccepted
from app.schemas.onu import (
    AuthorizeBody,
    BulkActionBody,
    BulkActionItem,
    BulkActionResult,
    OnuDetail,
    OnuLog,
    OnuPage,
    OnuStatus,
    PendingOnu,
    ReplaceOnuBody,
    SignalBucket,
    SignalPoint,
    SpeedProfileBody,
    StateBody,
    VlanBody,
)
from app.services import olt_service, onu_service

router = APIRouter(prefix="/api/onus", tags=["onus"])
ACCEPTED = {"response_model": JobAccepted, "status_code": status.HTTP_202_ACCEPTED}

@router.get("", response_model=OnuPage)
async def list_onus(
    q: str | None = None,
    olt_id: int | None = None,
    pon_port_id: int | None = None,
    state: Literal["online", "down", "rx_warn", "not_configured"] | None = None,
    speed_profile_id: int | None = None,
    signal: list[SignalBucket] | None = Query(None, description="Filter bucket RX, bisa banyak"),
    onu_status: list[OnuStatus] | None = Query(None, alias="status"),
    vlan_id: int | None = None,
    zone_id: int | None = None,
    splitter_id: int | None = None,
    onu_type: str | None = None,
    sort: str = "serial",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await onu_service.search_onus(
        db, user, q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
        speed_profile_id=speed_profile_id, sort=sort, page=page, size=size,
        signal=signal, status=onu_status, vlan_id=vlan_id, zone_id=zone_id,
        splitter_id=splitter_id, onu_type=onu_type,
    )
    return OnuPage(items=items, total=total, page=page, size=size)

@router.get("/export.csv", response_class=Response)
async def export_csv(
    q: str | None = None,
    olt_id: int | None = None,
    pon_port_id: int | None = None,
    state: Literal["online", "down", "rx_warn", "not_configured"] | None = None,
    speed_profile_id: int | None = None,
    signal: list[SignalBucket] | None = Query(None),
    onu_status: list[OnuStatus] | None = Query(None, alias="status"),
    vlan_id: int | None = None,
    zone_id: int | None = None,
    splitter_id: int | None = None,
    onu_type: str | None = None,
    sort: str = "serial",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export CSV mengikuti filter aktif (PRD 3.4.5). Parameternya sama persis dengan
    GET /api/onus kecuali paginasi — seluruh hasil filter diexport, dibatasi CSV_MAX.
    """
    items, _ = await onu_service.search_onus(
        db, user, q=q, olt_id=olt_id, pon_port_id=pon_port_id, state=state,
        speed_profile_id=speed_profile_id, sort=sort, page=1, size=onu_service.CSV_MAX,
        signal=signal, status=onu_status, vlan_id=vlan_id, zone_id=zone_id,
        splitter_id=splitter_id, onu_type=onu_type,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(
        content=onu_service.csv_bytes(items),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="onu-{stamp}.csv"'},
    )

@router.get("/pending", response_model=list[PendingOnu])
async def list_pending(olt_id: int | None = None, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return await onu_service.list_pending(db, olt_id, user)

@router.post("/pending/rescan", **ACCEPTED)
async def rescan_pending(olt_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """Tombol "Scan ulang" (PRD 3.4.3). Satu OLT per klik; scan otomatis 1 menit tetap jalan."""
    return JobAccepted(job_id=await olt_service.enqueue_olt_job(
        db, olt_id, "sync_unconfigured", user))

@router.get("/customer-id-taken")
async def customer_id_taken(customer_id: str, db: AsyncSession = Depends(get_db),
                            _: User = Depends(get_current_user)) -> dict:
    return {"taken": await onu_service.customer_id_taken(db, customer_id)}

@router.post("/authorize", **ACCEPTED)
async def authorize(body: AuthorizeBody, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return JobAccepted(job_id=await onu_service.create_and_enqueue_authorize(db, body, user))

@router.post("/bulk", response_model=BulkActionResult, status_code=status.HTTP_202_ACCEPTED)
async def bulk_action(body: BulkActionBody, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Aksi massal tabel Configured. Hapus massal butuh role manager (sama dengan DELETE satuan)."""
    if body.action == "delete_onu":
        require_roles(MANAGERS)(user)
    payload = {k: v for k, v in body.model_dump(
        exclude={"serials", "action"}).items() if v is not None} or None
    items = await onu_service.enqueue_bulk(db, body.serials, body.action, user, payload)
    return BulkActionResult(
        items=[BulkActionItem(**i) for i in items],
        queued=sum(1 for i in items if i["job_id"] is not None),
        failed=sum(1 for i in items if i["job_id"] is None),
    )

@router.get("/{serial}", response_model=OnuDetail)
async def get_onu(serial: str, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return await onu_service.get_onu(db, serial, user)

@router.post("/{serial}/refresh", **ACCEPTED)
async def refresh_detail(serial: str, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """Baca ulang live dari OLT (optical, versi, running-config). Read-only, tetap lewat job."""
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(
        db, serial, "refresh_onu_detail", user))

@router.post("/{serial}/resync", **ACCEPTED)
async def resync(serial: str, db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(db, serial, "resync_onu", user))

@router.post("/{serial}/vlan", **ACCEPTED)
async def set_vlan(serial: str, body: VlanBody, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    job_id = await onu_service.enqueue_onu_job(db, serial, "set_onu_vlan", user, body.model_dump())
    return JobAccepted(job_id=job_id)

@router.post("/{serial}/replace", **ACCEPTED)
async def replace(serial: str, body: ReplaceOnuBody, db: AsyncSession = Depends(get_db),
                  user: User = Depends(require_roles(MANAGERS))):
    job_id = await onu_service.enqueue_onu_job(db, serial, "replace_onu", user, body.model_dump())
    return JobAccepted(job_id=job_id)

@router.post("/{serial}/restore-factory", **ACCEPTED)
async def restore_factory(serial: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles(MANAGERS))):
    """Destruktif: ONU kembali ke setelan pabrik. Role manager + konfirmasi di UI."""
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(
        db, serial, "restore_factory", user))

@router.get("/{serial}/signal", response_model=list[SignalPoint])
async def signal(serial: str, range: Literal["24h", "7d", "30d"] = "24h",
                 db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await onu_service.signal_history(db, serial, range, user)

@router.get("/{serial}/logs", response_model=list[OnuLog])
async def logs(serial: str, limit: int = Query(100, ge=1, le=500),
               db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await onu_service.onu_logs(db, serial, limit, user)

@router.post("/{serial}/reboot", **ACCEPTED)
async def reboot(serial: str, db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(db, serial, "reboot_onu", user))

@router.post("/{serial}/state", **ACCEPTED)
async def set_state(serial: str, body: StateBody, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    job_id = await onu_service.enqueue_onu_job(db, serial, "set_state", user, body.model_dump())
    return JobAccepted(job_id=job_id)

@router.post("/{serial}/speed-profile", **ACCEPTED)
async def speed_profile(serial: str, body: SpeedProfileBody, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    job_id = await onu_service.enqueue_onu_job(
        db, serial, "apply_speed_profile", user, body.model_dump()
    )
    return JobAccepted(job_id=job_id)

@router.delete("/{serial}", **ACCEPTED)
async def delete(serial: str, db: AsyncSession = Depends(get_db),
                 user: User = Depends(require_roles(MANAGERS))):
    return JobAccepted(job_id=await onu_service.enqueue_onu_job(db, serial, "delete_onu", user))
