"""The original Character lock and WC filter use the caller's existing Session."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domains.characters.models import Character
from app.domains.routines.models import AgentSlot
from app.domains.world_characters.models import WorldCharacter


class SqlAlchemySlotReferences:
    def __init__(self, db: Session):
        self.db = db

    def lock_character_id(self, character_id: str) -> str | None:
        return self.db.scalar(
            select(Character.id)
            .where(Character.id == character_id)
            .with_for_update()
        )

    def owner_controlled_predicate(self) -> ColumnElement[bool]:
        return (
            select(WorldCharacter.id)
            .where(
                WorldCharacter.character_id == AgentSlot.assigned_character_id,
                WorldCharacter.control_mode == "owner_controlled",
                WorldCharacter.status == "active",
            )
            .exists()
        )

    def get_character(self, character_id: str) -> Character | None:
        return self.db.get(Character, character_id)
