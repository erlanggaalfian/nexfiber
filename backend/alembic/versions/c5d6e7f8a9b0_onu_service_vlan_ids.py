"""VLAN layanan per-ONU sebagai DAFTAR (`onus.service_vlan_ids`).

Bug nyata (OLT WNG id=158, C320, 247 ONU, SNMP baca-saja 2026-10-26): modal "Update
attached VLANs" selalu terbuka tanpa centang walau ONU jelas punya VLAN. Sebabnya
`onus.vlan_id` hanya SATU FK ke baris `vlans`, jadi ONU multi-layanan kehilangan VLAN
keduanya: perangkat punya `(15, 100)` pada 171 ONU dan `(1021, 100)` pada 4 ONU,
total 187/247 ONU multi-VLAN, tapi DB cuma menyimpan 1 nomor. Selain itu
`GET /api/onus/{sn}` sama sekali tidak punya field daftar VLAN
(`'service_vlans' in payload -> False`), jadi frontend memang tidak pernah
menerima data untuk dicentang.

Kolom ini menyimpan nomor VLAN apa adanya dari perangkat (bukan FK): VLAN yang belum
terdaftar di master `vlans` tetap data nyata dan tidak boleh hilang. `vlan_id` lama
TIDAK dihapus — masih dipakai dialog "Ubah VLAN"/`authorize_onu` yang menulis satu
VLAN primer.

NULL = belum pernah disinkron; `[]` = ONU memang tanpa service-port. Pembeda itu
dipakai UI supaya daftar kosong yang jujur tidak tertukar dengan "data belum ada".

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "onus",
        sa.Column("service_vlan_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Backfill dari `vlan_id` yang sudah ada: lebih baik satu VLAN benar daripada nol
    # centang sampai sync berikutnya jalan. Sync nanti menimpanya dengan daftar penuh
    # dari perangkat. Hanya ONU yang punya VLAN primer — sisanya tetap NULL (belum
    # disinkron), bukan `[]` palsu.
    op.execute("""
        UPDATE onus o
           SET service_vlan_ids = to_jsonb(ARRAY[v.vlan_id])
          FROM vlans v
         WHERE v.id = o.vlan_id
           AND o.vlan_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("onus", "service_vlan_ids")
