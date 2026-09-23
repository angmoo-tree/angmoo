"""Durable relationship interpretation and daily review work (SQLite canonical)."""

from datetime import datetime, date
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.domains.relationships.models.social import JSON_DOCUMENT


class RelationshipPolicy(Base):
    __tablename__ = "relationship_policies"
    __table_args__ = (CheckConstraint("mode IN ('legacy','interpreted')", name="ck_relationship_policy_mode"),)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False, default="legacy")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class RelationshipExperienceReceipt(Base):
    __tablename__ = "relationship_experience_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["actor_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        ForeignKeyConstraint(["target_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        UniqueConstraint("world_id", "actor_world_character_id", "source_kind", "source_key", name="uq_relationship_experience_source"),
        CheckConstraint("actor_world_character_id != target_world_character_id", name="ck_relationship_experience_not_self"),
        Index("ix_relationship_experience_pair_time", "world_id", "actor_world_character_id", "target_world_character_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RelationshipMetricApplication(Base):
    __tablename__ = "relationship_metric_applications"
    __table_args__ = (
        CheckConstraint("status IN ('pending','applied','invalid','superseded')", name="ck_relationship_metric_application_status"),
        Index("ix_relationship_metric_application_pending", "status", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experience_id: Mapped[str] = mapped_column(ForeignKey("relationship_experience_receipts.id"), nullable=False, unique=True)
    decision_key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    actual_delta: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    state_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RelationshipMetricBudget(Base):
    __tablename__ = "relationship_metric_budgets"
    __table_args__ = (
        ForeignKeyConstraint(["actor_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        ForeignKeyConstraint(["target_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
    )
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), primary_key=True)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_world_character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    local_day: Mapped[date] = mapped_column(Date, primary_key=True)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)


class RelationshipReviewWork(Base):
    __tablename__ = "relationship_review_work"
    __table_args__ = (
        ForeignKeyConstraint(["actor_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        ForeignKeyConstraint(["target_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        CheckConstraint("phase IN ('direct','partial','reduce','final')", name="ck_relationship_review_phase"),
        CheckConstraint("status IN ('pending','running','ready','applied','failed','stale')", name="ck_relationship_review_status"),
        UniqueConstraint("world_id", "actor_world_character_id", "target_world_character_id", "period_key", "part_key", name="uq_relationship_review_part"),
        Index("ix_relationship_review_pending", "status", "next_attempt_at", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    period_key: Mapped[str] = mapped_column(String(128), nullable=False)
    part_key: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("relationship_review_work.id"))
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_view_version: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RelationshipReviewMemoryReceipt(Base):
    __tablename__ = "relationship_review_memory_receipts"
    __table_args__ = (
        UniqueConstraint("world_id", "actor_world_character_id", "memory_id", "memory_digest", name="uq_relationship_review_memory"),
        Index("ix_relationship_review_memory_target", "world_id", "actor_world_character_id", "target_world_character_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(ForeignKey("world_characters.id"), nullable=False)
    target_world_character_id: Mapped[str | None] = mapped_column(ForeignKey("world_characters.id"))
    memory_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id"), nullable=False)
    memory_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    work_id: Mapped[str | None] = mapped_column(ForeignKey("relationship_review_work.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
