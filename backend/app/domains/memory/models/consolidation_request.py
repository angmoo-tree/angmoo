"""Durable trigger receipts; existing jobs retain their identity and retry budget."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MemoryConsolidationRequest(Base):
    __tablename__ = "memory_consolidation_requests"
    __table_args__ = (
        UniqueConstraint("scope_setting_id", "idempotency_key", name="uq_memory_request_key"),
        UniqueConstraint("scope_setting_id", "scheduled_for_utc", name="uq_memory_request_slot"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_digest: Mapped[str] = mapped_column(String(64))
    scheduled_for_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cutoff_sequence: Mapped[int] = mapped_column(Integer)
    scope_version: Mapped[int] = mapped_column(Integer)
    settings_version: Mapped[int] = mapped_column(Integer)
    profile_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), index=True)
    last_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coalesced_to_request_id: Mapped[str | None] = mapped_column(ForeignKey("memory_consolidation_requests.id"))


class MemoryConsolidationJob(Base):
    __tablename__ = "memory_consolidation_jobs"
    request_id: Mapped[str] = mapped_column(ForeignKey("memory_consolidation_requests.id", ondelete="CASCADE"), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("memory_batch_runs.job_id", ondelete="CASCADE"), primary_key=True, index=True)
    phase: Mapped[str] = mapped_column(String(24), default="queued")
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
