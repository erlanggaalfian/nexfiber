"""job_type test_connection + onus.onu_index nullable

onu_index is NULL from API-create until the authorize job picks a free ID read live from
the OLT (or the operator's manual override fills it at create time).

Revision ID: c4d2e3f6a7b8
Revises: b3c1d2e4f5a6
Create Date: 2026-10-24 12:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c4d2e3f6a7b8'
down_revision: Union[str, None] = 'b3c1d2e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'test_connection'")
    op.alter_column('onus', 'onu_index', nullable=True)


def downgrade() -> None:
    # Postgres can't drop an enum value; only the column change is reverted.
    op.alter_column('onus', 'onu_index', nullable=False)
