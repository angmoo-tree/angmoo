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


class AgentRelationshipPoint(Base):
    __tablename__ = "agent_relationship_points"
    __table_args__ = (
        UniqueConstraint(
            "source_signature",
            name="uq_agent_relationship_points_source_signature",
        ),
        Index(
            "ix_agent_relationship_points_recipient_status_created",
            "recipient_character_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_agent_relationship_points_pair_created",
            "pair_key",
            "created_at",
        ),
        Index(
            "ix_agent_relationship_points_chain_depth",
            "chain_id",
            "chain_depth",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipient_character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    source_character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    source_post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id"), nullable=False, index=True
    )
    source_run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id"))
    reply_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    reply_run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id"))
    selected_run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id"))
    consumed_run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id"))
    consumed_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    topic_brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_signature: Mapped[str] = mapped_column(String(220), nullable=False)
    chain_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    chain_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pair_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    failure_class: Mapped[Optional[str]] = mapped_column(String(80))
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    selected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    recipient_character: Mapped["Character"] = relationship(
        foreign_keys=[recipient_character_id]
    )
    source_character: Mapped["Character"] = relationship(
        foreign_keys=[source_character_id]
    )


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
