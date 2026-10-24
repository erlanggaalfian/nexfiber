"""speed_profiles.vlan_db_id + job types VLAN/speed profile

Revision ID: a1b2c3d4e5f6
Revises: 10909b061371
Create Date: 2026-10-24

Ditulis tangan (bukan autogenerate): hanya satu kolom + nilai ENUM baru, dan
autogenerate suka ikut mengusulkan drop partisi internal activity_logs_default.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "10909b061371"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_JOB_TYPES = ("create_vlan", "delete_vlan", "push_speed_profile", "sync_speed_profiles")
OLD_JOB_TYPES = (
    "authorize_onu", "delete_onu", "reboot_onu", "set_state", "sync_onu_status",
    "sync_onu_optical", "sync_unconfigured", "backup_olt_config", "apply_speed_profile",
    "tr069_push", "test_connection",
)


def upgrade() -> None:
    op.add_column("speed_profiles", sa.Column("vlan_db_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_speed_profiles_vlan_db_id", "speed_profiles", "vlans", ["vlan_db_id"], ["id"]
    )
    for value in NEW_JOB_TYPES:
        op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # FK dinamai eksplisit supaya bisa di-drop di sini.
    op.drop_constraint("fk_speed_profiles_vlan_db_id", "speed_profiles", type_="foreignkey")
    op.drop_column("speed_profiles", "vlan_db_id")
    # Postgres tidak bisa menghapus nilai ENUM: tipe dibuat ulang tanpa nilai baru.
    # Baris job dengan nilai baru dihapus dulu, kalau tidak cast-nya gagal.
    op.execute(
        "DELETE FROM jobs WHERE job_type::text IN "
        f"({', '.join(repr(v) for v in NEW_JOB_TYPES)})"
    )
    values = ", ".join(repr(v) for v in OLD_JOB_TYPES)
    op.execute(f"CREATE TYPE job_type_old AS ENUM ({values})")
    op.execute(
        "ALTER TABLE jobs ALTER COLUMN job_type TYPE job_type_old "
        "USING job_type::text::job_type_old"
    )
    op.execute("DROP TYPE job_type")
    op.execute("ALTER TYPE job_type_old RENAME TO job_type")
