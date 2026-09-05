"""Connect canonical source owners to the projection service's existing Session."""
from sqlalchemy.orm import Session
from app.domains.relationships.contracts.projection_commands import (
    ProjectionCommandError, ProjectionPost, ProjectionWorldCharacter,
)
from app.domains.social.repository.event_evidence import get_post
from app.domains.world_characters.exceptions import WorldCharacterContractError
from app.domains.world_characters.service.projection_scope import get_projection_world_character


class SqlAlchemyProjectionCommandReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def world_character(self, *, world_id: str, world_character_id: str) -> ProjectionWorldCharacter:
        try:
            return get_projection_world_character(
                self.db, world_id=world_id, world_character_id=world_character_id
            )
        except WorldCharacterContractError as exc:
            raise ProjectionCommandError(exc.reason_code) from exc

    def get_post(self, post_id: str) -> ProjectionPost | None:
        return get_post(self.db, post_id)
