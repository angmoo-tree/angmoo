"""Persistence port for World-scoped public profile reads."""

from __future__ import annotations

from typing import Protocol

from app.domains.world_characters.domain.public_profile import (
    WorldCharacterPublicProfile,
)


class WorldCharacterPublicProfileReader(Protocol):
    def list_for_world(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> tuple[WorldCharacterPublicProfile, ...]: ...

    def get_for_world(
        self,
        *,
        world_id: str,
        world_character_id: str,
        current_user_id: str,
    ) -> WorldCharacterPublicProfile: ...


__all__ = ["WorldCharacterPublicProfileReader"]
