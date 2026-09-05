"""Read-only structural records and the actual cross-owner Chat query seam.

Queries return records attached to the supplied Session. No copied ORM objects
or independent transaction is introduced by this contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session


class ChatUser(Protocol):
    id: str
    display_name: str


class ChatCharacter(Protocol):
    id: str
    owner_id: str
    name: str
    handle: str
    avatar_url: str | None
    banner_url: str | None
    deleted_at: datetime | None
    moderation_status: str
    execution_mode: str
    one_liner: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: str
    safety_rules: str
    persona_summary: str


class ChatWorldCharacter(Protocol):
    id: str
    character_id: str
    role_key: str | None
    control_mode: str


class ChatInstallation(Protocol):
    bootstrap_state: str
    owner_user_id: str | None


class ChatCredential(Protocol):
    id: str
    provider: str
    key_fingerprint: str | None
    enabled: bool
    encrypted_api_key: str | None


class ChatScopeQueries(Protocol):
    def owner_controlled_world_characters(
        self, db: Session, owner_id: str, world_id: str, *, lock_scope: bool = False
    ) -> list[ChatWorldCharacter]: ...
    def local_installation(
        self, db: Session, *, lock_scope: bool = False
    ) -> ChatInstallation | None: ...
    def owned_world_id(
        self, db: Session, owner_id: str, world_id: str, *, lock_scope: bool = False
    ) -> str | None: ...
    def responding_world_character(
        self, db: Session, world_id: str, world_character_id: str
    ) -> tuple[ChatWorldCharacter, ChatCharacter] | None: ...
    def world_chat_role(
        self,
        db: Session,
        world_character_id: str,
        *,
        world_id: str,
        expected_owner_id: str | None = None,
        lock_scope: bool = False,
    ) -> tuple[ChatWorldCharacter, ChatCharacter] | None: ...
    def claimed_local_installation_exists(self, db: Session) -> bool: ...


class WorldCharacterBlockQuery(Protocol):
    def __call__(
        self,
        db: Session,
        *,
        world_id: str,
        first_world_character_id: str,
        second_world_character_id: str,
    ) -> bool: ...
