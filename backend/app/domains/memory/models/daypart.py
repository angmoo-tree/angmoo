"""Daypart observation/action history on the shared ORM metadata."""

from datetime import date, datetime
from typing import Any, Optional

from app.models import Base
from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class AgentDaypartMemoryEvent(Base):
    __tablename__ = "agent_daypart_memory_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    memory_session_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    daypart_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    activity_daypart: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_post_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("posts.id"), index=True
    )
    notification_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notifications.id"), index=True
    )
    thread_id: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    topic_signature: Mapped[Optional[str]] = mapped_column(String(300))
    run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_runs.id"), index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    provided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    character: Mapped["Character"] = relationship()  # noqa: F821 - shared registry string target
