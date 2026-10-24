from sqlalchemy import BigInteger, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin


class Zone(TimestampMixin, Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_zone_owner_name"),)

    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
