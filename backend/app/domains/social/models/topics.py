"""Canonical recommendation metadata. Posts and approved profiles remain sources."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (JSON, CheckConstraint, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class RecommendationCatalog(Base):
    __tablename__ = "social_recommendation_catalogs"

    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Fixed once; eligibility additionally requires an explicit native creation receipt.
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    key_world_character_id: Mapped[str | None] = mapped_column(ForeignKey("world_characters.id", ondelete="SET NULL"))


class RecommendationTopic(Base):
    __tablename__ = "social_recommendation_topics"
    __table_args__ = (
        UniqueConstraint("scope_key", "normalized_name", name="uq_social_topic_name_scope"),
        CheckConstraint("(scope_key = 'common' AND world_id IS NULL) OR (world_id IS NOT NULL AND scope_key = world_id)", name="ck_social_topic_scope"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    world_id: Mapped[str | None] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)


class RecommendationTopicSource(Base):
    """Current World/character links, not historical post references."""
    __tablename__ = "social_recommendation_topic_sources"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"],
                             ["world_characters.id", "world_characters.world_id"], ondelete="CASCADE"),
        UniqueConstraint("world_id", "source_key", "topic_id", name="uq_social_topic_source"),
        Index("ix_social_topic_source_character", "world_character_id", "topic_id"),
        Index("ix_social_topic_source_world", "world_id", "topic_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str | None] = mapped_column(String(64))
    topic_id: Mapped[str] = mapped_column(ForeignKey("social_recommendation_topics.id", ondelete="CASCADE"), nullable=False)


class RecommendationPost(Base):
    """An absent receipt means ineligible, including imported and pre-cutover posts."""
    __tablename__ = "social_recommendation_posts"
    __table_args__ = (
        ForeignKeyConstraint(["post_id", "world_id"], ["posts.id", "posts.world_id"], ondelete="CASCADE"),
        UniqueConstraint("post_id", "world_id", name="uq_social_recommendation_post_scope"),
        Index("ix_social_recommendation_post_world_created", "world_id", "created_at", "post_id"),
    )

    post_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature_body_digest: Mapped[str | None] = mapped_column(String(64))
    final_signature: Mapped[str | None] = mapped_column(String(300))
    matched_catalog_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RecommendationPostTopic(Base):
    __tablename__ = "social_recommendation_post_topics"
    __table_args__ = (
        ForeignKeyConstraint(["post_id", "world_id"],
                             ["social_recommendation_posts.post_id", "social_recommendation_posts.world_id"], ondelete="CASCADE"),
        Index("ix_social_recommendation_topic_recent", "world_id", "topic_id", "created_at", "post_id"),
    )

    post_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("social_recommendation_topics.id", ondelete="CASCADE"), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationPreparation(Base):
    __tablename__ = "social_recommendation_preparations"
    __table_args__ = (
        UniqueConstraint("world_id", "source_key", name="uq_social_recommendation_preparation_source"),
        ForeignKeyConstraint(["world_character_id", "world_id"],
                             ["world_characters.id", "world_characters.world_id"], ondelete="CASCADE"),
        CheckConstraint("state IN ('pending','running','ready','failed','stale')", name="ck_social_topic_preparation_state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    source_digest: Mapped[str | None] = mapped_column(String(64))
    applied_digest: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_code: Mapped[str | None] = mapped_column(String(64))


class RecommendationDelivery(Base):
    __tablename__ = "social_recommendation_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"],
                             ["world_characters.id", "world_characters.world_id"], ondelete="CASCADE"),
        UniqueConstraint("world_character_id", "cycle_key", name="uq_social_recommendation_delivery_cycle"),
        CheckConstraint("state IN ('prepared','dispatched','uncertain','delivered')", name="ck_social_recommendation_delivery_state"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cycle_key: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    post_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    trace: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
