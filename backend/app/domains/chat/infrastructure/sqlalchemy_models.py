"""SQLAlchemy persistence models for Chat v1 compatibility and World Chat v2."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CharacterMessageSetting(Base):
    __tablename__ = "character_message_settings"

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped["Character"] = relationship()


class UserMessagePreference(Base):
    __tablename__ = "user_message_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    credential_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="message_key"
    )
    source_character_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    default_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gemini-2.5-flash-lite"
    )
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
    source_character: Mapped[Optional["Character"]] = relationship()


class MessageThread(Base):
    __tablename__ = "message_threads"
    __table_args__ = (
        CheckConstraint(
            "(response_lease_token IS NULL) = "
            "(response_lease_expires_at IS NULL)",
            name="ck_message_threads_response_lease_pair",
        ),
        CheckConstraint(
            "(world_scope_status = 'resolved' AND world_id IS NOT NULL "
            "AND requester_world_character_id IS NOT NULL "
            "AND responding_world_character_id IS NOT NULL "
            "AND requester_world_character_id <> responding_world_character_id) OR "
            "(world_scope_status IN ('ambiguous', 'quarantined') "
            "AND world_id IS NULL "
            "AND requester_world_character_id IS NULL "
            "AND responding_world_character_id IS NULL)",
            name="ck_message_threads_world_scope_binding",
        ),
        ForeignKeyConstraint(
            ["requester_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_message_threads_requester_world",
        ),
        ForeignKeyConstraint(
            ["responding_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_message_threads_responding_world",
        ),
        ForeignKeyConstraint(
            ["responding_world_character_id", "character_id"],
            ["world_characters.id", "world_characters.character_id"],
            name="fk_message_threads_responding_character",
        ),
        Index(
            "uq_message_threads_active_world_roles",
            "requester_id",
            "world_id",
            "requester_world_character_id",
            "responding_world_character_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND world_scope_status = 'resolved'"
            ),
            sqlite_where=text(
                "deleted_at IS NULL AND world_scope_status = 'resolved'"
            ),
        ),
        Index(
            "uq_message_threads_active_legacy_ambiguous",
            "requester_id",
            "character_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
            ),
            sqlite_where=text(
                "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
            ),
        ),
        Index(
            "ix_message_threads_owner_world_status",
            "requester_id",
            "world_id",
            "world_scope_status",
        ),
        Index(
            "ix_message_threads_requester_last",
            "requester_id",
            "last_message_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    world_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("worlds.id", name="fk_message_threads_world"), nullable=True
    )
    requester_world_character_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    responding_world_character_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    world_scope_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ambiguous", server_default="ambiguous"
    )
    selected_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gemini-2.5-flash-lite"
    )
    response_lease_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    response_lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    requester: Mapped["User"] = relationship()
    character: Mapped["Character"] = relationship()
    messages: Mapped[list["MessageMessage"]] = relationship(
        back_populates="thread", order_by="MessageMessage.created_at"
    )


class MessageMessage(Base):
    __tablename__ = "message_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("message_threads.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    error_code: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    thread: Mapped[MessageThread] = relationship(back_populates="messages")
