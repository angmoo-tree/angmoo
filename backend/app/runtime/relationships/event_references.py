"""Bind actual owner operations to the event caller's one Session."""
from typing import cast
from sqlalchemy.orm import Session
from app.domains.relationships.contracts.events import EventExecution
from app.domains.relationships.exceptions import SocialEventRuntimeError
from app.domains.worlds.service.character_entry import get_character_entry_world
from app.domains.world_characters.service.event_scope import validate_event_scope
from app.domains.world_characters.exceptions import WorldCharacterSocialScopeError
from app.domains.social.repository.blocks import world_character_pair_is_blocked
from app.domains.social.repository import event_evidence as social_evidence
from app.domains.routines.repository import event_evidence as routine_evidence
from app.domains.routines.service import public_action_executions
from app.domains.routines.models import AgentPublicActionExecution


class SqlAlchemyEventReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_world(self, world_id: str):
        return get_character_entry_world(self.db, world_id)

    def validate_world_character(self, *, world_id: str, world_character_id: str, lock: bool = False) -> None:
        try:
            validate_event_scope(self.db, world_id=world_id, world_character_id=world_character_id, lock=lock)
        except WorldCharacterSocialScopeError as exc:
            raise SocialEventRuntimeError(str(exc)) from exc

    def world_character_pair_is_blocked(self, *, world_id: str, first_world_character_id: str, second_world_character_id: str) -> bool:
        return world_character_pair_is_blocked(self.db, world_id=world_id, first_world_character_id=first_world_character_id, second_world_character_id=second_world_character_id)

    def get_post(self, post_id: str):
        return social_evidence.get_post(self.db, post_id)

    def get_numeric_source(self, *, source_object_type: str, source_id: int):
        if source_object_type == "agent_public_action_execution":
            return public_action_executions.get_execution(self.db, source_id)
        return social_evidence.get_numeric_source(self.db, source_object_type=source_object_type, source_id=source_id)

    def get_joint_activity(self, joint_activity_id: str):
        return routine_evidence.get_joint_activity(self.db, joint_activity_id)

    def get_execution(self, execution_id: int):
        return public_action_executions.get_execution(self.db, execution_id)

    def set_social_event_id(self, execution: EventExecution, *, social_event_id: str) -> None:
        public_action_executions.set_social_event_id(cast(AgentPublicActionExecution, execution), social_event_id=social_event_id)
