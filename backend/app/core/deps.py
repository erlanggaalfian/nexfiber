from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_access_token, password_token_claim
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db),
    request: Request = None,  # type: ignore[assignment] — FastAPI menyuntik Request di sini
) -> User:
    # Penegakan must_change_password di server (bukan hanya di frontend):
    # user dengan flag ini hanya boleh memanggil POST /api/auth/change-password
    # (jalan keluarnya), GET /api/auth/me (yang dipakai frontend untuk
    # mendeteksi flag), dan POST /api/auth/logout (logout harus selalu bisa).
    # Endpoint lain menjawab 403, bukan 401, supaya jelas
    # ini bukan token yang salah. Catatan: FastAPI menolak `Request | None`
    # sebagai parameter dependency (dianggap field Pydantic), jadi parameter
    # ini ditulis `Request = None` agar tetap bisa disuntik; pemanggilan
    # langsung tanpa Request tetap menegakkan (tidak bisa dibuktikan sebagai
    # pengecualian).
    exempt = False
    if request is not None:
        path, method = request.url.path, request.method
        exempt = (method == "POST" and path == "/api/auth/change-password") \
            or (method == "GET" and path == "/api/auth/me") \
            or (method == "POST" and path == "/api/auth/logout")
    return await _user_from_token(db, token, enforce_must_change=not exempt)

async def get_user_from_query_token(token: str, db: AsyncSession = Depends(get_db)) -> User:
    """For EventSource, which cannot send an Authorization header (PRD 4.5.C SSE).

    TIDAK LAGI dipakai jalur SSE: stream kini hanya menerima token SSE sekali
    pakai lewat jobs.py (bukan token akses di query string). Fungsi ini
    dipertahankan supaya import lama tidak pecah, tapi jangan dipakai lagi
    untuk autentikasi query-token baru.
    """
    return await _user_from_token(db, token)

async def _user_from_token(db: AsyncSession, token: str,
                           enforce_must_change: bool = False) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError, AttributeError) as exc:
        # Token malformed (mis. tanpa sub / sub bukan angka) sebelumnya lolos
        # sebagai 500 dari int()/KeyError; itu harus 401, bukan 500.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid") from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak ditemukan atau nonaktif")
    # Revokasi minimal tanpa kolom DB baru: token yang membawa klaim "ph" harus
    # cocok dengan password_hash saat ini. Reset/ganti password mengubah hash,
    # sehingga semua token lama otomatis ditolak. Token tanpa klaim (diterbitkan
    # sebelum perubahan ini, dan token test) tetap diterima sampai kedaluwarsa.
    ph = payload.get("ph")
    if ph is not None and ph != password_token_claim(user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Token sudah tidak berlaku (password diubah)")
    # Revokasi lewat logout: token yang jti-nya tercatat di daftar revoked
    # (tabel settings, lihat auth_service) ditolak meski belum kedaluwarsa.
    # Token tanpa jti (diterbitkan sebelum perubahan ini) tidak bisa dicabut
    # satu-per-satu — batasan kompatibilitas, hanya ganti password yang
    # mencabutnya. Satu lookup PK tambahan per request.
    jti = payload.get("jti")
    if jti is not None:
        from app.services import auth_service
        if await auth_service.is_token_jti_recorded(db, auth_service.REVOKED_TOKENS_KEY, jti):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Token sudah tidak berlaku (logout)")
    if enforce_must_change and user.must_change_password:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Password harus diganti dulu (POST /api/auth/change-password)")
    return user


def require_roles(allowed: set[str]) -> Callable:
    """Role gate (403). Data scope is separate: services filter by rbac.scope_olt_ids (404)."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Peran Anda tidak boleh melakukan ini")
        return user

    return checker
