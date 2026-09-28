from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models


def get_public_action_execution_by_signature(
    db: Session, signature: str
) -> models.AgentPublicActionExecution | None:
    return db.scalar(
        select(models.AgentPublicActionExecution).where(
            models.AgentPublicActionExecution.signature == signature
        )
    )


def successful_social_replies(db: Session, *, activity_id: str, world_id: str, actor_id: str):
    return list(db.scalars(select(models.AgentPublicActionExecution).where(
        models.AgentPublicActionExecution.run_id == activity_id,
        models.AgentPublicActionExecution.world_id == world_id,
        models.AgentPublicActionExecution.actor_world_character_id == actor_id,
        models.AgentPublicActionExecution.scope.in_(("inbox", "feed")),
        models.AgentPublicActionExecution.action_type == "reply",
        models.AgentPublicActionExecution.status == "succeeded").order_by(models.AgentPublicActionExecution.id)))
