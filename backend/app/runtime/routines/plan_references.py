"""Original planning reference queries on the caller's existing Session."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.characters.models import Character
from app.domains.identity.models import LlmCredential
from app.domains.worlds.models import World, WorldMembership
from app.domains.world_characters.models import (
    WorldActivityCandidate, WorldActivityRepertoire, WorldCharacter,
    WorldCommunityProfile,
)
from app.domains.world_characters.service.runtime_modes import set_activity_runtime_mode
from app.domains.world_characters.service.setup_validation import character_contract_hash


class SqlAlchemyPlanReferences:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_character(self, character_id: str) -> Character | None:
        return self._db.get(Character, character_id)

    def character_contract_hash(self, character: Character) -> str:
        return character_contract_hash(character)

    def find_world_character(
        self, *, character_id: str, world_id: str, lock_for_update: bool = False
    ) -> WorldCharacter | None:
        statement = select(WorldCharacter).where(
            WorldCharacter.world_id == world_id,
            WorldCharacter.character_id == character_id,
        )
        if lock_for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_membership(self, membership_id: str) -> WorldMembership | None:
        return self._db.get(WorldMembership, membership_id)

    def get_world(self, world_id: str) -> World | None:
        return self._db.get(World, world_id)

    def get_ready_repertoire(
        self, world_character_id: str
    ) -> WorldActivityRepertoire | None:
        return self._db.scalar(
            select(WorldActivityRepertoire).where(
                WorldActivityRepertoire.world_character_id == world_character_id,
                WorldActivityRepertoire.status == "ready",
            )
        )

    def get_profile(self, profile_id: str) -> WorldCommunityProfile | None:
        return self._db.get(WorldCommunityProfile, profile_id)

    def list_enabled_candidates(self, repertoire_id: str) -> list[WorldActivityCandidate]:
        return list(self._db.scalars(
            select(WorldActivityCandidate).where(
                WorldActivityCandidate.repertoire_id == repertoire_id,
                WorldActivityCandidate.enabled.is_(True),
            )
        ))

    def get_credential(self, credential_id: str) -> LlmCredential | None:
        return self._db.get(LlmCredential, credential_id)

    def set_activity_runtime_mode(
        self, world_character: WorldCharacter, *, activity_runtime_mode: str
    ) -> None:
        set_activity_runtime_mode(
            world_character, activity_runtime_mode=activity_runtime_mode
        )
