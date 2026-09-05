"""Bind active WorldCharacter and Social source reads to one caller Session."""
from sqlalchemy.orm import Session
from app.domains.relationships.contracts.observations import ObservationPost, ObservationWorldCharacter
from app.domains.social.contracts.observations import SocialObservationError
from app.domains.social.repository.blocks import write_pair_is_blocked
from app.domains.social.repository.event_evidence import get_post
from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError
from app.domains.world_characters.service.event_scope import validate_event_scope


class SqlAlchemyObservationReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def world_character(self, *, world_id: str, world_character_id: str, lock: bool = False) -> ObservationWorldCharacter:
        try:
            return validate_event_scope(self.db, world_id=world_id, world_character_id=world_character_id, lock=lock)
        except WorldCharacterSocialScopeError as exc:
            raise SocialObservationError(str(exc)) from exc

    def get_post(self, post_id: str) -> ObservationPost | None:
        return get_post(self.db, post_id)

    def pair_blocked(self, *, world_id: str, actor_id: str, target_id: str) -> bool:
        return write_pair_is_blocked(self.db, world_id=world_id, actor_id=actor_id, target_id=target_id)
