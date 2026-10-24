"""Anti-numpuk job per ONU: partial unique index (job_type, onu_id) saat pending/running.

Kenapa: cek aplikasi `exists_active_for_onu` bisa dilewati dua proses yang jalan bersamaan
(keduanya membaca "belum ada", keduanya insert). Index inilah yang memutuskan pemenang,
sama seperti `uq_jobs_sync_pending_per_olt` untuk job sync per OLT.

Aman untuk data lama: baris pending/running duplikat (job_type, onu_id) yang sudah ada
ditutup sebagai 'cancelled' lebih dulu, menyisakan satu baris tertua per pasangan — tidak
ada baris yang dihapus, histori job tetap utuh. Bisa dibatalkan (downgrade hanya drop index).

Revision ID: f2b3c4d5e6a7
Revises: e1f2a3b4c5d6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c4d5e6a7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_jobs_active_per_onu"
WHERE = "status IN ('pending','running') AND onu_id IS NOT NULL"


def upgrade() -> None:
    # Sisakan job tertua per (job_type, onu_id) yang masih aktif; sisanya dibatalkan.
    op.execute(sa.text(f"""
        UPDATE jobs SET status = 'cancelled', finished_at = now(),
                        error_code = 'Superseded',
                        error_message = 'Dibatalkan: job sejenis untuk ONU ini sudah ada'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY job_type, onu_id ORDER BY id
                ) AS rn
                FROM jobs WHERE {WHERE}
            ) ranked WHERE rn > 1
        )
    """))
    op.create_index(INDEX_NAME, "jobs", ["job_type", "onu_id"], unique=True,
                    postgresql_where=sa.text(WHERE))


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="jobs")
