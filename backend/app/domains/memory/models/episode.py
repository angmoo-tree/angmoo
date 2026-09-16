"""Additive episode metadata; MemoryItem remains the canonical situation."""

from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

EPISODE_TABLES = (
    "memory_episode_bundles", "memory_episode_info", "memory_episode_units",
    "memory_episode_unit_evidence", "memory_episode_processed_units", "memory_episode_links",
)


class MemoryEpisodeBundle(Base):
    __tablename__ = "memory_episode_bundles"
    __table_args__ = (
        UniqueConstraint("scope_setting_id", "policy_version", "activation_epoch", "manifest_hash", name="uq_episode_bundle_manifest"),
        CheckConstraint("length(manifest_hash) = 64", name="ck_episode_bundle_hash"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    activation_epoch: Mapped[str] = mapped_column(String(64), nullable=False)
    cutoff_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MemoryEpisodeInfo(Base):
    __tablename__ = "memory_episode_info"
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("memory_episode_bundles.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)


class MemoryEpisodeUnit(Base):
    __tablename__ = "memory_episode_units"
    __table_args__ = (
        UniqueConstraint("memory_item_id", "unit_key", "unit_revision", name="uq_episode_unit"),
        CheckConstraint("chat_thought_message_id IS NULL OR social_thought_id IS NULL", name="ck_episode_unit_thought_owner"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_key: Mapped[str] = mapped_column(String(160), nullable=False)
    unit_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage: Mapped[str] = mapped_column(String(24), nullable=False)
    chat_thought_message_id: Mapped[int | None] = mapped_column(ForeignKey("chat_message_thoughts.message_id", ondelete="SET NULL"))
    social_thought_id: Mapped[str | None] = mapped_column(ForeignKey("social_activity_thoughts.id", ondelete="SET NULL"))
    thought_digest: Mapped[str | None] = mapped_column(String(64))


class MemoryEpisodeUnitEvidence(Base):
    __tablename__ = "memory_episode_unit_evidence"
    unit_id: Mapped[str] = mapped_column(ForeignKey("memory_episode_units.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("memory_item_evidence.id", ondelete="CASCADE"), primary_key=True)
    start_offset: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class MemoryEpisodeProcessedUnit(Base):
    __tablename__ = "memory_episode_processed_units"
    __table_args__ = (
        UniqueConstraint("scope_setting_id", "policy_version", "activation_epoch", "unit_key", "unit_revision", name="uq_episode_processed_unit"),
        CheckConstraint("decision IN ('used','skipped')", name="ck_episode_processed_decision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("memory_episode_bundles.id", ondelete="CASCADE"), nullable=False)
    scope_setting_id: Mapped[str] = mapped_column(ForeignKey("memory_scope_settings.id", ondelete="CASCADE"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    activation_epoch: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_key: Mapped[str] = mapped_column(String(160), nullable=False)
    unit_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)


class MemoryEpisodeLink(Base):
    __tablename__ = "memory_episode_links"
    __table_args__ = (
        CheckConstraint("prior_item_id <> following_item_id", name="ck_episode_link_not_self"),
        Index("ix_episode_link_following", "following_item_id"),
    )
    prior_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    following_item_id: Mapped[str] = mapped_column(ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
