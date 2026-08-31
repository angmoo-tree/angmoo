"""SQLAlchemy persistence models for the legacy-compatible Chat v1 boundary.

P8-L-B moves ownership without changing tables, columns, constraints, indexes,
or runtime behavior. World-scoped Chat v2 schema work remains in P8-L-D.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
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
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
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
