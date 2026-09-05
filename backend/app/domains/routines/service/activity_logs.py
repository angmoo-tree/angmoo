"""Visible activity history and original caller-owned log persistence."""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.routines import models
from app.domains.routines.constants import HIDDEN_ACTIVITY_ACTION_TYPES, STATE_SAVE_DEDUPE_WINDOW


def filter_visible_activity_logs(
    logs: list[models.AgentActivityLog], *, limit: int
) -> list[models.AgentActivityLog]:
    visible: list[models.AgentActivityLog] = []
    state_saved_seen: list[datetime] = []
    for log in logs:
        if log.action_type in HIDDEN_ACTIVITY_ACTION_TYPES:
            continue
        if log.action_type == "state_saved":
            if any(
                abs(saved_at - log.created_at) <= STATE_SAVE_DEDUPE_WINDOW
                for saved_at in state_saved_seen
            ):
                continue
            state_saved_seen.append(log.created_at)
        visible.append(log)
        if len(visible) >= limit:
            break
    return visible


def list_recent_activity(
    db: Session, character_id: str, limit: int = 20
) -> list[models.AgentActivityLog]:
    logs = list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(models.AgentActivityLog.character_id == character_id)
            .where(
                models.AgentActivityLog.action_type.not_in(
                    HIDDEN_ACTIVITY_ACTION_TYPES
                )
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc()
            )
            .limit(max(limit * 3, limit + 20))
        )
    )
    return filter_visible_activity_logs(logs, limit=limit)


def log_activity(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    action_type: str,
    target_post_id: str | None,
    reason: str,
    result: str,
) -> models.AgentActivityLog:
    log = models.AgentActivityLog(
        user_id=user_id,
        character_id=character_id,
        action_type=action_type,
        target_post_id=target_post_id,
        reason=reason,
        result=result,
    )
    db.add(log)
    unit_of_work.finish_write(db, log)
    return log
