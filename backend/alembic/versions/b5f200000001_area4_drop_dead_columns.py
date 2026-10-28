"""Area 4 (putaran baru): hapus kolom mati.

- splitters.used_ports: tidak pernah dibaca/ditulis kode mana pun (grep: hanya
  definisi model + migrasi awal), tidak ada di SplitterOut maupun frontend.
  Jumlah port terpakai yang benar dihitung dari Onu.splitter_id.
- pon_ports.onu_count: tidak pernah dibaca/ditulis kode mana pun — PonPortOut
  diisi dari hitungan query di olt_repo/olt_service, bukan kolom ini.

Aman dihapus: tidak ada kode (app maupun tes) yang mengonstruksi/membaca
kedua kolom ini; konstruktor PonPort/Splitter di tes tidak menyebutkannya.
Downgrade mengembalikan kolom dengan default 0 (nilai historis tidak bisa
dipulihkan — memang tidak pernah dipakai, jadi tidak ada yang hilang).

Revision ID: b5f200000001
Revises: a5f100000001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5f200000001"
down_revision: str | None = "a5f100000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("splitters", "used_ports")
    op.drop_column("pon_ports", "onu_count")


def downgrade() -> None:
    op.add_column("pon_ports", sa.Column("onu_count", sa.Integer(), nullable=False,
                                         server_default="0"))
    op.add_column("splitters", sa.Column("used_ports", sa.Integer(), nullable=False,
                                         server_default="0"))
