"""Area 6 (navigasi/lintas bidang): partial unique email + unique splitter_port.

- users.email: dari unique penuh (users_email_key) menjadi partial unique
  uq_users_email_active WHERE deleted_at IS NULL, sama seperti username.
  Kolom TIDAK dihapus: skema awal membuatnya NOT NULL sehingga DB lama bisa
  berisi email, dan tidak ada API yang menulisnya saat ini — menghapus kolom
  adalah kehilangan data yang tidak bisa dikembalikan.
- onus (splitter_id, splitter_port): unique partial WHERE deleted_at IS NULL,
  menutup balapan persis yang tidak bisa ditutup cek aplikasi di authorize/
  update_info. NULL tidak saling memblokir di Postgres unique index.

PERINGATAN: bila DB sudah berisi email aktif duplikat atau (splitter_id,
splitter_port) aktif duplikat, upgrade gagal di index itu (DDL Postgres
transaksional, DB tetap di revisi lama). Bersihkan duplikatnya dulu, lalu
jalankan lagi upgrade.

Revision ID: c6a200000001
Revises: b5f200000001 (dirantai setelah migrasi Area 4 putaran yang sama,
yang juga ber-down_revision a5f100000001 — keduanya independen, tetapi
rantai tunggal menghindari dua head. Bila migrasi Area 4 dibatalkan, ubah
down_revision kembali ke a5f100000001.)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6a200000001"
down_revision: str | None = "b5f200000001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index(
        "uq_users_email_active", "users", ["email"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_onu_splitter_port", "onus", ["splitter_id", "splitter_port"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_onu_splitter_port", table_name="onus")
    op.drop_index("uq_users_email_active", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
