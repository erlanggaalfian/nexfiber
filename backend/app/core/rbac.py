"""Roles & OLT scope (PRD 3.7). Superadmin = all OLTs, Admin = OLTs it owns, User = OLTs of
its Admin. Out-of-scope reads answer 404 so other Admins' data never leaks.
"""

from sqlalchemy import Select, select

from app.models.olt import Olt
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
    owner = owner_of(user)
    return None if owner is None else select(Olt.id).where(Olt.owner_id == owner)

def scoped(stmt: Select, olt_col, scope: Scope) -> Select:
    return stmt if scope is None else stmt.where(olt_col.in_(scope))
