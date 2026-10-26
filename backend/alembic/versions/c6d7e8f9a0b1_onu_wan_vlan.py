"""VLAN WAN per-ONU dari running-config (`onus.wan_vlan`).

Modal "Update ONU mode" membuka field "WAN VLAN-ID" kosong karena tidak ada kolom yang
menyimpan VLAN WAN perangkat: `onus.vlan_id` FK master (satu VLAN primer, sering NULL)
dan `onus.service_vlan_ids` adalah SEMUA VLAN service-port (termasuk mgmt/VoIP), jadi
keduanya bukan jawaban "VLAN WAN mana yang dipakai ONU ini".

Sumbernya satu baris nyata di stanza `pon-onu-mng` running-config:

    flow 1 pri 0 vlan 15

`flow 1` = flow milik gemport 1 (layanan WAN). Nomor VLAN disimpan apa adanya (bukan FK):
VLAN yang belum terdaftar di master tetap data nyata. NULL = perangkat tidak melaporkan
baris itu — tidak di-backfill dari kolom lain supaya tidak ada angka karangan.

Revision ID: c6d7e8f9a0b1
Revises: c5d6e7f8a9b0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("onus", sa.Column("wan_vlan", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("onus", "wan_vlan")
