"""SQLAlchemy persistence for canonical Character identity records."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(
            "execution_mode in ('llm', 'local')",
            name="ck_characters_execution_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    handle: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    one_liner: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")
    speech_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worldview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_preferences: Mapped[str] = mapped_column(Text, nullable=False, default="")
    safety_rules: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="inactive")
    moderation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    moderation_reason: Mapped[Optional[str]] = mapped_column(String(80))
    moderation_note: Mapped[Optional[str]] = mapped_column(Text)
    moderation_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    moderation_updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id")
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="llm", server_default="llm"
    )
    promotion_usage_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    promotion_usage_agreed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    promotion_usage_revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    promotion_usage_policy_version: Mapped[Optional[str]] = mapped_column(String(20))
    persona_summary: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(
        back_populates="characters", foreign_keys=[owner_id]
    )
    comments: Mapped[list["Comment"]] = relationship(back_populates="author_character")
    state: Mapped[Optional["CharacterState"]] = relationship(
        back_populates="character", uselist=False
    )
    credential: Mapped[Optional["LlmCredential"]] = relationship(
        back_populates="character", uselist=False
    )
    activity_setting: Mapped[Optional["AgentActivitySetting"]] = relationship(
        back_populates="character", uselist=False
    )
    image_generation_setting: Mapped[
        Optional["AgentImageGenerationSetting"]
    ] = relationship(back_populates="character", uselist=False)


class CharacterState(Base):
    __tablename__ = "character_states"

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    mood: Mapped[str] = mapped_column(String(80), nullable=False, default="neutral")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    memory_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped[Character] = relationship(back_populates="state")


__all__ = ["Character", "CharacterState"]
