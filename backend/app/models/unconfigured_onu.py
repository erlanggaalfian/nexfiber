from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UnconfiguredOnu(Base):
    """Latest sync_unconfigured scan per OLT; feeds /onus/pending. Rows not seen in a
    successful scan are deleted, and a row is removed once its ONU is authorized.
    """

    __tablename__ = "unconfigured_onus"
    __table_args__ = (
        UniqueConstraint("olt_id", "serial_number", name="uq_unconfigured_olt_serial"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    olt_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=False)
    pon_port_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pon_ports.id"), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(50), nullable=False)
    onu_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
