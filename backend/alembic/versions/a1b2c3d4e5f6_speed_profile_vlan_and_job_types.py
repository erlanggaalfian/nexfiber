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
    # uq_vlan_olt_vlanid tidak mengikat VLAN global: di Postgres NULL != NULL, jadi
    # (NULL, 2501) boleh berulang. Index parsial ini yang menolak duplikat VLAN global.
    op.execute(
        "CREATE UNIQUE INDEX uq_vlan_global_vlanid ON vlans (vlan_id) WHERE olt_id IS NULL"
    )
    for value in NEW_JOB_TYPES:
        op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_vlan_global_vlanid")
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
    # Index parsial uq_jobs_sync_pending_per_olt memuat konstanta bertipe job_type di
    # predikatnya; selama index itu ada, ALTER TYPE kolomnya ditolak. Drop lalu buat ulang.
    op.execute("DROP INDEX IF EXISTS uq_jobs_sync_pending_per_olt")
    op.execute(
        "ALTER TABLE jobs ALTER COLUMN job_type TYPE job_type_old "
        "USING job_type::text::job_type_old"
    )
    op.execute("DROP TYPE job_type")
    op.execute("ALTER TYPE job_type_old RENAME TO job_type")
    op.execute(
        "CREATE UNIQUE INDEX uq_jobs_sync_pending_per_olt ON jobs (job_type, olt_id) "
        "WHERE status IN ('pending','running') "
        "AND job_type IN ('sync_onu_status','sync_onu_optical','sync_unconfigured')"
    )
