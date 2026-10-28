"""Port config terakhir ditulis Nexfiber per ONU (prefill modal Eth/WiFi).

- onus.port_configs (JSONB, nullable): {"eth": {"1": {...}}, "wifi": {"1": {...}}}.
  NULL = belum pernah ditulis Nexfiber; tidak ada backfill (nilai lama tidak
  bisa ditebak dari perangkat tanpa baca-live yang terbukti).

Revision ID: d7a300000002
Revises: d7a300000001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d7a300000002"
down_revision: str | None = "d7a300000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("onus", sa.Column("port_configs", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("onus", "port_configs")
