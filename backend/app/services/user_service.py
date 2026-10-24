"""User CRUD scoped per role (PRD 3.4.9 + 3.7). Users are never deleted, only deactivated,
so Logs keep pointing at a real row.
"""

import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.rbac import ADMIN, SUPERADMIN, USER
from app.core.security import hash_password
from app.models.user import User
from app.repositories import user_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.user import UserCreate, UserOut, UserUpdate

TEMP_PASSWORD_BYTES = 12


def _out(row: tuple[User, str | None, int]) -> UserOut:
    user, admin_username, olt_count = row
    return UserOut(
        id=user.id, username=user.username, full_name=user.full_name, role=user.role,
        admin_id=user.admin_id, admin_username=admin_username, olt_count=olt_count,
        is_active=user.is_active, must_change_password=user.must_change_password,
        last_login_at=user.last_login_at, created_at=user.created_at,
    )


async def list_users(db: AsyncSession, viewer: User, role: str | None = None) -> list[UserOut]:
    return [_out(row) for row in await user_repo.list_visible(db, viewer, role)]


async def _get(db: AsyncSession, user_id: int, viewer: User) -> tuple[User, str | None, int]:
    row = await user_repo.get_visible(db, user_id, viewer)
    if row is None:
        raise NotFoundError(f"User {user_id} not found")
    return row


async def get_user(db: AsyncSession, user_id: int, viewer: User) -> UserOut:
    return _out(await _get(db, user_id, viewer))


async def _parent_id(db: AsyncSession, role: str, admin_id: int | None, actor: User) -> int | None:
    """Admin only ever creates Users under itself; Superadmin must name the parent Admin."""
    if role != USER:
        return None
    if actor.role != SUPERADMIN:
        return actor.id
    if admin_id is None:
        raise ValidationAppError("User wajib punya Admin induk")
    parent = await db.get(User, admin_id)
    if parent is None or parent.deleted_at is not None or parent.role != ADMIN:
        raise ValidationAppError("Admin induk harus Admin yang aktif")
    return parent.id


def _may_set_role(role: str, actor: User) -> None:
    if role == ADMIN and actor.role != SUPERADMIN:
        raise ValidationAppError("Hanya Superadmin yang bisa membuat Admin")


async def _save(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Username sudah dipakai") from exc


async def create_user(db: AsyncSession, body: UserCreate, actor: User) -> UserOut:
    _may_set_role(body.role, actor)
    user = User(
        username=body.username, full_name=body.full_name, role=body.role,
        password_hash=hash_password(body.password),
        admin_id=await _parent_id(db, body.role, body.admin_id, actor),
    )
    db.add(user)
    await _save(db)
    await log_activity(db, action="user.create", entity_type="user", entity_id=str(user.id),
                       success=True, user_id=actor.id,
                       after={"username": user.username, "role": user.role,
                              "admin_id": user.admin_id})
    await db.commit()
    return await get_user(db, user.id, actor)


async def update_user(db: AsyncSession, user_id: int, body: UserUpdate, actor: User) -> UserOut:
    user, _, olt_count = await _get(db, user_id, actor)
    values = body.model_dump(exclude_unset=True)

    if {"role", "admin_id"} & values.keys() and actor.role != SUPERADMIN:
        raise ValidationAppError("Hanya Superadmin yang bisa mengubah peran atau Admin induk")
    if values.get("is_active") is False:
        await _check_deactivable(db, user, olt_count)

    role = values.get("role", user.role)
    if "role" in values:
        _may_set_role(role, actor)
        user.role = role
    if "role" in values or "admin_id" in values:
        user.admin_id = await _parent_id(db, role, values.get("admin_id", user.admin_id), actor)
    if values.get("password"):
        user.password_hash = hash_password(values["password"])
        user.must_change_password = False
    if "full_name" in values:
        user.full_name = values["full_name"]
    if "is_active" in values:
        user.is_active = values["is_active"]

    await _save(db)
    await log_activity(db, action="user.update", entity_type="user", entity_id=str(user.id),
                       success=True, user_id=actor.id,
                       after={k: v for k, v in values.items() if k != "password"}
                       | ({"password": "[REDACTED]"} if values.get("password") else {}))
    await db.commit()
    return await get_user(db, user.id, actor)


async def _check_deactivable(db: AsyncSession, user: User, olt_count: int) -> None:
    """PRD 3.4.9: an Admin that still owns OLTs must hand them over first; and the last
    active Superadmin can never be locked out.
    """
    if olt_count:
        raise ValidationAppError(
            f"User ini masih memiliki {olt_count} OLT. Pindahkan atau hapus OLT-nya dulu"
        )
    if user.role == SUPERADMIN and await user_repo.count_active_superadmins(db) <= 1:
        raise ValidationAppError("Superadmin terakhir tidak bisa dinonaktifkan")


async def reset_password(db: AsyncSession, user_id: int, actor: User) -> str:
    """Returns a one-time temp password; the user must change it at next login."""
    user, _, _ = await _get(db, user_id, actor)
    temp = secrets.token_urlsafe(TEMP_PASSWORD_BYTES)
    user.password_hash = hash_password(temp)
    user.must_change_password = True
    await log_activity(db, action="user.reset_password", entity_type="user",
                       entity_id=str(user.id), success=True, user_id=actor.id)
    await db.commit()
    return temp
