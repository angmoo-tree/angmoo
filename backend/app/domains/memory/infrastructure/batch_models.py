"""Additive durable settings, admission and batch audit; canonical content stays in sources."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


MEMORY_BATCH_TABLES = (
    "memory_batch_profiles",
    "memory_batch_settings",
    "memory_activation_epochs",
    "memory_source_deliveries",
    "memory_batch_runs",
    "memory_selection_decisions",
)


class MemoryBatchProfile(Base):
    __tablename__ = "memory_batch_profiles"
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MemoryBatchSetting(Base):
    __tablename__ = "memory_batch_settings"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_memory_batch_setting_version"),
    )
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True
    )
    ai_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    consent_version: Mapped[str | None] = mapped_column(String(48))
    shutdown_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    schedule_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    local_time: Mapped[str] = mapped_column(
        String(5), nullable=False, default="22:30", server_default="22:30"
    )
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_consumed_date: Mapped[str | None] = mapped_column(String(10))
    trigger_cutoff: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trigger_kind: Mapped[str | None] = mapped_column(String(16))
    trigger_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brief_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_request_key: Mapped[str | None] = mapped_column(String(128))
    last_request_digest: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MemoryActivationEpoch(Base):
    __tablename__ = "memory_activation_epochs"
    __table_args__ = (
        UniqueConstraint(
            "scope_setting_id", "scope_version", name="uq_memory_activation_version"
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemorySourceDelivery(Base):
    __tablename__ = "memory_source_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "scope_setting_id",
            "source_type",
            "source_id",
            name="uq_memory_source_delivery",
        ),
        CheckConstraint(
            "state IN ('pending','delivered','invalidated')",
            name="ck_memory_delivery_state",
        ),
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    epoch_id: Mapped[str] = mapped_column(
        ForeignKey("memory_activation_epochs.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_candidates.id", ondelete="SET NULL")
    )
    batch_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_maintenance_jobs.id", ondelete="SET NULL"), index=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(80))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MemoryBatchRun(Base):
    __tablename__ = "memory_batch_runs"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('scheduled','shutdown','recovery','explicit')",
            name="ck_memory_batch_trigger",
        ),
        CheckConstraint(
            "physical_calls >= 0 AND physical_calls <= 3", name="ck_memory_batch_calls"
        ),
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("memory_maintenance_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    cutoff_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="memory-batch.v2"
    )
    physical_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_code: Mapped[str | None] = mapped_column(String(80))
    provider_latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    thought_tokens: Mapped[int | None] = mapped_column(Integer)


class MemorySelectionDecisionModel(Base):
    __tablename__ = "memory_selection_decisions"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_memory_selection_candidate"),
        CheckConstraint(
            "decision IN ('retain','skip','invalidated')",
            name="ck_memory_selection_decision",
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("memory_batch_runs.job_id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("memory_candidates.id", ondelete="CASCADE"), nullable=False
    )
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_items.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def create_memory_batch_schema(connection: Connection) -> None:
    for name in MEMORY_BATCH_TABLES:
        Base.metadata.tables[name].create(connection, checkfirst=False)
