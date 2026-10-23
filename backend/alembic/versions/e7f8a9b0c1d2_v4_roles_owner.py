"""v4 roles superadmin/admin/user, users.admin_id, olts.owner_id (PRD 3.7, 4.6)

Generic mapping for any DB: admin -> superadmin, every other role -> user under the first
superadmin; existing OLTs are owned by that superadmin.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-10-25 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FIRST_SUPERADMIN = "(SELECT min(id) FROM users WHERE role = 'superadmin')"

def upgrade() -> None:
    op.execute("CREATE TYPE user_role_v4 AS ENUM ('superadmin', 'admin', 'user')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role_v4 USING "
        "(CASE WHEN role = 'admin' THEN 'superadmin' ELSE 'user' END)::user_role_v4"
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_v4 RENAME TO user_role")

    op.add_column("users", sa.Column("admin_id", sa.BigInteger(),
                                     sa.ForeignKey("users.id"), nullable=True))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(),
                                     server_default=sa.false(), nullable=False))
    op.alter_column("users", "email", nullable=True)
    op.execute(f"UPDATE users SET admin_id = {FIRST_SUPERADMIN} WHERE role = 'user'")
    op.create_check_constraint("ck_users_admin_id", "users",
                               "(role = 'user') = (admin_id IS NOT NULL)")

    op.add_column("olts", sa.Column("owner_id", sa.BigInteger(),
                                    sa.ForeignKey("users.id"), nullable=True))
    op.add_column("olts", sa.Column("snmp_community_rw_enc", sa.LargeBinary(), nullable=True))
    op.execute(f"UPDATE olts SET owner_id = {FIRST_SUPERADMIN}")
    op.alter_column("olts", "owner_id", nullable=False)
    op.create_index("ix_olts_owner_id", "olts", ["owner_id"])

def downgrade() -> None:
    op.drop_index("ix_olts_owner_id", "olts")
    op.drop_column("olts", "snmp_community_rw_enc")
    op.drop_column("olts", "owner_id")
    op.drop_constraint("ck_users_admin_id", "users")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "admin_id")
    op.execute("CREATE TYPE user_role_v3 AS ENUM ('admin', 'noc', 'teknisi', 'viewer')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role_v3 USING "
        "(CASE WHEN role = 'user' THEN 'teknisi' ELSE 'admin' END)::user_role_v3"
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_v3 RENAME TO user_role")
