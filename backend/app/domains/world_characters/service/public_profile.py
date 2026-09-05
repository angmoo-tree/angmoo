"""SQLAlchemy reader for Local WorldCharacter public profile surfaces."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.world_characters.contracts.queries import CharacterProfileRecord, WorldCharacterQueries
from app.domains.world_characters.contracts.public_profile import (
    WorldCharacterProfileNotFoundError,
    WorldCharacterPublicProfile,
)
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds import service as world_service


class _CurrentUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


class WorldCharacterProfileService:
    def __init__(self, db: Session, *, queries: WorldCharacterQueries) -> None:
        self.db = db
        self.queries = queries

    def list_for_world(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> tuple[WorldCharacterPublicProfile, ...]:
        self._require_world_access(world_id, current_user_id)
        rows = self.queries.public_profile_rows(self.db, world_id)
        return tuple(self._snapshot(world_character, character) for world_character, character in rows)

    def get_for_world(
        self,
        *,
        world_id: str,
        world_character_id: str,
        current_user_id: str,
    ) -> WorldCharacterPublicProfile:
        self._require_world_access(world_id, current_user_id)
        row = self.queries.public_profile_row(self.db, world_id, world_character_id)
        if row is None:
            raise WorldCharacterProfileNotFoundError()
        return self._snapshot(row[0], row[1])

    def _require_world_access(self, world_id: str, current_user_id: str) -> None:
        world_service.require_world_read_access(
            self.db,
            world_id=world_id,
            user=_CurrentUser(current_user_id),
        )

    @staticmethod
    def _snapshot(
        world_character: WorldCharacter,
        character: CharacterProfileRecord,
    ) -> WorldCharacterPublicProfile:
        local_profile = world_character.local_profile or {}
        display_name = str(local_profile.get("display_name") or character.name)
        avatar_value = local_profile.get("avatar_url") or character.avatar_url
        banner_value = local_profile.get("banner_url") or character.banner_url
        intro = str(local_profile.get("intro") or character.one_liner or "")
        return WorldCharacterPublicProfile(
            world_id=world_character.world_id,
            world_character_id=world_character.id,
            character_id=character.id,
            display_name=display_name,
            handle=character.handle,
            avatar_url=str(avatar_value) if avatar_value else None,
            banner_url=str(banner_value) if banner_value else None,
            intro=intro,
            role_key=world_character.role_key,
            control_mode=world_character.control_mode,
        )


__all__ = ["WorldCharacterProfileService"]
