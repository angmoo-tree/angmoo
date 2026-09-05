"""Bind original Social and scoped-routine reads to one caller Session."""
from sqlalchemy.orm import Session
from app.domains.social.repository import resident_context
from app.runtime.routine_posts import routine_world_character_for_character


class SqlAlchemyPostSelectionReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest_visible_nonself_root_id(self, character_id: str) -> str | None:
        return resident_context.get_latest_visible_nonself_root_id(self.db, character_id)

    def get_latest_visible_root_id(self) -> str | None:
        return resident_context.get_latest_visible_root_id(self.db)

    def routine_world_character_for_character(self, *, character_id: str) -> object | None:
        return routine_world_character_for_character(self.db, character_id=character_id)
