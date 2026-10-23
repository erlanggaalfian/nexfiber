from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

VlanType = Enum("internet", "management", "voip", "iptv", "other", name="vlan_type")
TagAction = Enum("transparent", "translate", "tag", name="vlan_tag_action")


class Vlan(TimestampMixin, Base):
    __tablename__ = "vlans"
    __table_args__ = (UniqueConstraint("olt_id", "vlan_id", name="uq_vlan_olt_vlanid"),)

    olt_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("olts.id"), nullable=True
    )  # NULL = global VLAN
    vlan_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4094
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(VlanType, nullable=False, default="internet")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gemport: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag_action: Mapped[str] = mapped_column(TagAction, nullable=False, default="tag")
    user_vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
