"""Execution evidence reads and links in the caller-owned transaction."""
from sqlalchemy.orm import Session
from app.domains.routines import models


def get_execution(db: Session, execution_id: int) -> models.AgentPublicActionExecution | None:
    return db.get(models.AgentPublicActionExecution, execution_id)


def set_social_event_id(execution: models.AgentPublicActionExecution, *, social_event_id: str) -> None:
    execution.social_event_id = social_event_id
