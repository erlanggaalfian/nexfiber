from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

SpeedProfileDirection = Enum("download", "upload", name="speed_profile_direction")


class SpeedProfile(TimestampMixin, Base):
    """Satu baris = satu arah (Opsi A, TODO Speed Profile pisah Download/Upload):
    sebelumnya satu profile menyimpan download_kbps + upload_kbps sekaligus, sekarang
    tiap arah punya baris + nama + device profile sendiri supaya kombinasi download/upload
    bebas dipasangkan per ONU.
    """

    __tablename__ = "speed_profiles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(SpeedProfileDirection, nullable=False)
    speed_kbps: Mapped[int] = mapped_column(Integer, nullable=False)
    olt_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("olts.id"), nullable=True
    )  # NULL = applies to all OLTs
    vlan_db_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vlans.id", name="fk_speed_profiles_vlan_db_id"), nullable=True
    )  # dropdown VLAN existing (read-only di halaman Speed Profile, DECISIONS)
    dba_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dba_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # type1-4
    # Nama profile di device (mis. <name>_UP untuk upload, <name>_DN untuk download) — diisi
    # saat push_to_olt. Satu baris = satu arah, jadi cukup satu field (dulu line/srv terpisah).
    device_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tcont_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
