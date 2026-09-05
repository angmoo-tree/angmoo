from __future__ import annotations

from app.domains.world_characters.contracts.studio_surface import StudioWorldCharacter
from app.domains.world_characters.ports.studio_surface import StudioWorldCharacterReader


def list_studio_world_characters(
    reader: StudioWorldCharacterReader,
    *,
    world_id: str,
    current_user_id: str,
) -> tuple[StudioWorldCharacter, ...]:
    return reader.list_for_creator(
        world_id=world_id,
        current_user_id=current_user_id,
    )


__all__ = ["list_studio_world_characters"]
