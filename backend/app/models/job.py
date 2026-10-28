from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin

JobType = Enum(
    "authorize_onu",
    "delete_onu",
    "reboot_onu",
    "set_state",
    "sync_onu_status",
    "sync_onu_optical",
    "sync_olt_metrics",
    "sync_unconfigured",
    "sample_onu_traffic",
    "backup_olt_config",
    "apply_speed_profile",
    "create_vlan",
    "delete_vlan",
    "set_vlan_ports",
    "set_port_config",
    "push_speed_profile",
    "sync_speed_profiles",
    "tr069_push",
    "test_connection",
    "refresh_onu_detail",
    "resync_onu",
    "set_onu_vlan",
    "replace_onu",
    "restore_factory",
    "read_onu_status",
    "read_onu_running_config",
    "read_onu_software",
    name="job_type",
)
JobStatus = Enum("pending", "running", "success", "failed", "cancelled", name="job_status")


class Job(TimestampMixin, Base):
    """Queue + history table, core of the SKIP LOCKED decision (PRD 4.5.A)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claim", "status", "run_after", "priority"),
        Index("ix_jobs_onu_created", "onu_id", "created_at"),
        Index("ix_jobs_olt_created", "olt_id", "created_at"),
        # Anti-numpuk per ONU: satu job tipe sama per ONU yang masih pending/running.
        # Pengganti cek aplikasi (exists_active_for_onu) yang bisa dilewati balapan dua
        # proses: index inilah yang memutuskan siapa menang.
        Index(
            "uq_jobs_active_per_onu",
            "job_type",
            "onu_id",
            unique=True,
            postgresql_where=text("status IN ('pending','running') AND onu_id IS NOT NULL"),
        ),
        Index(
            "uq_jobs_sync_pending_per_olt",
            "job_type",
            "olt_id",
            unique=True,
            # LIKE on a casted enum needs ::text, whose output function isn't IMMUTABLE and
            # Postgres rejects that in an index predicate — so list the sync_* values explicitly.
            # Diperluas (area 5): backup_olt_config, sync_speed_profiles, dan
            # test_connection adalah operasi satu-OLT yang tidak boleh menumpuk.
            # TIDAK mencakup create/delete_vlan, set_vlan_ports, set_port_config,
            # push_speed_profile: payload-nya berbeda-beda per job dan antrean
            # berurutan lewat CLI lock sudah cukup; unique per-OLT akan menolak
            # operasi berbeda yang sah. Jangan klaim indeks ini mencakup semua job.
            postgresql_where=text(
                "status IN ('pending','running') "
                "AND job_type IN ('sync_onu_status','sync_onu_optical','sync_unconfigured',"
                "'sync_olt_metrics','sample_onu_traffic','backup_olt_config',"
                "'sync_speed_profiles','test_connection')"
            ),
        ),
    )

    job_type: Mapped[str] = mapped_column(JobType, nullable=False)
    status: Mapped[str] = mapped_column(JobStatus, nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    olt_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=True)
    onu_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("onus.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
