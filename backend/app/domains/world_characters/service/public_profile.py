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
        values = self.queries.effective_profiles(self.db, world_id=world_id,
            world_character_ids=[role.id for role, _ in rows])
        names = self.queries.role_names(self.db, world_id)
        return tuple(self._snapshot(world_character, character, profile=values[world_character.id], role_names=names) for world_character, character in rows)

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
        values = self.queries.effective_profiles(self.db, world_id=world_id, world_character_ids=[world_character_id])
        return self._snapshot(row[0], row[1], profile=values[world_character_id], role_names=self.queries.role_names(self.db, world_id))

    def _require_world_access(self, world_id: str, current_user_id: str) -> None:
        world_service.require_world_read_access(
            self.db,
            world_id=world_id,
            user=_CurrentUser(current_user_id),
        )

    def _snapshot(
        self,
        world_character: WorldCharacter,
        character: CharacterProfileRecord,
        *, profile, role_names,
    ) -> WorldCharacterPublicProfile:
        display_name, avatar_value, banner_value, intro = profile.display_name, profile.avatar_url, profile.banner_url, profile.intro
        return WorldCharacterPublicProfile(
            world_id=world_character.world_id,
            world_character_id=world_character.id,
            character_id=character.id,
            display_name=display_name,
            handle=profile.handle,
            avatar_url=str(avatar_value) if avatar_value else None,
            banner_url=str(banner_value) if banner_value else None,
            intro=intro,
            role_key=world_character.role_key,
            control_mode=world_character.control_mode,
            role_name=role_names.get(world_character.role_key),
        )


__all__ = ["WorldCharacterProfileService"]
