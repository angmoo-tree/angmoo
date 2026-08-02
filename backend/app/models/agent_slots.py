from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


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

