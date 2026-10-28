from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, SetupRequest, SetupStatus, TokenResponse
from app.services import auth_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class ChangePasswordRequest(BaseModel):
    """Skema lokal di router (bukan schemas/auth.py) supaya endpoint ini tidak
    bergantung pada file di luar kepemilikan area ini. Aturan sama dengan
    UserCreate: password baru min 12, maks 128."""

    old_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

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

@router.post("/logout", status_code=204)
async def logout(db: AsyncSession = Depends(get_db),
                 user: User = Depends(get_current_user),
                 token: str = Depends(oauth2_scheme)) -> None:
    """Logout server-side: jti token ini dicatat di daftar revoked (tabel
    settings) sehingga deps menolaknya pada request berikutnya, meski belum
    kedaluwarsa. Idempotent: token yang sudah tidak valid tetap dijawab 204
    bila user-nya masih lolos get_current_user; token tanpa jti (diterbitkan
    sebelum perubahan ini) tidak punya apa-apa untuk dicatat — ia hanya bisa
    dicabut lewat ganti password, dan kedaluwarsa sendiri maksimal 8 jam.
    Frontend tetap harus membuang token dari localStorage-nya sendiri."""
    try:
        payload = decode_access_token(token)
    except Exception:
        return
    jti, exp = payload.get("jti"), payload.get("exp")
    if isinstance(jti, str) and isinstance(exp, (int, float)):
        await auth_service.record_token_jti(db, auth_service.REVOKED_TOKENS_KEY, jti, exp)
        await db.commit()


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user

@router.post("/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)) -> None:
    """Ganti password mandiri untuk user yang sedang login (semua role).

    Ini jalan keluar yang membuat penegakan must_change_password di frontend
    tidak menjadi jebakan: login tetap berhasil, tapi RequireAuth menampilkan
    form ganti password sampai flag dibersihkan, dan endpoint ini tidak
    membutuhkan manager. Password lama wajib benar; token lama otomatis
    tercabut karena password_hash berubah (klaim "ph" di deps).
    """
    await auth_service.change_password(db, user, body.old_password, body.new_password)
