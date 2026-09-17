"""One successful social action's self-expression; legacy declarations remain."""

from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class SocialActivityThought(Base):
    __tablename__ = "social_activity_thoughts"
    __table_args__ = (
        CheckConstraint("source_kind IN ('post_revision','action_event')", name="ck_social_thought_source_kind"),
        CheckConstraint("(source_kind = 'post_revision' AND source_post_id IS NOT NULL) OR (source_kind = 'action_event' AND source_post_id IS NULL)", name="ck_social_thought_source"),
        CheckConstraint("status IN ('recorded','missing','invalid')", name="ck_social_thought_status"),
        CheckConstraint("(status = 'recorded' AND thought_text IS NOT NULL AND length(trim(thought_text)) BETWEEN 1 AND 280) OR (status <> 'recorded' AND thought_text IS NULL AND truncated = false)", name="ck_social_thought_content"),
        CheckConstraint("length(source_digest) = 64", name="ck_social_thought_digest"),
        ForeignKeyConstraint(["actor_world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"], name="fk_social_thought_actor_world"),
        UniqueConstraint("source_post_id", "source_digest", name="uq_social_thought_post_revision"),
        UniqueConstraint("public_action_execution_id", name="uq_social_thought_execution"),
        Index("ix_social_thought_scope", "owner_id", "world_id", "actor_world_character_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    social_event_id: Mapped[str] = mapped_column(ForeignKey("social_events.id", ondelete="CASCADE"), nullable=False, unique=True)
    public_action_execution_id: Mapped[int | None] = mapped_column(ForeignKey("agent_public_action_executions.id", ondelete="CASCADE"))
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    thought_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
