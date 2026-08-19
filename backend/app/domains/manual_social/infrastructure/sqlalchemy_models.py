from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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


class OwnerManualSocialWrite(Base):
    __tablename__ = "owner_manual_social_writes"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('post','reply')",
            name="ck_owner_manual_social_writes_operation",
        ),
        CheckConstraint(
            "(operation = 'post' AND target_post_id IS NULL) OR "
            "(operation = 'reply' AND target_post_id IS NOT NULL)",
            name="ck_owner_manual_social_writes_target",
        ),
        ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_owner_manual_social_writes_actor_scope",
        ),
        UniqueConstraint(
            "world_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_owner_manual_social_writes_request",
        ),
        UniqueConstraint("result_post_id", name="uq_owner_manual_social_writes_result"),
        Index(
            "ix_owner_manual_social_writes_world_created",
            "world_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    target_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    result_post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OwnerManualInboxCandidate(Base):
    __tablename__ = "owner_manual_inbox_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','claimed','consumed','released','rejected')",
            name="ck_owner_manual_inbox_candidates_status",
        ),
        CheckConstraint(
            "actor_world_character_id != target_world_character_id",
            name="ck_owner_manual_inbox_candidates_not_self",
        ),
        CheckConstraint(
            "version >= 1", name="ck_owner_manual_inbox_candidates_version"
        ),
        ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_owner_manual_inbox_candidates_actor_scope",
        ),
        ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_owner_manual_inbox_candidates_target_scope",
        ),
        UniqueConstraint(
            "source_reply_post_id",
            "target_world_character_id",
            name="uq_owner_manual_inbox_candidates_source_target",
        ),
        Index(
            "ix_owner_manual_inbox_candidates_target_status",
            "target_world_character_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_owner_manual_inbox_candidates_claim_expiry",
            "status",
            "claim_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reply_post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id"), nullable=False
    )
    target_post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    target_activity_beat_id: Mapped[str | None] = mapped_column(
        ForeignKey("activity_beats.id")
    )
    claim_run_id: Mapped[str | None] = mapped_column(String(64))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


__all__ = ["OwnerManualInboxCandidate", "OwnerManualSocialWrite"]
