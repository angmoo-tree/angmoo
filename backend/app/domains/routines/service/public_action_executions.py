from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.core import unit_of_work


def create_public_action_execution(
    db: Session,
    *,
    run_id: str,
    character_id: str,
    signature: str,
    scope: str,
    action_type: str,
    target_post_id: str | None = None,
    target_profile_type: str | None = None,
    target_profile_id: str | None = None,
    brief_hash: str | None = None,
    world_id: str | None = None,
    actor_world_character_id: str | None = None,
    feed_observation_id: str | None = None,
    interaction_intent: str | None = None,
    comment_purpose: str | None = None,
) -> models.AgentPublicActionExecution:
    execution = models.AgentPublicActionExecution(
        run_id=run_id,
        character_id=character_id,
        signature=signature,
        scope=scope,
        action_type=action_type,
        target_post_id=target_post_id,
        target_profile_type=target_profile_type,
        target_profile_id=target_profile_id,
        brief_hash=brief_hash,
        world_id=world_id,
        actor_world_character_id=actor_world_character_id,
        feed_observation_id=feed_observation_id,
        interaction_intent=interaction_intent,
        comment_purpose=comment_purpose,
        status="pending",
    )
    db.add(execution)
    unit_of_work.finish_write(db, execution)
    return execution


def mark_public_action_execution_finished(
    db: Session,
    execution: models.AgentPublicActionExecution,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    failure_class: str | None = None,
) -> models.AgentPublicActionExecution:
    execution.status = status
    execution.result = result
    execution.failure_class = failure_class
    execution.completed_at = datetime.now(UTC)
    unit_of_work.finish_write(db, execution)
    return execution
