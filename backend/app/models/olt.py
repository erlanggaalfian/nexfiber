from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

OltVendor = Enum("zte", "cdata", name="olt_vendor")  # MVP driver only supports zte (PRD trade-off #1)
CliProtocol = Enum("ssh", "telnet", name="olt_cli_protocol")
OltStatus = Enum("online", "offline", "unreachable", name="olt_status")


class Olt(TimestampMixin, Base):
    __tablename__ = "olts"
    # Partial unique: OLT ter-soft-delete tidak lagi memblokir OLT pengganti
    # dengan host/port yang sama (baris terhapus dikecualikan dari index).
    __table_args__ = (
        Index(
            "uq_olt_host_cliport", "host", "cli_port", unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(INET, nullable=False)
    vendor: Mapped[str] = mapped_column(OltVendor, nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cli_protocol: Mapped[str] = mapped_column(CliProtocol, nullable=False, default="ssh")
    cli_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    cli_username: Mapped[str] = mapped_column(String(100), nullable=False)
    cli_password_enc: Mapped[bytes] = mapped_column(nullable=False)
    cli_enable_password_enc: Mapped[bytes | None] = mapped_column(nullable=True)
    snmp_version: Mapped[str] = mapped_column(String(10), nullable=False, default="2c")
    snmp_community_enc: Mapped[bytes] = mapped_column(nullable=False)
    snmp_community_rw_enc: Mapped[bytes | None] = mapped_column(nullable=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    snmp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=161)
    pon_port_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_onu_per_port: Mapped[int] = mapped_column(Integer, nullable=False, default=128)
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    status: Mapped[str] = mapped_column(OltStatus, nullable=False, default="unreachable")
    # Kesehatan perangkat (DECISIONS "Kesehatan OLT — skema DB"): kolom langsung di olts,
    # data per-card sebagai JSONB. Diisi job sync_olt_metrics tiap 15 menit.
    cpu_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ram_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    software_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Info sistem SNMP standar (sysName/sysLocation), ikut siklus health yang sama.
    sys_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sys_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cards: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Nama port uplink hasil scan (gei_1/5/1, ...), pilihan port di tab VLANs.
    uplink_ports: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OltAccess(Base):
    """Akses tambahan ke satu OLT untuk Admin/Superadmin lain (PRD 3.7 aturan 1 diperluas:
    `olts.owner_id` tetap pemilik utama, baris di sini hanya menambah yang boleh melihat/
    mengelola). Tabel junction murni: tanpa id/timestamp, PK gabungan."""

    __tablename__ = "olt_access"

    olt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("olts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class PonPort(TimestampMixin, Base):
    __tablename__ = "pon_ports"
    __table_args__ = (UniqueConstraint("olt_id", "slot", "port", name="uq_ponport_olt_slot_port"),)

    olt_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    ifindex: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    oper_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    rx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # onu_count DIHAPUS pada migrasi area4-2026-10-28: tidak pernah dibaca/
    # ditulis kode mana pun — PonPortOut.onu_count diisi dari hitungan query
    # di olt_repo/olt_service, bukan dari kolom ini.
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OltConfigBackup(Base):
    __tablename__ = "olt_config_backups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    olt_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=False)
    config_text: Mapped[str] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
