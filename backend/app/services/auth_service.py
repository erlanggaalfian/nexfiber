from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.core.security import create_access_token, verify_password
from app.models.user import User


async def login(db: AsyncSession, username: str, password: str) -> str:
    user = (
        await db.execute(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise ValidationAppError("Username atau password salah")

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return create_access_token(user.id, user.role)
