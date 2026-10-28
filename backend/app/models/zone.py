from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin


class Zone(TimestampMixin, Base):
    __tablename__ = "zones"
    # Case-insensitive, sesuai cek aplikasi (lower(name)): "Jakarta" dan
    # "jakarta" milik owner yang sama tidak boleh jadi dua baris.
    __table_args__ = (
        Index("uq_zone_owner_name_lower", "owner_id", text("lower(name)"), unique=True),
    )

    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
