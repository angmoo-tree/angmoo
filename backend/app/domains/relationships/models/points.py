"""Persistent relationship response candidates; runtime run ownership is separate."""
from datetime import datetime
from typing import Any, Optional
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models import Base


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
