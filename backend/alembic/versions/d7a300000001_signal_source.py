"""Verifikasi gabungan putaran 4: kolom sumber histori sinyal.

- onu_signal_history.source (nullable): "status_change" atau "optical" untuk
  baris baru; baris lama dibiarkan NULL (= sumber tidak diketahui, tidak
  ditebak lewat backfill).

Revision ID: d7a300000001
Revises: c6a200000001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a300000001"
down_revision: str | None = "c6a200000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("onu_signal_history", sa.Column("source", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("onu_signal_history", "source")
