"""Execution evidence reads and links in the caller-owned transaction."""
from sqlalchemy.orm import Session
from app.domains.routines import models


def get_execution(db: Session, execution_id: int) -> models.AgentPublicActionExecution | None:
    return db.get(models.AgentPublicActionExecution, execution_id)


def set_social_event_id(execution: models.AgentPublicActionExecution, *, social_event_id: str) -> None:
    execution.social_event_id = social_event_id


def set_social_scope(execution: models.AgentPublicActionExecution, *, world_id: str, actor_world_character_id: str) -> None:
    execution.world_id = world_id
    execution.actor_world_character_id = actor_world_character_id


def set_interaction_intent(execution: models.AgentPublicActionExecution, *, interaction_intent: str | None) -> None:
    execution.interaction_intent = interaction_intent
