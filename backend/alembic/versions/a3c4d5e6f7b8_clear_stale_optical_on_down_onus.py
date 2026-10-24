"""Bersihkan nilai optik palsu pada ONU yang tidak online (bug "ONU down Rx -30 dBm").

Sejak sync_service mengosongkan kolom optik saat ONU turun, baris lama masih menyimpan
angka terakhir dan UI menampilkannya seolah ONU masih punya sinyal. Migrasi ini hanya
men-set kolom optik jadi NULL untuk ONU yang statusnya bukan 'online' — TIDAK menghapus
baris apa pun, dan riwayat (onu_signal_history) tidak disentuh sehingga angka terakhir
tetap bisa dilihat di grafik. Downgrade tidak bisa mengembalikan angka lama (dan tidak
perlu: angka itu memang tidak sahih), jadi downgrade sengaja tidak melakukan apa-apa.

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6a7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c4d5e6f7b8"
down_revision: str | None = "f2b3c4d5e6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE onus
        SET rx_power_dbm = NULL, tx_power_dbm = NULL, olt_rx_power_dbm = NULL,
            temperature_c = NULL, voltage_v = NULL, bias_current_ma = NULL
        WHERE deleted_at IS NULL AND status <> 'online'
          AND (rx_power_dbm IS NOT NULL OR tx_power_dbm IS NOT NULL
               OR olt_rx_power_dbm IS NOT NULL OR temperature_c IS NOT NULL
               OR voltage_v IS NOT NULL OR bias_current_ma IS NOT NULL)
    """))


def downgrade() -> None:
    """Tidak ada yang dipulihkan: nilai lama tidak sahih dan ada di onu_signal_history."""
