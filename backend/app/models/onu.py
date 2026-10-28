from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

OnuAuthType = Enum("sn", "loid", "password", name="onu_auth_type")
OnuStatus = Enum("online", "offline", "los", "dying_gasp", "power_off", "unknown", name="onu_status")
OnuConfigState = Enum("success", "failed", "configuring", "initial", name="onu_config_state")
OnuAdminState = Enum("enabled", "disabled", name="onu_admin_state")


class Onu(TimestampMixin, Base):
    __tablename__ = "onus"
    __table_args__ = (
        # Partial unique (PRD 4.6): a serial/slot can be reused once the old row is soft-deleted.
        Index(
            "uq_onu_olt_serial",
            "olt_id",
            "serial_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_onu_ponport_index",
            "pon_port_id",
            "onu_index",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Satu port splitter hanya boleh dipakai satu ONU aktif: cek aplikasi
        # sudah ada di authorize/update_info, tetapi balapan persis dua request
        # bersamaan tetap bisa lolos tanpa constraint DB ini. NULL diabaikan
        # Postgres pada unique index (baris tanpa splitter/port tidak saling
        # memblokir), dan baris ter-soft-delete tidak memblokir pemakaian ulang.
        Index(
            "uq_onu_splitter_port",
            "splitter_id",
            "splitter_port",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    olt_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=False)
    pon_port_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pon_ports.id"), nullable=False)
    # ONU ID within PON, 1-128/256. NULL until the authorize job picks a free ID from the OLT.
    onu_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    serial_number: Mapped[str] = mapped_column(String(50), nullable=False)
    auth_type: Mapped[str] = mapped_column(OnuAuthType, nullable=False, default="sn")
    loid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    auth_password_enc: Mapped[bytes | None] = mapped_column(nullable=True)

    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    onu_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hardware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    software_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(OnuStatus, nullable=False, default="unknown")
    config_state: Mapped[str] = mapped_column(OnuConfigState, nullable=False, default="initial")
    match_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    admin_state: Mapped[str] = mapped_column(OnuAdminState, nullable=False, default="enabled")

    rx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    tx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    olt_rx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    voltage_v: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    bias_current_ma: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    vlan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("vlans.id"), nullable=True)
    # VLAN layanan NYATA di perangkat: SEMUA `service-port ... vlan N` ONU ini, urutan
    # perangkat, dedupe. `vlan_id` di atas hanya satu VLAN primer (FK master) dan terbukti
    # kehilangan VLAN kedua pada 187/247 ONU di OLT WNG. NULL = belum pernah disinkron
    # (beda dari `[]` yang berarti ONU memang tidak punya service-port) — pembeda itu
    # dipakai UI untuk tidak menampilkan daftar karangan.
    service_vlan_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # TODO Speed Profile pisah Download/Upload (Opsi A): 1 FK gabungan -> 2 FK per arah.
    download_speed_profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("speed_profiles.id"), nullable=True
    )
    upload_speed_profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("speed_profiles.id"), nullable=True
    )
    splitter_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("splitters.id"), nullable=True)
    line_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    srv_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tr069_profile_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    genieacs_device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Phase 2

    zone_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("zones.id"), nullable=True)
    onu_type_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("onu_types.id"), nullable=True)
    preset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("onu_presets.id"), nullable=True)
    splitter_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    onu_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    wan_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # VLAN WAN NYATA di perangkat: angka pada `flow 1 pri <p> vlan <N>` di stanza
    # `pon-onu-mng` running-config. Bukan FK master (VLAN perangkat belum tentu terdaftar)
    # dan bukan turunan `service_vlan_ids` (daftar itu memuat juga VLAN mgmt/VoIP).
    # NULL = perangkat tidak melaporkan baris itu.
    wan_vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pppoe_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pppoe_password_enc: Mapped[bytes | None] = mapped_column(nullable=True)
    mgmt_ip_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    # IP management: HANYA `Current IP address` host di VLAN bertanda `type ==
    # "management"` (aturan keras; sumber chip "Mgmt IP").
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    # IP WAN: `Current IP address` host di VLAN NON-management (sumber chip "Setup
    # WAN"). Kolom terpisah — tidak pernah diturunkan dari `ip_address` atau
    # sebaliknya; NULL = tidak ada host non-management yang bisa dipasangkan.
    wan_ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_down_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_down_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OnuTrafficHistory(Base):
    """Sampel counter octet per ONU + laju bps yang sudah dihitung saat sampling.

    bps dihitung di backend (bukan di frontend) karena hanya backend yang tahu sampel
    sebelumnya; kalau counter wrap/reset atau OLT tak terjangkau, bps-nya NULL — tidak
    pernah 0 palsu. Counter mentah tetap disimpan supaya laju bisa dihitung ulang kalau
    rumusnya diperbaiki.
    """

    __tablename__ = "onu_traffic_history"
    __table_args__ = (
        Index("ix_onu_traffic_onu_sampled", "onu_id", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    onu_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("onus.id"), nullable=False)
    # Relatif ONU (schemas/onu_traffic.py): in = masuk ke ONU = download pelanggan.
    in_octets: Mapped[int] = mapped_column(Numeric(20, 0), nullable=False)
    out_octets: Mapped[int] = mapped_column(Numeric(20, 0), nullable=False)
    in_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    out_bps: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OnuSignalHistory(Base):
    """Separate from onus so the main row isn't UPDATEd thousands of times/day (PRD 4.6)."""

    __tablename__ = "onu_signal_history"
    __table_args__ = (
        Index("ix_onu_signal_onu_sampled", "onu_id", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    onu_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("onus.id"), nullable=False)
    rx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    tx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    olt_rx_power_dbm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    status: Mapped[str] = mapped_column(OnuStatus, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Asal baris: "status_change" (poll status 1 menit / absent) atau "optical"
    # (poll optik 15 menit). None = baris lama, sumber tidak diketahui (tidak ditebak).
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
