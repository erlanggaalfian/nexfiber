from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.rbac import PermissionDenied, require_role
from app.core.security import decode_access_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    return await _user_from_token(db, token)

async def get_user_from_query_token(token: str, db: AsyncSession = Depends(get_db)) -> User:
    """For EventSource, which cannot send an Authorization header (PRD 4.5.C SSE)."""
    return await _user_from_token(db, token)

async def _user_from_token(db: AsyncSession, token: str) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid") from exc

    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak ditemukan atau nonaktif")
    return user


def require_permission(allowed: set[str]) -> Callable:
    """FastAPI dependency factory: raise 403 if current user's role isn't in `allowed`."""

    def checker(user: User = Depends(get_current_user)) -> User:
        try:
            require_role(user.role, allowed)
        except PermissionDenied as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
        return user

    return checker
