from sqlalchemy import Boolean, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

OnuPonType = Enum("gpon", "epon", "xgpon", "xgspon", name="onu_type_pon_type")
OnuTypeCapability = Enum("bridging", "bridging_routing", name="onu_type_capability")


class OnuType(TimestampMixin, Base):
    """Global catalog (managed by Superadmin), not owner-scoped — PRD 4.6."""

    __tablename__ = "onu_types"
    __table_args__ = (
        Index("uq_onu_type_name", "name", unique=True),
    )

    pon_type: Mapped[str] = mapped_column(OnuPonType, nullable=False, default="gpon")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    eth_ports: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    wifi_ssids: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    voip_ports: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catv: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capability: Mapped[str] = mapped_column(OnuTypeCapability, nullable=False, default="bridging")
    allow_custom_profiles: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
