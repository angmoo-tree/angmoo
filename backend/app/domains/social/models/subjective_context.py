"""Normalized persistence for declared subjective context of successful SNS actions."""

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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domains.social.contracts.subjective_context import (
    ACTION_SUBJECTIVE_CONTEXT_VERSION,
    ActionEmotionLabel,
    ActionMotivationKind,
    SubjectiveContextProvenance,
)


SUBJECTIVE_CONTEXT_SCHEMA_TABLES = ("social_action_subjective_contexts",)


def _sql_values(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


class SocialActionSubjectiveContext(Base):
    __tablename__ = "social_action_subjective_contexts"
    __table_args__ = (
        CheckConstraint(
            f"schema_version = '{ACTION_SUBJECTIVE_CONTEXT_VERSION}'",
            name="ck_social_action_subjective_contexts_version",
        ),
        CheckConstraint(
            f"motivation_kind IN ({_sql_values(ActionMotivationKind.values())})",
            name="ck_social_action_subjective_contexts_motivation_kind",
        ),
        CheckConstraint(
            f"emotion_label IN ({_sql_values(ActionEmotionLabel.values())})",
            name="ck_social_action_subjective_contexts_emotion_label",
        ),
        CheckConstraint(
            "length(trim(motivation_text)) BETWEEN 1 AND 280",
            name="ck_social_action_subjective_contexts_motivation_text",
        ),
        CheckConstraint(
            "emotion_text IS NULL OR length(trim(emotion_text)) BETWEEN 1 AND 280",
            name="ck_social_action_subjective_contexts_emotion_text",
        ),
        CheckConstraint(
            "emotion_intensity IS NULL OR emotion_intensity BETWEEN 0 AND 100",
            name="ck_social_action_subjective_contexts_emotion_intensity",
        ),
        CheckConstraint(
            "emotion_label != 'unspecified' OR "
            "(emotion_text IS NULL AND emotion_intensity IS NULL)",
            name="ck_social_action_subjective_contexts_unspecified_emotion",
        ),
        CheckConstraint(
            "provenance_kind = 'declared_at_action_decision'",
            name="ck_social_action_subjective_contexts_provenance",
        ),
        CheckConstraint(
            "length(source_digest) = 64",
            name="ck_social_action_subjective_contexts_digest",
        ),
        CheckConstraint(
            "invalidation_reason IS NULL OR invalidation_reason IN "
            "('source_deleted','source_hidden','membership_inactive','blocked',"
            "'world_mismatch','manual_exclusion')",
            name="ck_social_action_subjective_contexts_invalidation",
        ),
        ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_social_action_subjective_contexts_actor_scope",
        ),
        UniqueConstraint(
            "social_event_id",
            name="uq_social_action_subjective_contexts_event",
        ),
        UniqueConstraint(
            "public_action_execution_id",
            name="uq_social_action_subjective_contexts_execution",
        ),
        Index(
            "ix_social_action_subjective_contexts_scope_captured",
            "owner_id",
            "world_id",
            "actor_world_character_id",
            "captured_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    social_event_id: Mapped[str] = mapped_column(
        ForeignKey("social_events.id"), nullable=False
    )
    public_action_execution_id: Mapped[int] = mapped_column(
        ForeignKey("agent_public_action_executions.id"), nullable=False
    )
    source_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    schema_version: Mapped[str] = mapped_column(
        String(48), nullable=False, default=ACTION_SUBJECTIVE_CONTEXT_VERSION
    )
    motivation_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    motivation_text: Mapped[str] = mapped_column(Text, nullable=False)
    emotion_label: Mapped[str] = mapped_column(String(32), nullable=False)
    emotion_text: Mapped[str | None] = mapped_column(Text)
    emotion_intensity: Mapped[int | None] = mapped_column(Integer)
    provenance_kind: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        default=SubjectiveContextProvenance.DECLARED_AT_ACTION_DECISION.value,
    )
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def create_subjective_context_schema(connection: Connection) -> None:
    Base.metadata.create_all(
        connection,
        tables=[Base.metadata.tables[name] for name in SUBJECTIVE_CONTEXT_SCHEMA_TABLES],
        checkfirst=False,
    )


def drop_subjective_context_schema(connection: Connection) -> None:
    Base.metadata.drop_all(
        connection,
        tables=[Base.metadata.tables[name] for name in SUBJECTIVE_CONTEXT_SCHEMA_TABLES],
        checkfirst=False,
    )


__all__ = [
    "SUBJECTIVE_CONTEXT_SCHEMA_TABLES",
    "SocialActionSubjectiveContext",
    "create_subjective_context_schema",
    "drop_subjective_context_schema",
]
