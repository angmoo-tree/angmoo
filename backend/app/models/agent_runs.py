from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base








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
