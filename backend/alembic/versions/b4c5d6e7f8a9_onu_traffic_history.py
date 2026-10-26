"""Histori trafik per ONU: tabel sampel counter + job type sampler.

Kenapa tabel sendiri, bukan kolom di `onu_signal_history`: intervalnya beda (trafik 5
menit, sinyal 15 menit / saat status berubah) dan baris sinyal juga ditulis saat status
berubah — menumpangkan counter di sana membuat delta waktunya tidak beraturan.

Retensi 30 hari (PRD "Database/Infra": time-series detail 30 hari, tabel biasa dengan
retensi bergulir). Pembersihan dilakukan job sampler itu sendiri, jadi tidak ada cron
tambahan. Index (onu_id, sampled_at) = pola query grafik 24j/7h/30h.

Revision ID: b4c5d6e7f8a9
Revises: a3c4d5e6f7b8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3c4d5e6f7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onu_traffic_history",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("onu_id", sa.BigInteger(), nullable=False),
        # Counter kumulatif octet (Counter64 muat di NUMERIC(20), tidak di BIGINT).
        sa.Column("in_octets", sa.Numeric(20, 0), nullable=False),
        sa.Column("out_octets", sa.Numeric(20, 0), nullable=False),
        # NULL = laju tidak diketahui (sampel pertama / counter wrap / reset), bukan 0.
        sa.Column("in_bps", sa.BigInteger(), nullable=True),
        sa.Column("out_bps", sa.BigInteger(), nullable=True),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["onu_id"], ["onus.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onu_traffic_onu_sampled", "onu_traffic_history",
                    ["onu_id", "sampled_at"], unique=False)
    # ALTER TYPE ... ADD VALUE tidak boleh di dalam transaksi di Postgres < 12.
    op.execute("COMMIT")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'sample_onu_traffic'")
    # Job sampler ikut aturan anti-numpuk per OLT seperti sync_* lainnya.
    op.execute("DROP INDEX IF EXISTS uq_jobs_sync_pending_per_olt")
    op.execute(
        "CREATE UNIQUE INDEX uq_jobs_sync_pending_per_olt ON jobs (job_type, olt_id) "
        "WHERE status IN ('pending','running') AND job_type IN "
        "('sync_onu_status','sync_onu_optical','sync_unconfigured','sync_olt_metrics',"
        "'sample_onu_traffic')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_jobs_sync_pending_per_olt")
    op.execute(
        "CREATE UNIQUE INDEX uq_jobs_sync_pending_per_olt ON jobs (job_type, olt_id) "
        "WHERE status IN ('pending','running') AND job_type IN "
        "('sync_onu_status','sync_onu_optical','sync_unconfigured','sync_olt_metrics')"
    )
    op.drop_index("ix_onu_traffic_onu_sampled", table_name="onu_traffic_history")
    op.drop_table("onu_traffic_history")
    # Nilai enum job_type dibiarkan: Postgres tidak mendukung DROP VALUE.
