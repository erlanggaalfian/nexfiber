"""IP WAN per-ONU dari laporan ip-host (`onus.wan_ip_address`).

Kolom terpisah dari `onus.ip_address` (aturan keras: `ip_address` HANYA IP VLAN
management). `wan_ip_address` = `Current IP address` blok `Host ID` yang terpasang ke
VLAN NON-management (pasangan `vlan-filter iphost N ... vlan V` / `ip-host N` ↔
`gemport N flow F` ↔ `flow F ... vlan V`), dipakai chip "Setup WAN" di Detail ONU.
NULL = tidak ada host non-management yang bisa dipasangkan — tidak pernah diisi dari
kolom lain (tidak ada angka/karangan).

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "c6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("onus", sa.Column("wan_ip_address", sa.String(length=45), nullable=True))


def downgrade() -> None:
    op.drop_column("onus", "wan_ip_address")
