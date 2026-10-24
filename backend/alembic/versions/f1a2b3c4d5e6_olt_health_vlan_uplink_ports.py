"""Kesehatan OLT di tabel olts + uplink_ports VLAN + job type sync_olt_metrics/set_vlan_ports

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-10-24

Ditulis tangan (bukan autogenerate), sama alasannya dengan a1b2c3d4e5f6.

DECISIONS "Kesehatan OLT — skema DB": kolom langsung di `olts`, data per-card
JSONB, BUKAN tabel `olt_cards`. `vlans.uplink_ports` ikut pola yang sama: hanya
dibaca/ditulis utuh di satu tab (Detail OLT > VLANs), tidak pernah di-query per port.

ALTER TYPE ... ADD VALUE tidak boleh dipakai di transaksi yang sama dengan
pemakaian nilainya (predikat index di bawah), jadi transaksi alembic di-commit
dulu di tengah migrasi.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_JOB_TYPES = ("sync_olt_metrics", "set_vlan_ports")
SYNC_TYPES_OLD = ("sync_onu_status", "sync_onu_optical", "sync_unconfigured")
SYNC_TYPES_NEW = (*SYNC_TYPES_OLD, "sync_olt_metrics")
HEALTH_COLUMNS = ("cpu_pct", "ram_pct", "temperature_c", "uptime_seconds", "software_version",
                  "cards", "uplink_ports")


def _sync_index(job_types: tuple[str, ...]) -> str:
    values = ", ".join(repr(v) for v in job_types)
    return (
        "CREATE UNIQUE INDEX uq_jobs_sync_pending_per_olt ON jobs (job_type, olt_id) "
        f"WHERE status IN ('pending','running') AND job_type IN ({values})"
    )


def upgrade() -> None:
    op.add_column("olts", sa.Column("cpu_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("olts", sa.Column("ram_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("olts", sa.Column("temperature_c", sa.Numeric(5, 2), nullable=True))
    op.add_column("olts", sa.Column("uptime_seconds", sa.BigInteger(), nullable=True))
    op.add_column("olts", sa.Column("software_version", sa.String(length=100), nullable=True))
    op.add_column("olts", sa.Column("cards", postgresql.JSONB(), nullable=False,
                                    server_default=sa.text("'[]'::jsonb")))
    # Nama port uplink hasil scan (gei_1/5/1, xgei_1/5/1): dipakai tab VLANs sebagai pilihan
    # port tagged/untagged. JSONB, sealasan dengan cards.
    op.add_column("olts", sa.Column("uplink_ports", postgresql.JSONB(), nullable=False,
                                    server_default=sa.text("'[]'::jsonb")))
    op.add_column("vlans", sa.Column("uplink_ports", postgresql.JSONB(), nullable=False,
                                     server_default=sa.text("'{}'::jsonb")))

    op.execute("COMMIT")  # lihat docstring: ADD VALUE harus commit sebelum dipakai
    for value in NEW_JOB_TYPES:
        op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{value}'")
    op.execute("COMMIT")

    op.execute("DROP INDEX IF EXISTS uq_jobs_sync_pending_per_olt")
    op.execute(_sync_index(SYNC_TYPES_NEW))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_jobs_sync_pending_per_olt")
    op.execute(_sync_index(SYNC_TYPES_OLD))
    op.drop_column("vlans", "uplink_ports")
    for column in HEALTH_COLUMNS:
        op.drop_column("olts", column)
    # Nilai ENUM tidak dihapus di sini: job lama yang memakainya masih tersimpan sebagai
    # riwayat, dan a1b2c3d4e5f6 sudah menunjukkan ongkos membangun ulang tipe job_type.
