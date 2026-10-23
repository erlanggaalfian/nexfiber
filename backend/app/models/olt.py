from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
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
    __table_args__ = (UniqueConstraint("host", "cli_port", name="uq_olt_host_cliport"),)

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
    snmp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=161)
    pon_port_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_onu_per_port: Mapped[int] = mapped_column(Integer, nullable=False, default=128)
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    status: Mapped[str] = mapped_column(OltStatus, nullable=False, default="unreachable")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    onu_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
