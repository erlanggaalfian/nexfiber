from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

SplitterType = Enum("odc", "odp", name="splitter_type")


class Splitter(TimestampMixin, Base):
    __tablename__ = "splitters"
    # Identitas get_or_create: code unik per OLT. NULL dianggap berbeda oleh
    # Postgres, jadi splitter tanpa code tidak saling memblokir.
    __table_args__ = (
        Index("uq_splitter_olt_code", "olt_id", "code", unique=True),
    )

    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("splitters.id"), nullable=True
    )  # ODC -> ODP chaining
    olt_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=True)
    pon_port_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pon_ports.id"), nullable=True
    )
    zone_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("zones.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(SplitterType, nullable=False)
    ratio: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 1:8, 1:16, 1:32, 1:64
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # used_ports DIHAPUS pada migrasi area4-2026-10-28: tidak pernah dibaca/
    # ditulis kode mana pun (grep: hanya definisi model + migrasi awal), dan
    # tidak ada di SplitterOut maupun frontend. Jumlah port terpakai yang
    # benar dihitung dari Onu.splitter_id (lihat master_data_repo._onu_count).
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    insertion_loss_db: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
