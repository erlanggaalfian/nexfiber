"""Job type baru untuk aksi Detail ONU (Fase C2).

Hanya menambah nilai ke enum job_type — tidak menyentuh tabel apa pun, supaya tidak
bentrok dengan migrasi track lain yang jalan paralel.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TYPES = (
    "refresh_onu_detail",  # baca live optical/versi/running-config satu ONU
    "resync_onu",          # kirim ulang config dari DB ke OLT
    "set_onu_vlan",        # pindah VLAN ONU
    "replace_onu",         # ganti SN, data pelanggan tetap
    "restore_factory",     # reset ONU ke setelan pabrik
)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE tidak bisa di dalam blok transaksi di Postgres < 12;
    # commit dulu supaya aman di semua versi yang didukung.
    op.execute("COMMIT")
    for name in NEW_TYPES:
        op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{name}'")


def downgrade() -> None:
    # Postgres tidak mendukung DROP VALUE pada enum. Nilai dibiarkan; job lama yang
    # memakainya tetap bisa dibaca. Downgrade di sini sengaja no-op.
    pass
