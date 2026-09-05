"""Injected joined reads return attached rows in the caller Session.

The adapter preserves SQL join multiplicity and order. WC services own access
checks and interpretation. Character is described structurally, not re-exported
as an ORM class that another domain can query or construct.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.domains.world_characters.models import WorldCharacter


class CharacterProfileRecord(Protocol):
    id: str
    name: str
    handle: str
    avatar_url: str | None
    banner_url: str | None
    one_liner: str
    moderation_status: str
    execution_mode: str


class WorldCharacterQueries(Protocol):
    def public_profile_rows(self, db: Session, world_id: str) -> Sequence[tuple[WorldCharacter, CharacterProfileRecord]]: ...
    def public_profile_row(self, db: Session, world_id: str, world_character_id: str) -> tuple[WorldCharacter, CharacterProfileRecord] | None: ...
    def studio_rows(self, db: Session, world_id: str) -> Sequence[tuple[WorldCharacter, CharacterProfileRecord]]: ...
    def candidate_rows(self, db: Session, world_id: str, current_user_id: str) -> Sequence[tuple[CharacterProfileRecord, WorldCharacter | None]]: ...
