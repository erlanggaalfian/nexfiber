from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, SetupRequest, SetupStatus, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    ip = request.client.host if request.client else "-"
    token = await auth_service.login(db, body.username, body.password, ip)
    return TokenResponse(access_token=token)

@router.get("/setup", response_model=SetupStatus)
async def setup_status(db: AsyncSession = Depends(get_db)) -> SetupStatus:
    return SetupStatus(needed=await auth_service.needs_setup(db))

@router.post("/setup", response_model=TokenResponse)
async def setup(body: SetupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if not await auth_service.needs_setup(db):
        raise NotFoundError("Not found")
    token = await auth_service.setup(db, body.username, body.full_name, body.password)
    return TokenResponse(access_token=token)

@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
