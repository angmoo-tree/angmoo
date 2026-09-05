"""Same-Session owner operations used at each Social action's original call point."""

from sqlalchemy.orm import Session
from app.domains.world_characters.service import action_scope
from app.domains.routines.service import public_action_executions
from app.domains.social.contracts.action_scope import ActionScopeReferences
from app.domains.social.contracts.source_writes import SourceWorldCharacter
from app.domains.social.contracts.subjective_persistence import SubjectiveExecution
from app.domains.social.exceptions import LangGraphSocialApplyError


class RuntimeActionScopeReferences(ActionScopeReferences):
    def __init__(self, db: Session) -> None:
        self.db = db

    def active_world_character(self, *, character_id: str) -> SourceWorldCharacter:
        return action_scope.active_world_character(
            self.db, character_id=character_id, error_type=LangGraphSocialApplyError
        )

    def get_world_character(
        self, world_character_id: str
    ) -> SourceWorldCharacter | None:
        return action_scope.get_world_character(self.db, world_character_id)

    def world_character_for_character(
        self, *, world_id: str, character_id: str
    ) -> SourceWorldCharacter:
        return action_scope.world_character_for_character(
            self.db,
            world_id=world_id,
            character_id=character_id,
            error_type=LangGraphSocialApplyError,
        )

    def set_execution_scope(
        self,
        execution: SubjectiveExecution,
        *,
        world_id: str,
        actor_world_character_id: str,
    ) -> None:
        public_action_executions.set_social_scope(
            execution,
            world_id=world_id,
            actor_world_character_id=actor_world_character_id,
        )
