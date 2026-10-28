from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

# PRD 4.6 / trade-off #4: fixed 3-value ENUM; access rules live in app/core/rbac.py (PRD 3.7).
UserRole = Enum("superadmin", "admin", "user", name="user_role")

class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("(role = 'user') = (admin_id IS NOT NULL)", name="ck_users_admin_id"),
        # Partial unique: username user ter-soft-delete bisa dipakai lagi.
        Index(
            "uq_users_username_active", "username", unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Email dipertahankan (bukan dihapus): kolom ini memang tidak ditulis
        # API/skema manapun saat ini, tetapi skema awal membuatnya NOT NULL
        # sehingga DB lama bisa berisi email — menghapus kolom adalah kehilangan
        # data yang tidak bisa dikembalikan. Yang diubah hanya constraint-nya:
        # dari unique penuh menjadi partial unique, supaya email akun
        # ter-soft-delete tidak memblokir pemakaian ulang, sama seperti username.
        Index(
            "uq_users_email_active", "email", unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(UserRole, nullable=False)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
