"""Compatibility exports for the canonical Chat SQLAlchemy models."""

from app.domains.chat.models import (
    CharacterMessageSetting,
    MessageMessage,
    MessageThread,
    UserMessagePreference,
)

__all__ = [
    "CharacterMessageSetting",
    "MessageMessage",
    "MessageThread",
    "UserMessagePreference",
]
