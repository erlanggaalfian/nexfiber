"""Roles & OLT scope (PRD 3.7). Superadmin = all OLTs, Admin = OLTs it owns, User = OLTs of
its Admin. Out-of-scope reads answer 404 so other Admins' data never leaks.

Kepemilikan OLT dibagi: selain `olts.owner_id` (pemilik utama), baris `olt_access`
memberi Admin/Superadmin lain akses penuh ke OLT yang sama. Scope satu-satunya tempat
aturan itu ditulis — semua query ONU/OLT/log/job memakai `scope_olt_ids` (DRY).
"""

from sqlalchemy import Select, or_, select

from app.models.olt import Olt, OltAccess
from app.models.user import User

SUPERADMIN, ADMIN, USER = "superadmin", "admin", "user"
MANAGERS = {SUPERADMIN, ADMIN}  # manage OLTs, delete ONU, restore factory

# None = no restriction; otherwise a subquery of allowed olts.id for `col.in_(scope)`.
Scope = Select | None

def owner_of(user: User) -> int | None:
    if user.role == SUPERADMIN:
        return None
    return user.id if user.role == ADMIN else user.admin_id

def scope_olt_ids(user: User) -> Scope:
    """OLT yang boleh disentuh: pemilik utama ATAU punya baris akses tambahan.

    Untuk role User yang dipakai adalah Admin induknya, jadi User ikut melihat OLT
    yang dibagikan ke Admin-nya.
    """
    owner = owner_of(user)
    if owner is None:
        return None
    shared = select(OltAccess.olt_id).where(OltAccess.user_id == owner)
    return select(Olt.id).where(or_(Olt.owner_id == owner, Olt.id.in_(shared)))

def scoped(stmt: Select, olt_col, scope: Scope) -> Select:
    return stmt if scope is None else stmt.where(olt_col.in_(scope))
