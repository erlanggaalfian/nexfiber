import time
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError, ValidationAppError
from app.core.rbac import SUPERADMIN
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User

MAX_FAILS = 5
WINDOW_S = 15 * 60

# ponytail: in-memory, valid for the single uvicorn process install.sh runs; move to a DB
# table if the API ever runs multiple workers.
_fails: dict[tuple[str, str], list[float]] = {}

class TooManyAttempts(AppError):
    status_code = 429

def _recent_fails(key: tuple[str, str]) -> list[float]:
    cutoff = time.monotonic() - WINDOW_S
    _fails[key] = [t for t in _fails.get(key, []) if t > cutoff]
    return _fails[key]

async def login(db: AsyncSession, username: str, password: str, ip: str) -> str:
    key = (ip, username)
    if len(_recent_fails(key)) >= MAX_FAILS:
        raise TooManyAttempts("Terlalu banyak percobaan gagal. Coba lagi dalam 15 menit")
    user = await db.scalar(
        select(User).where(User.username == username, User.deleted_at.is_(None))
    )
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        _fails[key].append(time.monotonic())
        raise ValidationAppError("Username atau password salah")
    _fails.pop(key, None)
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return create_access_token(user.id, user.role)

async def needs_setup(db: AsyncSession) -> bool:
    return not await db.scalar(select(func.count(User.id)))

async def setup(db: AsyncSession, username: str, full_name: str, password: str) -> str:
    """First Superadmin (PRD 3.4.1). Advisory lock so two racing requests can't both win."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('nexfiber_setup'))"))
    if not await needs_setup(db):
        raise NotFoundError("Not found")
    user = User(username=username, full_name=full_name, password_hash=hash_password(password),
                role=SUPERADMIN, last_login_at=datetime.now(UTC))
    db.add(user)
    await db.commit()
    return create_access_token(user.id, user.role)
