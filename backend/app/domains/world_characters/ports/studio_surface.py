from __future__ import annotations

from typing import Protocol

from app.domains.world_characters.domain.studio_surface import StudioWorldCharacter


class StudioWorldCharacterReader(Protocol):
    def list_for_creator(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> tuple[StudioWorldCharacter, ...]: ...


__all__ = ["StudioWorldCharacterReader"]
