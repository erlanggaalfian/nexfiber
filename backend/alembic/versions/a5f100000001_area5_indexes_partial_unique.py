"""Area 5: index hilang + partial unique soft-delete + unique get_or_create.

- activity_logs: index olt/user/action + created_at (tabel terpartisi: index
  non-unique menyebar ke partisi, diizinkan Postgres).
- onu_signal_history: index (onu_id, sampled_at); jobs: index (olt_id, created_at).
- jobs anti-numpuk per-OLT diperluas ke backup_olt_config, sync_speed_profiles,
  test_connection. TIDAK mencakup create/delete_vlan, set_vlan_ports,
  set_port_config, push_speed_profile (payload berbeda per job; antrean lewat
  CLI lock sudah cukup) — jangan klaim indeks ini mencakup semua job.
- olts (host, cli_port) dan users (username) jadi partial unique WHERE
  deleted_at IS NULL, supaya baris ter-soft-delete tidak memblokir pakai ulang.
- Unique get_or_create: speed_profiles (olt_id, direction, device_profile_id),
  onu_presets (owner_id, name), onu_types (name), splitters (olt_id, code),
  zones (owner_id, lower(name)) menggantikan unique eksak lama.

PERINGATAN: bila DB sudah berisi duplikat untuk salah satu unique baru di
atas, upgrade akan gagal di constraint itu (DDL Postgres transaksional, DB
tetap di revisi lama). Bersihkan duplikatnya dulu, lalu jalankan lagi upgrade.

Revision ID: a5f100000001
Revises: d7e8f9a0b1c2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5f100000001"
down_revision: str | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_JOBS = (
    "sync_onu_status", "sync_onu_optical", "sync_unconfigured",
    "sync_olt_metrics", "sample_onu_traffic", "backup_olt_config",
    "sync_speed_profiles", "test_connection",
)


def _sync_predicate() -> str:
    jobs = ",".join(f"'{j}'" for j in SYNC_JOBS)
    return f"status IN ('pending','running') AND job_type IN ({jobs})"


def upgrade() -> None:
    # 1. Index hilang.
    op.create_index("ix_activity_logs_olt_created", "activity_logs", ["olt_id", "created_at"])
    op.create_index("ix_activity_logs_user_created", "activity_logs", ["user_id", "created_at"])
    op.create_index("ix_activity_logs_action_created", "activity_logs", ["action", "created_at"])
    op.create_index("ix_onu_signal_onu_sampled", "onu_signal_history", ["onu_id", "sampled_at"])
    op.create_index("ix_jobs_olt_created", "jobs", ["olt_id", "created_at"])

    # 2. Perluas anti-numpuk per-OLT (drop + buat ulang dengan predikat baru).
    op.drop_index("uq_jobs_sync_pending_per_olt", table_name="jobs")
    op.create_index(
        "uq_jobs_sync_pending_per_olt", "jobs", ["job_type", "olt_id"], unique=True,
        postgresql_where=sa.text(_sync_predicate()),
    )

    # 3. OLT partial unique (ganti constraint penuh dengan index parsial).
    op.drop_constraint("uq_olt_host_cliport", "olts", type_="unique")
    op.create_index(
        "uq_olt_host_cliport", "olts", ["host", "cli_port"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 4. Username partial unique. Nama constraint unique kolom bisa berbeda
    # antar instalasi, jadi hapus semua unique constraint yang menyebut username.
    op.execute(sa.text(
        "DO $$ DECLARE r record; BEGIN "
        "FOR r IN SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'users'::regclass AND contype = 'u' "
        "AND pg_get_constraintdef(oid) LIKE '%username%' LOOP "
        "EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || quote_ident(r.conname); "
        "END LOOP; END $$"
    ))
    op.create_index(
        "uq_users_username_active", "users", ["username"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 5. Unique get_or_create master data.
    op.create_index(
        "uq_speed_profile_olt_direction_device", "speed_profiles",
        ["olt_id", "direction", "device_profile_id"], unique=True,
    )
    op.create_index("uq_onu_preset_owner_name", "onu_presets", ["owner_id", "name"], unique=True)
    op.create_index("uq_onu_type_name", "onu_types", ["name"], unique=True)
    op.create_index("uq_splitter_olt_code", "splitters", ["olt_id", "code"], unique=True)
    op.drop_constraint("uq_zone_owner_name", "zones", type_="unique")
    op.create_index(
        "uq_zone_owner_name_lower", "zones", ["owner_id", sa.text("lower(name)")], unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_zone_owner_name_lower", table_name="zones")
    op.create_unique_constraint("uq_zone_owner_name", "zones", ["owner_id", "name"])
    op.drop_index("uq_splitter_olt_code", table_name="splitters")
    op.drop_index("uq_onu_type_name", table_name="onu_types")
    op.drop_index("uq_onu_preset_owner_name", table_name="onu_presets")
    op.drop_index("uq_speed_profile_olt_direction_device", table_name="speed_profiles")
    op.drop_index("uq_users_username_active", table_name="users")
    op.execute(sa.text(
        "ALTER TABLE users ADD CONSTRAINT users_username_key UNIQUE (username)"
    ))
    op.drop_index("uq_olt_host_cliport", table_name="olts")
    op.create_unique_constraint("uq_olt_host_cliport", "olts", ["host", "cli_port"])
    op.drop_index("uq_jobs_sync_pending_per_olt", table_name="jobs")
    op.create_index(
        "uq_jobs_sync_pending_per_olt", "jobs", ["job_type", "olt_id"], unique=True,
        postgresql_where=sa.text(
            "status IN ('pending','running') "
            "AND job_type IN ('sync_onu_status','sync_onu_optical','sync_unconfigured',"
            "'sync_olt_metrics','sample_onu_traffic')"
        ),
    )
    op.drop_index("ix_jobs_olt_created", table_name="jobs")
    op.drop_index("ix_onu_signal_onu_sampled", table_name="onu_signal_history")
    op.drop_index("ix_activity_logs_action_created", table_name="activity_logs")
    op.drop_index("ix_activity_logs_user_created", table_name="activity_logs")
    op.drop_index("ix_activity_logs_olt_created", table_name="activity_logs")
