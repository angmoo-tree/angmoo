from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.worlds import JSON_DOCUMENT


class WorldCharacterFeedCursor(Base):
    __tablename__ = "world_character_feed_cursors"
    __table_args__ = (
        CheckConstraint(
            "next_keyword_offset IN (0,2,4,6)",
            name="ck_world_character_feed_cursors_offset",
        ),
        CheckConstraint(
            "version >= 1", name="ck_world_character_feed_cursors_version"
        ),
        ForeignKeyConstraint(
            ["world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_feed_cursors_character_scope",
        ),
    )

    world_character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    next_keyword_offset: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_cycle_key: Mapped[str | None] = mapped_column(String(128))
    last_run_id: Mapped[str | None] = mapped_column(String(64))
    last_cycle_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorldCharacterFeedObservation(Base):
    __tablename__ = "world_character_feed_observations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('claimed','observed','retryable_failed')",
            name="ck_world_character_feed_observations_status",
        ),
        CheckConstraint(
            "decision_outcome IS NULL OR decision_outcome IN "
            "('not_selected','action_selected','no_action')",
            name="ck_world_character_feed_observations_outcome",
        ),
        CheckConstraint(
            "selected_action IS NULL OR selected_action IN "
            "('like','comment','repost','follow')",
            name="ck_world_character_feed_observations_action",
        ),
        CheckConstraint(
            "interaction_intent IS NULL OR interaction_intent IN "
            "('ordinary_comment','joint_activity_proposal','proposal_response')",
            name="ck_world_character_feed_observations_intent",
        ),
        CheckConstraint(
            "comment_purpose IS NULL OR comment_purpose IN "
            "('question','advice','empathy','encouragement','information',"
            "'humor','disagreement','competition','observation')",
            name="ck_world_character_feed_observations_purpose",
        ),
        CheckConstraint(
            "reason_code IS NULL OR reason_code IN "
            "('no_searchable_keyword','no_candidate','no_allowed_action',"
            "'model_abstained','proposal_ineligible','proposal_apply_not_ready',"
            "'target_stale','writer_invalid')",
            name="ck_world_character_feed_observations_reason",
        ),
        ForeignKeyConstraint(
            ["observer_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_feed_observations_observer_scope",
        ),
        ForeignKeyConstraint(
            ["post_id", "world_id"],
            ["posts.id", "posts.world_id"],
            name="fk_world_character_feed_observations_post_scope",
        ),
        UniqueConstraint(
            "observer_world_character_id",
            "post_id",
            name="uq_world_character_feed_observations_post",
        ),
        Index(
            "ix_world_character_feed_observations_claim_expiry",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_world_character_feed_observations_character_created",
            "observer_world_character_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observer_world_character_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    post_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    claim_token: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cycle_key: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    matched_keywords: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    matched_fields: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    rank_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    post_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decision_outcome: Mapped[str | None] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    selected_action: Mapped[str | None] = mapped_column(String(24))
    interaction_intent: Mapped[str | None] = mapped_column(String(40))
    comment_purpose: Mapped[str | None] = mapped_column(String(40))
    public_action_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_public_action_executions.id")
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorldCharacterBlock(Base):
    __tablename__ = "world_character_blocks"
    __table_args__ = (
        CheckConstraint(
            "blocker_world_character_id != blocked_world_character_id",
            name="ck_world_character_blocks_not_self",
        ),
        ForeignKeyConstraint(
            ["blocker_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_blocks_blocker_scope",
        ),
        ForeignKeyConstraint(
            ["blocked_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_world_character_blocks_blocked_scope",
        ),
        UniqueConstraint(
            "blocker_world_character_id",
            "blocked_world_character_id",
            name="uq_world_character_blocks_direction",
        ),
        Index("ix_world_character_blocks_world", "world_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    blocker_world_character_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    blocked_world_character_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
