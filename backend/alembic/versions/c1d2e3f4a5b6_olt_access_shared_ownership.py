"""Tabel olt_access: satu OLT bisa dibagikan ke beberapa Admin/Superadmin

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-10-24

Ditulis tangan (bukan autogenerate), sama alasannya dengan f1a2b3c4d5e6.

Backward compatible: `olts.owner_id` tidak disentuh sama sekali, jadi seluruh OLT
yang sudah ada tetap dimiliki dan terlihat oleh owner lamanya. Tabel baru hanya
MENAMBAH yang boleh mengakses (rbac.scope_olt_ids = owner_id OR olt_access).
Tidak ada data yang dipindah atau dihapus.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "olt_access",
        sa.Column("olt_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["olt_id"], ["olts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("olt_id", "user_id"),
    )
    op.create_index("ix_olt_access_user_id", "olt_access", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_olt_access_user_id", table_name="olt_access")
    op.drop_table("olt_access")
