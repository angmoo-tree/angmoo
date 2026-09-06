"""Same Session reads from their actual owners and runtime graph connection."""
from sqlalchemy.orm import Session
from app.config import Settings
from app.domains.characters.service.profile import get_character
from app.domains.world_characters.service.projection_scope import (
    diagnostic_world_character_status, find_diagnostic_world_character,
)
from app.domains.social.repository.blocks import world_character_pair_is_blocked
from app.domains.social.repository.event_evidence import get_post
from app.domains.routines.repository.joint_diagnostics import list_active_joint_activities
from app.domains.relationships.contracts.graph_read import GraphProvider, RelationshipGraphReadGateway
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway


class SqlAlchemyDiagnosticReferences:
    def __init__(self, db: Session, config: Settings) -> None:
        self.db = db
        self.config = config

    def get_character(self, character_id: str):
        return get_character(self.db, character_id)

    def find_world_character(self, *, world_id: str, character_id: str):
        return find_diagnostic_world_character(self.db, world_id=world_id, character_id=character_id)

    def world_character_status(self, *, world_id: str, world_character_id: str) -> str | None:
        return diagnostic_world_character_status(self.db, world_id=world_id, world_character_id=world_character_id)

    def pair_blocked(self, *, world_id: str, actor_id: str, target_id: str) -> bool:
        return world_character_pair_is_blocked(self.db, world_id=world_id, first_world_character_id=actor_id, second_world_character_id=target_id)

    def get_post(self, post_id: str):
        return get_post(self.db, post_id)

    def list_active_joint_activities(self, *, world_id: str, world_character_id: str):
        return list_active_joint_activities(self.db, world_id=world_id, world_character_id=world_character_id)

    def graph_gateway(self, *, graph_provider: GraphProvider) -> RelationshipGraphReadGateway:
        return SqlAlchemyRelationshipGraphReadGateway(self.db, config=self.config, graph_provider=graph_provider)
