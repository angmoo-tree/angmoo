"""Read-only profile presentation facts, supplied without copying attached rows."""

from __future__ import annotations
from typing import Protocol
from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfileQuery,
)


class ProfileIdentity(Protocol):
    @property
    def character_id(self) -> str: ...


class ProfileCharacter(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def handle(self) -> str | None: ...
    @property
    def avatar_url(self) -> str | None: ...


class ProfileWorldCharacter(Protocol):
    @property
    def local_profile(self) -> object: ...


class ProfileActivityReferences(Protocol):
    def profile(self, query: WorldCharacterSocialProfileQuery) -> ProfileIdentity: ...
    def _viewer_world_character_ids(
        self, query: WorldCharacterSocialProfileQuery
    ) -> tuple[str, ...]: ...
    def authors(
        self, author_ids: set[str]
    ) -> dict[str, tuple[ProfileWorldCharacter, ProfileCharacter]]: ...
    def active_author_ids(self, *, world_id: str, author_ids: set[str]) -> set[str]: ...
    def characters_by_handles(
        self, all_handles: set[str]
    ) -> dict[str, ProfileCharacter]: ...
