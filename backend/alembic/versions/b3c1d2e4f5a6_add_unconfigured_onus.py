"""add unconfigured_onus

Revision ID: b3c1d2e4f5a6
Revises: 8611cae7ba13
Create Date: 2026-10-24 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, None] = '8611cae7ba13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'unconfigured_onus',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('olt_id', sa.BigInteger(), nullable=False),
        sa.Column('pon_port_id', sa.BigInteger(), nullable=False),
        sa.Column('serial_number', sa.String(length=50), nullable=False),
        sa.Column('onu_type', sa.String(length=50), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['olt_id'], ['olts.id']),
        sa.ForeignKeyConstraint(['pon_port_id'], ['pon_ports.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('olt_id', 'serial_number', name='uq_unconfigured_olt_serial'),
    )

def downgrade() -> None:
    op.drop_table('unconfigured_onus')
