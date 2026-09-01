"""Port for exact-World WorldCharacter social profile reads."""

from __future__ import annotations

from typing import Protocol

from app.domains.social.domain.profile_activity import (
    WorldCharacterSocialProfilePage,
    WorldCharacterSocialProfileQuery,
)


class WorldCharacterSocialProfileReader(Protocol):
    def read(
        self,
        query: WorldCharacterSocialProfileQuery,
    ) -> WorldCharacterSocialProfilePage: ...


__all__ = ["WorldCharacterSocialProfileReader"]
