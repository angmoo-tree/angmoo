"""Existing mixed Character/World membership reads in the exact caller Session."""

from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfileQuery,
)
from app.domains.social.contracts.profile_references import (
    ProfileIdentity,
    ProfileCharacter,
    ProfileWorldCharacter,
)
from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership
from app.runtime.world_characters.composition import public_profile_service


class RuntimeProfileReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def profile(self, query: WorldCharacterSocialProfileQuery) -> ProfileIdentity:
        return public_profile_service(self.db).get_for_world(
            world_id=query.world_id,
            world_character_id=query.world_character_id,
            current_user_id=query.current_user_id,
        )

    def _viewer_world_character_ids(
        self, query: WorldCharacterSocialProfileQuery
    ) -> tuple[str, ...]:
        rows = self.db.scalars(
            select(WorldCharacter.id)
            .join(
                WorldMembership,
                (WorldMembership.id == WorldCharacter.membership_id)
                & (WorldMembership.world_id == WorldCharacter.world_id),
            )
            .where(
                WorldCharacter.world_id == query.world_id,
                WorldCharacter.owner_user_id == query.current_user_id,
                WorldCharacter.control_mode == "owner_controlled",
                WorldCharacter.status == "active",
                WorldMembership.user_id == query.current_user_id,
                WorldMembership.status == "active",
            )
            .order_by(WorldCharacter.id.asc())
        )
        return tuple((str(value) for value in rows))

    def authors(
        self, author_ids: set[str]
    ) -> dict[str, tuple[ProfileWorldCharacter, ProfileCharacter]]:
        authors = {
            str(world_character.id): (world_character, character)
            for world_character, character in self.db.execute(
                select(WorldCharacter, Character)
                .join(Character, Character.id == WorldCharacter.character_id)
                .where(WorldCharacter.id.in_(author_ids))
            ).all()
        }
        return authors

    def active_author_ids(self, *, world_id: str, author_ids: set[str]) -> set[str]:
        active_author_ids = {
            str(value)
            for value in self.db.scalars(
                select(WorldCharacter.id)
                .join(Character, Character.id == WorldCharacter.character_id)
                .join(
                    WorldMembership,
                    (WorldMembership.id == WorldCharacter.membership_id)
                    & (WorldMembership.world_id == WorldCharacter.world_id),
                )
                .where(
                    WorldCharacter.id.in_(author_ids),
                    WorldCharacter.world_id == world_id,
                    WorldCharacter.status == "active",
                    WorldMembership.status == "active",
                    Character.deleted_at.is_(None),
                    Character.moderation_status == "active",
                )
            )
        }
        return active_author_ids

    def characters_by_handles(
        self, all_handles: set[str]
    ) -> dict[str, ProfileCharacter]:
        characters = {
            str(character.handle): character
            for character in self.db.scalars(
                select(Character).where(
                    Character.handle.in_(all_handles),
                    Character.deleted_at.is_(None),
                    Character.moderation_status == "active",
                )
            )
            if character.handle is not None
        }
        return characters
