"""SQLAlchemy persistence for canonical Character identity records."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
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


class AgentCreationDraft(Base):
    __tablename__ = "agent_creation_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="google")
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    handle: Mapped[Optional[str]] = mapped_column(String(40))
    one_liner: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")
    speech_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worldview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_preferences: Mapped[str] = mapped_column(Text, nullable=False, default="")
    safety_rules: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_style: Mapped[str] = mapped_column(String(40), nullable=False, default="기본")
    appearance_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_temp_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_temp_url: Mapped[Optional[str]] = mapped_column(String(500))
    persona_enhance_available_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    media_generation_available_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()


class ProfileImageQuotaReservation(Base):
    __tablename__ = "profile_image_quota_reservations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    quota_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    candidate_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    route_mode: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

class ProfileImageCandidate(Base):
    __tablename__ = "profile_image_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    draft_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_creation_drafts.id"), index=True
    )
    character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"), index=True)
    quota_reservation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("profile_image_quota_reservations.id"), index=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    bucket: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False, default="image/webp")
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    route_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    quota_reservation: Mapped[Optional[ProfileImageQuotaReservation]] = relationship()
