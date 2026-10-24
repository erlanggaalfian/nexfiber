"""Job type baru untuk diagnostik Detail ONU (Status / Running config / Info SW).

Hanya menambah nilai ke enum job_type — tidak menyentuh tabel apa pun, supaya tidak
bentrok dengan migrasi track lain yang jalan paralel. Tidak ada kolom baru untuk
menyimpan output: hasil hidup di jobs.result saja (lihat laporan tahap ini).

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TYPES = (
    "read_onu_status",          # 9 blok status live satu ONU (read-only)
    "read_onu_running_config",  # 3 blok running-config (role manager saja)
    "read_onu_software",        # equip + capability ONU
)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE tidak bisa di dalam blok transaksi di Postgres < 12;
    # commit dulu supaya aman di semua versi yang didukung.
    op.execute("COMMIT")
    for name in NEW_TYPES:
        op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{name}'")


def downgrade() -> None:
    # Postgres tidak mendukung DROP VALUE pada enum; nilai dibiarkan (no-op), sama
    # seperti migrasi job_type sebelumnya.
    pass
