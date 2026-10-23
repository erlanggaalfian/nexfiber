from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ActivityLog(Base):
    """raw_command/raw_output mandatory for every write to an OLT (PRD 4.3/4.6). Retention 1 year.

    Partitioned by month on created_at (PRD Database/Infra 3.2 "wajib partisi") — partition
    key must be part of the PK, hence the composite (id, created_at). Partitions are created
    by the Alembic migration + a monthly cron (see docs/db-maintenance.md), not by the ORM.
    """

    __tablename__ = "activity_logs"
    __table_args__ = {"postgresql_partition_by": "RANGE (created_at)"}

    # Composite PK disables SQLAlchemy's implicit autoincrement, so declare it explicitly.
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("jobs.id"), nullable=True)
    olt_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("olts.id"), nullable=True)
    onu_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("onus.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_command: Mapped[str | None] = mapped_column(nullable=True)
    raw_output: Mapped[str | None] = mapped_column(nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
