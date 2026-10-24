from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin


class SpeedProfile(TimestampMixin, Base):
    __tablename__ = "speed_profiles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    download_kbps: Mapped[int] = mapped_column(Integer, nullable=False)
    upload_kbps: Mapped[int] = mapped_column(Integer, nullable=False)
    olt_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("olts.id"), nullable=True
    )  # NULL = applies to all OLTs
    vlan_db_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vlans.id", name="fk_speed_profiles_vlan_db_id"), nullable=True
    )  # dropdown VLAN existing (read-only di halaman Speed Profile, DECISIONS)
    dba_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dba_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # type1-4
    line_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    srv_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tcont_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
