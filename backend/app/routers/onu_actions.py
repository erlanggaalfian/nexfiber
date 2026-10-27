"""`/api/onus/{onu_id}/...` — aksi & konfigurasi ONU (semua modal SmartOLT).

Kontrak (frontend bergantung, nama field TIDAK boleh berubah):
  GET  /api/onus/{id}/actions        -> {actions:[{kind, supported, writes_device, note?}]}
  GET  /api/onus/{id}/config-options -> isi dropdown semua modal
  PUT  /api/onus/{id}/location       -> OnuDetail (hanya DB Nexfiber, tanpa perangkat)
  POST /api/onus/{id}/refresh-ip     -> {ip_address: str|null} (read-only, satu perintah)
  POST /api/onus/{id}/actions/{kind} -> {ok, executed, detail, commands:[str tanpa sandi]}

Router terpisah dari `onus.py` (yang berkunci serial) karena kontrak ini berkunci id DB.
Harus di-include SEBELUM `onus.router` supaya `/{id}/...` tidak ketelan `/{serial}`.
Kind yang sintaksnya belum terbukti di perangkat -> 501, tidak pernah dikarang.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.onu import OnuDetail
from app.services import onu_action_service

router = APIRouter(prefix="/api/onus", tags=["onu-actions"])


class LocationBody(BaseModel):
    """Update location details — tidak ada perintah ke OLT, jadi tanpa `confirm`."""

    zone_id: int | None = None
    splitter_id: int | None = None
    splitter_port: int | None = Field(None, ge=1)
    sector_id: int | None = None
    name: str | None = Field(None, max_length=100)
    address: str | None = Field(None, max_length=500)
    contact: str | None = Field(None, max_length=100)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class ActionResult(BaseModel):
    ok: bool
    executed: bool
    detail: str
    commands: list[str] = []
    job_id: int | None = None


@router.get("/{onu_id}/actions")
async def list_actions(onu_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)) -> dict:
    return await onu_action_service.list_actions(db, onu_id, user)


@router.get("/{onu_id}/config-options")
async def config_options(onu_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)) -> dict:
    return await onu_action_service.config_options(db, onu_id, user)


@router.post("/{onu_id}/refresh-ip")
async def refresh_ip(onu_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    """IP ONU terbaca perangkat untuk tautan Detail ONU; read-only, tanpa `confirm`."""
    return await onu_action_service.refresh_ip(db, onu_id, user)


@router.put("/{onu_id}/location", response_model=OnuDetail)
async def update_location(onu_id: int, body: LocationBody,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)) -> OnuDetail:
    return await onu_action_service.update_location(
        db, onu_id, body.model_dump(exclude_none=True), user)


ActionKind = Literal[
    "attached-vlans", "onu-mode", "eth-port", "wifi-port", "wifi-clear", "external-id",
    "onu-type", "speed-profile", "move", "replace-sn", "mgmt-ip", "voip-enable",
    "voip-disable", "iptv", "reboot", "disable", "enable", "restore-factory",
    "resync-config", "delete",
]


@router.post("/{onu_id}/actions/{kind}", response_model=ActionResult)
async def run_action(onu_id: int, kind: ActionKind, body: dict, response: Response,
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)) -> ActionResult:
    """Body bebas per kind (divalidasi di service/pembangun perintah).

    `commands` pada respons SELALU sudah diredaksi — password WiFi/PPPoE tidak pernah
    keluar dari backend. no-store supaya tidak tertinggal di cache browser/proxy.
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await onu_action_service.run_action(db, onu_id, kind, body or {}, user)
    except NotImplementedError as exc:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return ActionResult(ok=False, executed=False, detail=str(exc))
    return ActionResult(**result)
