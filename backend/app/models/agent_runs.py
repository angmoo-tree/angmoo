from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


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


class AgentDaypartMemoryEvent(Base):
    __tablename__ = "agent_daypart_memory_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    memory_session_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    daypart_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    activity_daypart: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"), index=True)
    notification_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notifications.id"), index=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    topic_signature: Mapped[Optional[str]] = mapped_column(String(300))
    run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    provided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    character: Mapped["Character"] = relationship()


from app.domains.relationships.models.points import AgentRelationshipPoint


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
