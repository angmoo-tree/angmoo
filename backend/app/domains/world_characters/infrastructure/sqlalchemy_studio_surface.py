from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.public import Character
from app.domains.world_characters.domain.studio_surface import StudioWorldCharacter
from app.domains.world_characters.infrastructure.sqlalchemy_models import (
    CharacterActiveWorld,
    WorldCharacter,
)
from app.domains.world_characters.infrastructure.sqlalchemy_setup_models import (
    WorldActivityRepertoire,
    WorldCommunityProfile,
)
from app.domains.worlds.public import require_creator_access


class _CurrentUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


class SqlAlchemyStudioWorldCharacterReader:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_creator(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> tuple[StudioWorldCharacter, ...]:
        require_creator_access(
            self.db,
            world_id=world_id,
            user=_CurrentUser(current_user_id),
        )
        rows = self.db.execute(
            select(WorldCharacter, Character)
            .join(Character, Character.id == WorldCharacter.character_id)
            .where(
                WorldCharacter.world_id == world_id,
                WorldCharacter.status.in_(("pending", "inactive", "active")),
            )
            .order_by(Character.name.asc(), WorldCharacter.id.asc())
        ).all()
        ids = [world_character.id for world_character, _character in rows]
        setup_status = self._setup_status(ids)
        selected_ids = self._selected_world_character_ids(ids)
        return tuple(
            self._snapshot(
                world_character,
                character,
                setup_status.get(world_character.id, (None, None)),
                selected_active_world=world_character.id in selected_ids,
            )
            for world_character, character in rows
        )

    def _selected_world_character_ids(
        self,
        world_character_ids: list[str],
    ) -> set[str]:
        if not world_character_ids:
            return set()
        return set(
            self.db.scalars(
                select(CharacterActiveWorld.world_character_id).where(
                    CharacterActiveWorld.world_character_id.in_(world_character_ids)
                )
            ).all()
        )

    def _setup_status(
        self,
        world_character_ids: list[str],
    ) -> dict[str, tuple[str | None, str | None]]:
        if not world_character_ids:
            return {}
        profile_status: dict[str, str] = {}
        for world_character_id, status in self.db.execute(
            select(
                WorldCommunityProfile.world_character_id,
                WorldCommunityProfile.status,
            )
            .where(
                WorldCommunityProfile.world_character_id.in_(world_character_ids)
            )
            .order_by(WorldCommunityProfile.created_at.desc())
        ):
            profile_status.setdefault(world_character_id, status)
        repertoire_status: dict[str, str] = {}
        for world_character_id, status in self.db.execute(
            select(
                WorldActivityRepertoire.world_character_id,
                WorldActivityRepertoire.status,
            )
            .where(
                WorldActivityRepertoire.world_character_id.in_(world_character_ids)
            )
            .order_by(WorldActivityRepertoire.created_at.desc())
        ):
            repertoire_status.setdefault(world_character_id, status)
        return {
            world_character_id: (
                profile_status.get(world_character_id),
                repertoire_status.get(world_character_id),
            )
            for world_character_id in world_character_ids
        }

    @staticmethod
    def _snapshot(
        world_character: WorldCharacter,
        character: Character,
        statuses: tuple[str | None, str | None],
        *,
        selected_active_world: bool,
    ) -> StudioWorldCharacter:
        if world_character.control_mode == "owner_controlled":
            setup_state = "unavailable_for_owner_controlled"
        elif statuses == ("ready", "ready"):
            setup_state = "approved"
        elif any(status is not None for status in statuses):
            setup_state = "generated"
        else:
            setup_state = "not_started"
        local_profile = world_character.local_profile or {}
        return StudioWorldCharacter(
            world_character_id=world_character.id,
            character_id=character.id,
            display_name=str(local_profile.get("display_name") or character.name),
            confirmation_name=character.name,
            avatar_url=str(local_profile.get("avatar_url") or character.avatar_url)
            if (local_profile.get("avatar_url") or character.avatar_url)
            else None,
            intro=str(local_profile.get("intro") or character.one_liner or ""),
            role_key=world_character.role_key,
            control_mode=world_character.control_mode,
            status=world_character.status,
            autonomous_enabled=world_character.autonomous_enabled,
            selected_active_world=selected_active_world,
            version=world_character.version,
            activity_setup_state=setup_state,
        )


__all__ = ["SqlAlchemyStudioWorldCharacterReader"]
