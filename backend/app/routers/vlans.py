"""VLAN endpoints. UI CRUD penuh ada di Detail OLT tab VLANs (DECISIONS); GET juga dipakai
dropdown Speed Profile dan Form Otorisasi (Fase C).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.rbac import MANAGERS
from app.models.user import User
from app.schemas.onu import VlanOut
from app.schemas.vlan import VlanCreate, VlanPorts, VlanUpdate
from app.services import vlan_service

router = APIRouter(prefix="/api/vlans", tags=["vlans"])
manager = require_roles(MANAGERS)


class VlanCreated(VlanOut):
    job_id: int | None = None  # NULL = VLAN global, tidak ada push ke OLT


@router.get("", response_model=list[VlanOut])
async def list_vlans(olt_id: int | None = None, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    return await vlan_service.list_vlans(db, olt_id, user)


@router.post("", response_model=VlanCreated, status_code=status.HTTP_201_CREATED)
async def create_vlan(body: VlanCreate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(manager)):
    vlan, job_id = await vlan_service.create_vlan(db, body, user)
    return VlanCreated(**VlanOut.model_validate(vlan).model_dump(), job_id=job_id)


@router.patch("/{vlan_db_id}", response_model=VlanOut)
async def update_vlan(vlan_db_id: int, body: VlanUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(manager)):
    return await vlan_service.update_vlan(db, vlan_db_id, body, user)


@router.put("/{vlan_db_id}/ports", status_code=status.HTTP_202_ACCEPTED)
async def set_ports(vlan_db_id: int, body: VlanPorts, db: AsyncSession = Depends(get_db),
                    user: User = Depends(manager)) -> dict:
    """Tagged/untagged port uplink -> job push (AGENTS.md: sentuh OLT selalu lewat job)."""
    return {"job_id": await vlan_service.set_ports(db, vlan_db_id, dict(body.ports), user)}


@router.delete("/{vlan_db_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_vlan(vlan_db_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(manager)) -> dict:
    return {"job_id": await vlan_service.delete_vlan(db, vlan_db_id, user)}
