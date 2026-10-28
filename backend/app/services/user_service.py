"""User CRUD scoped per role (PRD 3.4.9 + 3.7). Delete is a soft-delete (`deleted_at`),
never a row removal, so Logs and `olts.owner_id` keep pointing at a real row.
"""

import secrets
from datetime import UTC, datetime

from sqlalchemy import text
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
    if parent is None or parent.deleted_at is not None or parent.role != ADMIN \
            or not parent.is_active:
        # is_active sebelumnya tidak dicek padahal docstring menyebut "aktif":
        # user baru di bawah Admin nonaktif langsung bekerja lewat scope induknya.
        raise ValidationAppError("Admin induk harus Admin yang aktif")
    return parent.id


async def _parent_active(db: AsyncSession, user: User) -> None:
    """Saat user diaktifkan kembali, induknya harus masih aktif; kalau tidak,
    user itu akan langsung bekerja lewat scope Admin yang sudah nonaktif."""
    if user.admin_id is None:
        return
    parent = await db.get(User, user.admin_id)
    if parent is not None and (parent.deleted_at is not None or not parent.is_active):
        raise ValidationAppError("Admin induk sudah tidak aktif; aktifkan induknya dulu")


def _may_set_role(role: str, actor: User) -> None:
    """Superadmin may create any role (peers included); an Admin may create Admins and
    Users, never a Superadmin. Role "user" never reaches here (router gate, PRD 3.7).
    ponytail: an Admin-created Admin is not visible to its creator (visibility is still
    `admin_id`-based per PRD 3.7); add a `created_by` column if that becomes a problem.
    """
    if role == SUPERADMIN and actor.role != SUPERADMIN:
        raise ValidationAppError("Hanya Superadmin yang bisa membuat Superadmin")


def _not_self(user: User, actor: User, what: str) -> None:
    """Nobody locks itself out of the app."""
    if user.id == actor.id:
        raise ValidationAppError(f"Anda tidak bisa {what} akun Anda sendiri")


async def _save(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # Sebelumnya SEMUA IntegrityError dipetakan ke "Username sudah dipakai",
        # termasuk pelanggaran kolom lain. Bedakan berdasarkan nama constraint
        # bila bisa dibaca dari pesan DB; sisanya tetap ConflictError generik.
        msg = str(getattr(exc, "orig", exc))
        # Nama constraint partial unique yang benar (model user.py):
        # uq_users_username_active, bukan users_username_key lama. Nama lama
        # tetap dicek sebagai fallback bila DB belum dimigrasi.
        if "uq_users_username_active" in msg or "users_username_key" in msg:
            raise ConflictError("Username sudah dipakai") from exc
        if "users_email_key" in msg:
            raise ConflictError("Email sudah dipakai") from exc
        raise ConflictError("Username sudah dipakai") from exc


async def create_user(db: AsyncSession, body: UserCreate, actor: User) -> UserOut:
    _may_set_role(body.role, actor)
    # Guard _username_taken_by_deleted DIHAPUS: partial unique
    # uq_users_username_active (WHERE deleted_at IS NULL) sudah mengizinkan
    # pemakaian ulang username dari baris soft-delete, dan guard lama justru
    # memblokirnya lagi di lapisan aplikasi. Duplikat aktif tetap ditolak
    # oleh constraint DB yang dipetakan di _save di atas.
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
    await db.refresh(user)
    # Read back from the row itself, not through the visibility filter: an Admin creating an
    # Admin peer may not see it afterwards (visibility is admin_id-based, PRD 3.7) and a
    # scoped re-read would answer 404 on a creation that did succeed.
    parent = await db.get(User, user.admin_id) if user.admin_id else None
    return _out((user, parent.username if parent else None, 0))


async def _lock_last_superadmin(db: AsyncSession) -> None:
    """Kunci advisory transaksi (seperti setup): menahan semua demote/nonaktif/
    hapus Superadmin lain sampai transaksi ini commit/rollback, supaya cek
    "Superadmin terakhir" tidak bisa dilompati dua permintaan bersamaan.
    Kunci dilepas otomatis di akhir transaksi (xact), bukan manual."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('nexfiber_last_superadmin'))"))


async def update_user(db: AsyncSession, user_id: int, body: UserUpdate, actor: User) -> UserOut:
    user, _, olt_count = await _get(db, user_id, actor)
    values = body.model_dump(exclude_unset=True)
    # Ambil kunci SEBELUM cek demote/nonaktif, supaya hitungan di bawah ini
    # dibaca setelah kunci dipegang (bukan sebelum). Hanya bila targetnya
    # Superadmin dan aksinya demote atau nonaktif — update biasa tidak perlu
    # diserialisasi.
    if user.role == SUPERADMIN and (values.get("role") not in (None, SUPERADMIN)
                                    or values.get("is_active") is False):
        await _lock_last_superadmin(db)

    if {"role", "admin_id"} & values.keys() and actor.role != SUPERADMIN:
        raise ValidationAppError("Hanya Superadmin yang bisa mengubah peran atau Admin induk")
    if values.get("is_active") is False:
        _not_self(user, actor, "menonaktifkan")
        await _check_deactivable(db, user, olt_count)
    if values.get("is_active") is True:
        await _parent_active(db, user)

    role = values.get("role", user.role)
    if "role" in values:
        _may_set_role(role, actor)
        # Proteksi demote, sejajar dengan proteksi nonaktif: Superadmin terakhir
        # tidak boleh didemote (sebelumnya hanya nonaktif yang dicek, sehingga
        # PATCH role bisa mengunci sistem dari tier Superadmin). Admin yang
        # masih memiliki OLT juga tidak boleh didemote jadi user.
        if user.role == SUPERADMIN and role != SUPERADMIN \
                and await user_repo.count_active_superadmins(db) <= 1:
            raise ValidationAppError("Superadmin terakhir tidak bisa didemote")
        if user.role == ADMIN and role == USER and olt_count:
            raise ValidationAppError(
                f"User ini masih memiliki {olt_count} OLT. Pindahkan atau hapus OLT-nya dulu")
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
    # Sebelumnya hanya delete_user yang memeriksa anak; menonaktifkan Admin
    # membiarkan seluruh subtree tetap login dan mengakses OLT induk nonaktif.
    if await user_repo.count_children(db, user.id):
        raise ValidationAppError(
            "User ini masih punya User di bawahnya. Hapus atau pindahkan dulu")
    if user.role == SUPERADMIN and await user_repo.count_active_superadmins(db) <= 1:
        raise ValidationAppError("Superadmin terakhir tidak bisa dinonaktifkan")


async def delete_user(db: AsyncSession, user_id: int, actor: User) -> None:
    """Soft-delete only (`deleted_at` + is_active=False), same as OLT/ONU: Logs and
    olts.owner_id keep pointing at a real row (PRD 3.4.9).
    """
    user, _, olt_count = await _get(db, user_id, actor)
    _not_self(user, actor, "menghapus")
    if user.role == SUPERADMIN:
        await _lock_last_superadmin(db)
    await _check_deactivable(db, user, olt_count)
    if await user_repo.count_children(db, user.id):
        raise ValidationAppError("User ini masih punya User di bawahnya. Hapus atau pindahkan dulu")
    user.deleted_at = datetime.now(UTC)
    user.is_active = False
    await log_activity(db, action="user.delete", entity_type="user", entity_id=str(user.id),
                       success=True, user_id=actor.id,
                       before={"username": user.username, "role": user.role})
    await db.commit()


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
