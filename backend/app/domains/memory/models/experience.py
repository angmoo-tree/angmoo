"""Owned experience copies. Source identifiers deliberately have no source FK."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MemoryExperienceSnapshot(Base):
    __tablename__ = "memory_experience_snapshots"
    __table_args__ = (CheckConstraint(
        "status IN ('historical_snapshot','partial_snapshot','snapshot_unavailable')",
        name="ck_memory_experience_status"),)
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryExperienceDependency(Base):
    __tablename__ = "memory_experience_dependencies"
    __table_args__ = (Index("ix_experience_dependency_origin", "scope_setting_id", "origin_memory_id"),)
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    # A flattened deletion dependency, never a runtime source-hydration edge.
    origin_memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)


class MemoryExperienceTombstone(Base):
    __tablename__ = "memory_experience_tombstones"
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), primary_key=True)
    memory_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MemoryExperienceInput(Base):
    __tablename__ = "memory_experience_inputs"
    __table_args__ = (CheckConstraint(
        "state IN ('prepared','submission_uncertain','received','effect_committed','failed','cancelled')",
        name="ck_memory_experience_input_state"),)
    # Same immutable identifier as the original input manifest; no source FK.
    manifest_id: Mapped[str] = mapped_column(ForeignKey("memory_situation_manifests.id", ondelete="CASCADE"), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
