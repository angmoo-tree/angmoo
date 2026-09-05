"""Compatibility exports for the canonical Chat HTTP schemas."""

from app.domains.chat.schemas import (
    CharacterMessageSettingRead,
    CharacterMessageSettingUpdate,
    MessageCredentialSource,
    MessageGoogleModel,
    MessageMessageCreate,
    MessageMessageRead,
    MessageSendRead,
    MessageSettingsRead,
    MessageSettingsUpdate,
    MessageThreadCreate,
    MessageThreadListRead,
    MessageThreadRead,
    MessageThreadUpdate,
    ProfileRef,
)

__all__ = [
    "CharacterMessageSettingRead",
    "CharacterMessageSettingUpdate",
    "MessageCredentialSource",
    "MessageGoogleModel",
    "MessageMessageCreate",
    "MessageMessageRead",
    "MessageSendRead",
    "MessageSettingsRead",
    "MessageSettingsUpdate",
    "MessageThreadCreate",
    "MessageThreadListRead",
    "MessageThreadRead",
    "MessageThreadUpdate",
    "ProfileRef",
]
