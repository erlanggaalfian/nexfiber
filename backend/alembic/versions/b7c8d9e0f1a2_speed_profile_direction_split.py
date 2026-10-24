"""Speed Profile pisah Download/Upload (Opsi A).

Data speed_profiles lama dihapus total (bukan auto-split) sesuai keputusan user —
tiap profile sekarang satu arah lewat kolom direction, bukan satu baris gabungan
download_kbps+upload_kbps. onus.speed_profile_id dipecah jadi 2 FK per arah.

Revision ID: b7c8d9e0f1a2
Revises: a2b3c4d5e6f7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM speed_profiles")
    direction_enum = sa.Enum("download", "upload", name="speed_profile_direction")
    direction_enum.create(op.get_bind())

    with op.batch_alter_table("speed_profiles") as batch:
        batch.add_column(sa.Column("direction", direction_enum, nullable=False,
                                   server_default="download"))
        batch.add_column(sa.Column("speed_kbps", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("device_profile_id", sa.String(50), nullable=True))
        batch.drop_column("download_kbps")
        batch.drop_column("upload_kbps")
        batch.drop_column("line_profile_id")
        batch.drop_column("srv_profile_id")
    op.alter_column("speed_profiles", "direction", server_default=None)
    op.alter_column("speed_profiles", "speed_kbps", server_default=None)

    with op.batch_alter_table("onus") as batch:
        batch.add_column(sa.Column("download_speed_profile_id", sa.BigInteger(),
                                   sa.ForeignKey("speed_profiles.id"), nullable=True))
        batch.add_column(sa.Column("upload_speed_profile_id", sa.BigInteger(),
                                   sa.ForeignKey("speed_profiles.id"), nullable=True))
        batch.drop_column("speed_profile_id")


def downgrade() -> None:
    with op.batch_alter_table("onus") as batch:
        batch.add_column(sa.Column("speed_profile_id", sa.BigInteger(),
                                   sa.ForeignKey("speed_profiles.id"), nullable=True))
        batch.drop_column("download_speed_profile_id")
        batch.drop_column("upload_speed_profile_id")

    with op.batch_alter_table("speed_profiles") as batch:
        batch.add_column(sa.Column("download_kbps", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("upload_kbps", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("line_profile_id", sa.String(50), nullable=True))
        batch.add_column(sa.Column("srv_profile_id", sa.String(50), nullable=True))
        batch.drop_column("direction")
        batch.drop_column("speed_kbps")
        batch.drop_column("device_profile_id")
    sa.Enum(name="speed_profile_direction").drop(op.get_bind())
