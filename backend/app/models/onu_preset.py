from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

OnuPresetMode = Enum("routing", "bridging", name="onu_preset_onu_mode")
OnuPresetWanMode = Enum("webpage", "dhcp", "static", "pppoe", name="onu_preset_wan_mode")


class OnuPreset(TimestampMixin, Base):
    """Config template picked when authorizing an ONU — name matched per-OLT at use (PRD 4.6)."""

    __tablename__ = "onu_presets"

    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    onu_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("onu_types.id"), nullable=False)
    vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_profile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    upload_profile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    onu_mode: Mapped[str] = mapped_column(OnuPresetMode, nullable=False, default="routing")
    wan_mode: Mapped[str] = mapped_column(OnuPresetWanMode, nullable=False, default="dhcp")
    zone_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("zones.id"), nullable=True)
    splitter_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("splitters.id"), nullable=True)
