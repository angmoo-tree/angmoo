"""Canonical SQLAlchemy persistence for Memory schema v1."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domains.memory.domain.provenance import (
    MemoryCandidateStatus,
    MemoryHotBriefStatus,
    MemoryItemStatus,
    MemoryJobStatus,
    MemoryKindV1,
    MemoryProviderMode,
    MemorySourceTypeV1,
)
from app.domains.memory.domain.retention import DEFAULT_MEMORY_RETENTION_DAYS


def _sql_values(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


MEMORY_SCHEMA_V1_TABLES = (
    "memory_scope_settings",
    "memory_candidates",
    "memory_items",
    "memory_item_evidence",
    "memory_hot_briefs",
    "memory_hot_brief_items",
    "memory_maintenance_jobs",
)


class MemoryScopeSettingModel(Base):
    __tablename__ = "memory_scope_settings"
    __table_args__ = (
        CheckConstraint(
            f"provider_mode IN ({_sql_values(MemoryProviderMode.values())})",
            name="ck_memory_scope_settings_provider_mode",
        ),
        CheckConstraint(
            "retention_days BETWEEN 1 AND 3650",
            name="ck_memory_scope_settings_retention_days",
        ),
        CheckConstraint("version >= 1", name="ck_memory_scope_settings_version"),
        ForeignKeyConstraint(
            ["subject_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_memory_scope_settings_subject_world",
        ),
        UniqueConstraint(
            "owner_id",
            "world_id",
            "subject_world_character_id",
            name="uq_memory_scope_settings_scope",
        ),
        Index(
            "ix_memory_scope_settings_owner_world",
            "owner_id",
            "world_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    subject_world_character_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    retention_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MEMORY_RETENTION_DAYS,
        server_default=str(DEFAULT_MEMORY_RETENTION_DAYS),
    )
    provider_mode: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=MemoryProviderMode.NONE.value,
        server_default=MemoryProviderMode.NONE.value,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MemoryCandidate(Base):
    __tablename__ = "memory_candidates"
    __table_args__ = (
        CheckConstraint(
            f"source_type IN ({_sql_values(MemorySourceTypeV1.values())})",
            name="ck_memory_candidates_source_type",
        ),
        CheckConstraint(
            "memory_kind_hint IS NULL OR memory_kind_hint IN "
            f"({_sql_values(MemoryKindV1.values())})",
            name="ck_memory_candidates_kind_hint",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(MemoryCandidateStatus.values())})",
            name="ck_memory_candidates_status",
        ),
        CheckConstraint(
            "length(source_digest) = 64",
            name="ck_memory_candidates_source_digest",
        ),
        CheckConstraint("version >= 1", name="ck_memory_candidates_version"),
        CheckConstraint(
            "(status = 'pending' AND decided_at IS NULL) OR "
            "(status IN ('accepted','rejected') AND decided_at IS NOT NULL)",
            name="ck_memory_candidates_decision_time",
        ),
        UniqueConstraint(
            "scope_setting_id",
            "idempotency_key",
            name="uq_memory_candidates_scope_idempotency",
        ),
        Index(
            "ix_memory_candidates_scope_status_created",
            "scope_setting_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_memory_candidates_source",
            "source_type",
            "source_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_kind_hint: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemoryCandidateStatus.PENDING.value,
        server_default=MemoryCandidateStatus.PENDING.value,
    )
    reason_code: Mapped[str | None] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryItem(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        CheckConstraint(
            f"memory_kind IN ({_sql_values(MemoryKindV1.values())})",
            name="ck_memory_items_kind",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(MemoryItemStatus.values())})",
            name="ck_memory_items_status",
        ),
        CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name="ck_memory_items_confidence",
        ),
        CheckConstraint(
            "salience BETWEEN 0.0 AND 1.0",
            name="ck_memory_items_salience",
        ),
        CheckConstraint("length(trim(summary)) > 0", name="ck_memory_items_summary"),
        CheckConstraint("version >= 1", name="ck_memory_items_version"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_memory_items_validity",
        ),
        CheckConstraint(
            "(status = 'active' AND superseded_by_id IS NULL AND deleted_at IS NULL) OR "
            "(status = 'superseded' AND superseded_by_id IS NOT NULL "
            "AND deleted_at IS NULL) OR "
            "(status = 'deleted' AND superseded_by_id IS NULL "
            "AND deleted_at IS NOT NULL)",
            name="ck_memory_items_lifecycle",
        ),
        CheckConstraint(
            "superseded_by_id IS NULL OR superseded_by_id <> id",
            name="ck_memory_items_not_self_superseded",
        ),
        CheckConstraint(
            "memory_kind NOT IN "
            "('DIRECTIONAL_RELATIONSHIP','ACCEPTED_JOINT_COMMITMENT') OR "
            "counterpart_world_character_id IS NOT NULL",
            name="ck_memory_items_counterpart_required",
        ),
        CheckConstraint(
            "memory_kind <> 'THREAD_SUMMARY' OR thread_id IS NOT NULL",
            name="ck_memory_items_thread_required",
        ),
        ForeignKeyConstraint(
            ["subject_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_memory_items_subject_world",
        ),
        ForeignKeyConstraint(
            ["counterpart_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_memory_items_counterpart_world",
        ),
        Index(
            "ix_memory_items_scope_status_validity",
            "owner_id",
            "world_id",
            "subject_world_character_id",
            "status",
            "valid_until",
        ),
        Index(
            "ix_memory_items_counterpart_kind",
            "world_id",
            "subject_world_character_id",
            "counterpart_world_character_id",
            "memory_kind",
        ),
        Index("ix_memory_items_thread_status", "thread_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    subject_world_character_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    counterpart_world_character_id: Mapped[str | None] = mapped_column(String(64))
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("message_threads.id"))
    memory_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemoryItemStatus.ACTIVE.value,
        server_default=MemoryItemStatus.ACTIVE.value,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    salience: Mapped[float] = mapped_column(Float, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_items.id")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MemoryItemEvidence(Base):
    __tablename__ = "memory_item_evidence"
    __table_args__ = (
        CheckConstraint(
            f"source_type IN ({_sql_values(MemorySourceTypeV1.values())})",
            name="ck_memory_item_evidence_source_type",
        ),
        CheckConstraint(
            "length(source_digest) = 64",
            name="ck_memory_item_evidence_source_digest",
        ),
        ForeignKeyConstraint(
            ["actor_world_character_id", "source_world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_memory_item_evidence_actor_world",
        ),
        ForeignKeyConstraint(
            ["target_world_character_id", "source_world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_memory_item_evidence_target_world",
        ),
        UniqueConstraint(
            "memory_item_id",
            "source_type",
            "source_id",
            "source_digest",
            name="uq_memory_item_evidence_source",
        ),
        Index(
            "ix_memory_item_evidence_source",
            "source_type",
            "source_id",
        ),
        Index("ix_memory_item_evidence_event", "source_event_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_item_id: Mapped[str] = mapped_column(
        ForeignKey("memory_items.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(64))
    source_world_id: Mapped[str] = mapped_column(
        ForeignKey("worlds.id"), nullable=False
    )
    actor_world_character_id: Mapped[str | None] = mapped_column(String(64))
    target_world_character_id: Mapped[str | None] = mapped_column(String(64))
    observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("world_character_feed_observations.id")
    )
    source_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryHotBrief(Base):
    __tablename__ = "memory_hot_briefs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(MemoryHotBriefStatus.values())})",
            name="ck_memory_hot_briefs_status",
        ),
        CheckConstraint("generation >= 1", name="ck_memory_hot_briefs_generation"),
        CheckConstraint(
            "length(source_item_set_digest) = 64",
            name="ck_memory_hot_briefs_source_digest",
        ),
        CheckConstraint(
            "(status = 'active' AND superseded_at IS NULL) OR "
            "(status IN ('superseded','invalidated') AND superseded_at IS NOT NULL)",
            name="ck_memory_hot_briefs_lifecycle",
        ),
        UniqueConstraint(
            "scope_setting_id",
            "generation",
            name="uq_memory_hot_briefs_scope_generation",
        ),
        Index(
            "ix_memory_hot_briefs_scope_status",
            "scope_setting_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    source_item_high_watermark: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    source_item_set_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemoryHotBriefStatus.ACTIVE.value,
        server_default=MemoryHotBriefStatus.ACTIVE.value,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryHotBriefItem(Base):
    __tablename__ = "memory_hot_brief_items"
    __table_args__ = (
        CheckConstraint(
            "memory_item_version >= 1",
            name="ck_memory_hot_brief_items_version",
        ),
        Index("ix_memory_hot_brief_items_memory", "memory_item_id"),
    )

    brief_id: Mapped[str] = mapped_column(
        ForeignKey("memory_hot_briefs.id"), primary_key=True
    )
    memory_item_id: Mapped[str] = mapped_column(
        ForeignKey("memory_items.id"), primary_key=True
    )
    memory_item_version: Mapped[int] = mapped_column(Integer, nullable=False)


class MemoryMaintenanceJob(Base):
    __tablename__ = "memory_maintenance_jobs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_values(MemoryJobStatus.values())})",
            name="ck_memory_maintenance_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_memory_maintenance_jobs_attempt_count",
        ),
        CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)",
            name="ck_memory_maintenance_jobs_lease_pair",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND completed_at IS NULL "
            "AND lease_token IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL "
            "AND completed_at IS NULL AND lease_token IS NOT NULL) OR "
            "(status IN ('succeeded','failed','cancelled') "
            "AND completed_at IS NOT NULL AND lease_token IS NULL)",
            name="ck_memory_maintenance_jobs_lifecycle",
        ),
        UniqueConstraint(
            "scope_setting_id",
            "idempotency_key",
            name="uq_memory_maintenance_jobs_scope_idempotency",
        ),
        Index(
            "ix_memory_maintenance_jobs_status_created",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(
        ForeignKey("memory_scope_settings.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemoryJobStatus.PENDING.value,
        server_default=MemoryJobStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def create_memory_schema_v1(connection: Connection) -> None:
    Base.metadata.create_all(
        connection,
        tables=[Base.metadata.tables[name] for name in MEMORY_SCHEMA_V1_TABLES],
        checkfirst=False,
    )


def drop_memory_schema_v1(connection: Connection) -> None:
    Base.metadata.drop_all(
        connection,
        tables=[Base.metadata.tables[name] for name in reversed(MEMORY_SCHEMA_V1_TABLES)],
        checkfirst=False,
    )


__all__ = [
    "MEMORY_SCHEMA_V1_TABLES",
    "MemoryCandidate",
    "MemoryHotBrief",
    "MemoryHotBriefItem",
    "MemoryItem",
    "MemoryItemEvidence",
    "MemoryMaintenanceJob",
    "MemoryScopeSettingModel",
    "create_memory_schema_v1",
    "drop_memory_schema_v1",
]
