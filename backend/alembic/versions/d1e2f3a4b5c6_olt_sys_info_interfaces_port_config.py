"""Info sistem SNMP (sysName/sysLocation) di tabel olts + job type set_port_config

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-10-24

Ditulis tangan, pola sama f1a2b3c4d5e6: nilai hasil pembacaan perangkat jadi kolom
langsung di `olts`, bukan tabel baru (DECISIONS "Kesehatan OLT — skema DB"). Status
port uplink TIDAK disimpan: tab Interfaces membacanya live tiap kali dibuka.

ALTER TYPE ... ADD VALUE harus di luar transaksi yang memakai nilainya, jadi transaksi
alembic di-commit dulu seperti migrasi job type sebelumnya.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("olts", sa.Column("sys_name", sa.String(length=255), nullable=True))
    op.add_column("olts", sa.Column("sys_location", sa.String(length=255), nullable=True))
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'set_port_config'")


def downgrade() -> None:
    op.drop_column("olts", "sys_location")
    op.drop_column("olts", "sys_name")
    # Nilai ENUM job_type tidak dihapus: job lama masih tersimpan sebagai riwayat.
