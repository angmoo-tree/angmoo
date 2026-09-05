"""Routine activity settings, durable runs, slots, feed cues and execution records."""
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from app.core import active_hours
from app.domains.routines.constants import DEFAULT_MAX_COMMENTS_PER_DAY, DEFAULT_MAX_POSTS_PER_DAY


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    credential_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("llm_credentials.id"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_key: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_auth_key: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running")
    gateway_result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AgentActivityLog(Base):
    __tablename__ = "agent_activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    character: Mapped["Character"] = relationship()


class AgentFeedCue(Base):
    __tablename__ = "agent_feed_cues"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    consumed_run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id"))
    consumed_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    character: Mapped["Character"] = relationship()


class AgentPublicActionExecution(Base):
    __tablename__ = "agent_public_action_executions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    signature: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"), index=True)
    target_profile_type: Mapped[Optional[str]] = mapped_column(String(40))
    target_profile_id: Mapped[Optional[str]] = mapped_column(String(64))
    world_id: Mapped[Optional[str]] = mapped_column(ForeignKey("worlds.id"), index=True)
    actor_world_character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("world_characters.id"), index=True
    )
    feed_observation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("world_character_feed_observations.id"), index=True
    )
    interaction_intent: Mapped[Optional[str]] = mapped_column(String(40))
    comment_purpose: Mapped[Optional[str]] = mapped_column(String(40))
    social_event_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("social_events.id"), index=True
    )
    brief_hash: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    failure_class: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["AgentRun"] = relationship()
    character: Mapped["Character"] = relationship()


class AgentSlot(Base):
    __tablename__ = "agent_slots"
    __table_args__ = (
        Index(
            "uq_agent_slots_assigned_character_not_null",
            "assigned_character_id",
            unique=True,
            postgresql_where=text("assigned_character_id IS NOT NULL"),
        ),
    )

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="idle")
    assigned_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    assigned_character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    assigned_credential_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("llm_credentials.id"), nullable=True
    )
    next_tick_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heartbeat_interval_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    locked_by_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AgentActivitySetting(Base):
    __tablename__ = "agent_activity_settings"
    __table_args__ = (
        CheckConstraint(
            "writing_repetition_level in ('off', 'light', 'normal', 'strong')",
            name="ck_agent_activity_settings_writing_repetition_level",
        ),
    )

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    auto_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    activity_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    comment_cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    max_comments_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_COMMENTS_PER_DAY
    )
    post_cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    max_posts_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_POSTS_PER_DAY
    )
    like_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    allow_post: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_like: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_repost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_follow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_unfollow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_observe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tendency_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tendency_action_ranges: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    planner_tendency_profile: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    tendency_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tendency_error: Mapped[str | None] = mapped_column(Text)
    active_hours_start: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default=active_hours.DEFAULT_ACTIVE_HOURS_START,
    )
    active_hours_end: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default=active_hours.DEFAULT_ACTIVE_HOURS_END,
    )
    autonomy_level: Mapped[str] = mapped_column(String(20), nullable=False, default="balanced")
    writing_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    writing_presence_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    writing_repetition_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="light"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped["Character"] = relationship(back_populates="activity_setting")

    @property
    def tendency_analysis_ready(self) -> bool:
        profile = (
            self.planner_tendency_profile
            if isinstance(self.planner_tendency_profile, dict)
            else {}
        )
        criteria = profile.get("feed_seed_interest_criteria")
        return bool(
            self.tendency_updated_at
            and self.tendency_summary.strip()
            and self.tendency_action_ranges
            and isinstance(criteria, str)
            and criteria.strip()
        )
