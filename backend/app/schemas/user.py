from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    # PRD 3.7 rule 5 only fixes how the *first* Superadmin is made (/setup). Later on a
    # Superadmin may create peers; who may set which role is enforced in user_service.
    role: str = Field(pattern="^(superadmin|admin|user)$")
    admin_id: int | None = None  # required for role=user; an Admin always gets itself


class UserUpdate(BaseModel):
    """Omitted fields stay unchanged. role/admin_id are Superadmin-only (PRD 3.4.9)."""

    full_name: str | None = Field(None, min_length=1, max_length=255)
    password: str | None = Field(None, min_length=12, max_length=128)
    role: str | None = Field(None, pattern="^(superadmin|admin|user)$")
    admin_id: int | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    """Never exposes password_hash."""

    id: int
    username: str
    full_name: str
    role: str
    admin_id: int | None
    admin_username: str | None
    olt_count: int
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class TempPassword(BaseModel):
    """Shown once, right after reset; never stored or logged in plain text."""

    password: str
