from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

SplitterType = Enum("odc", "odp", name="splitter_type")


class Splitter(TimestampMixin, Base):
    __tablename__ = "splitters"

    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("splitters.id"), nullable=True
    )  # ODC -> ODP chaining
    olt_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=True)
    pon_port_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pon_ports.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(SplitterType, nullable=False)
    ratio: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 1:8, 1:16, 1:32, 1:64
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_ports: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    insertion_loss_db: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
