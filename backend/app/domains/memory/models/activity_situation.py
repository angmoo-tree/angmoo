"""Durable admission, application and policy transition owned by Memory."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

SITUATION_TABLES = (
    "memory_situation_settings", "memory_situation_manifests", "memory_situation_runs",
    "memory_situation_requests", "memory_situation_receipts", "memory_situation_info",
    "memory_situation_sources", "memory_situation_transitions", "memory_situation_recheck_attempts",
)


class MemorySituationProcessingSetting(Base):
    __tablename__ = "memory_situation_settings"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_situation_setting_version"),)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True)
    daily_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    local_time: Mapped[str] = mapped_column(String(5), nullable=False, default="22:30", server_default="22:30")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    shutdown_apply_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    last_request_key: Mapped[str | None] = mapped_column(String(128))
    last_request_digest: Mapped[str | None] = mapped_column(String(64))
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brief_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemorySituationManifest(Base):
    __tablename__ = "memory_situation_manifests"
    __table_args__ = (UniqueConstraint("scope_setting_id", "call_identity", name="uq_situation_manifest_call"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)
    call_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemorySituationApplyRun(Base):
    __tablename__ = "memory_situation_runs"
    __table_args__ = (
        CheckConstraint("trigger IN ('scheduled','manual','quit')", name="ck_situation_run_trigger"),
        CheckConstraint("state IN ('pending','running','completed','deferred','error')", name="ck_situation_run_state"),
        CheckConstraint("work_kind IN ('pending_apply','blocked_recheck')", name="ck_situation_run_work_kind"),
        UniqueConstraint("scope_setting_id", "trigger", "request_identity", name="uq_situation_run_identity"),
        Index("ix_situation_run_pending", "state", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    work_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="pending_apply", server_default="pending_apply")
    request_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    cutoff_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settings_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")


class MemorySituationRequest(Base):
    __tablename__ = "memory_situation_requests"
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("memory_situation_runs.id", ondelete="CASCADE"))
    result_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemorySituationReceipt(Base):
    __tablename__ = "memory_situation_receipts"
    __table_args__ = (
        UniqueConstraint("scope_setting_id", "logical_activity_id", "lane", "target_key", name="uq_situation_activity_target"),
        CheckConstraint("lane IN ('chat','inbox','feed','routine')", name="ck_situation_lane"),
        CheckConstraint("description_status IN ('valid','missing','invalid','output_order_invalid')", name="ck_situation_description_status"),
        CheckConstraint("state IN ('pending','claimed','applied','blocked','skipped','error','discarded')", name="ck_situation_receipt_state"),
        CheckConstraint("state_version >= 1", name="ck_situation_receipt_version"),
        CheckConstraint("(state = 'discarded' AND manifest_id IS NULL AND description IS NULL AND applied_item_id IS NULL) OR (state <> 'discarded' AND manifest_id IS NOT NULL)", name="ck_situation_receipt_manifest"),
        Index("ix_situation_receipt_pending", "scope_setting_id", "state", "sequence"),
        {"sqlite_autoincrement": True},
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)
    logical_activity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    lane: Mapped[str] = mapped_column(String(16), nullable=False)
    target_key: Mapped[str] = mapped_column(String(256), nullable=False)
    manifest_id: Mapped[str | None] = mapped_column(ForeignKey("memory_situation_manifests.id", ondelete="CASCADE"))
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    activation_epoch: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    description_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discard_request_key: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(80))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("memory_situation_runs.id", ondelete="SET NULL"))
    applied_item_id: Mapped[str | None] = mapped_column(ForeignKey("memory_items.id", ondelete="SET NULL"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryActivitySituationInfo(Base):
    __tablename__ = "memory_situation_info"
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    receipt_sequence: Mapped[int] = mapped_column(ForeignKey("memory_situation_receipts.sequence", ondelete="CASCADE"), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    locale: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    thought_reference: Mapped[str | None] = mapped_column(String(128))


class MemoryActivitySituationSource(Base):
    __tablename__ = "memory_situation_sources"
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("memory_item_evidence.id", ondelete="SET NULL"))
    source: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)


class MemorySituationRecheckAttempt(Base):
    """One bounded outcome per receipt in a frozen recheck run; no originals."""
    __tablename__ = "memory_situation_recheck_attempts"
    run_id: Mapped[str] = mapped_column(ForeignKey("memory_situation_runs.id", ondelete="CASCADE"), primary_key=True)
    receipt_sequence: Mapped[int] = mapped_column(ForeignKey("memory_situation_receipts.sequence", ondelete="CASCADE"), primary_key=True)
    validation_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    previous_run_id: Mapped[str | None] = mapped_column(ForeignKey("memory_situation_runs.id", ondelete="SET NULL"))
    previous_state: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_error_code: Mapped[str | None] = mapped_column(String(80))
    applied_item_id: Mapped[str | None] = mapped_column(ForeignKey("memory_items.id", ondelete="SET NULL"))
    before_version: Mapped[int] = mapped_column(Integer, nullable=False)
    after_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemorySituationTransition(Base):
    __tablename__ = "memory_situation_transitions"
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    admitted_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    legacy_cutoff: Mapped[int] = mapped_column(Integer, nullable=False)
    discard_key: Mapped[str | None] = mapped_column(String(128))
    discarded_job_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
