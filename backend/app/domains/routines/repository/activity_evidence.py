from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import (
    OBSERVATION_NOTE_ACTION_TYPE,
    V6_STATE_PUBLIC_ACTION_LEDGER_TYPES,
    V6_OBSERVATION_CONTEXT_TYPES,
    HIDDEN_ACTIVITY_ACTION_TYPES,
)


def latest_feed_interest(
    db: Session, *, character_id: str, since: datetime
) -> models.AgentActivityLog | None:
    return db.scalar(
        select(models.AgentActivityLog)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type == "feed_interests_noted",
            models.AgentActivityLog.created_at >= since,
        )
        .order_by(models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc())
        .limit(1)
    )


def latest_feed_history_sanitize(
    db: Session, *, character_id: str, since: datetime, action_type: str
) -> models.AgentActivityLog | None:
    return db.scalar(
        select(models.AgentActivityLog)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type
            == action_type,
            models.AgentActivityLog.created_at >= since,
        )
        .order_by(models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc())
        .limit(1)
    )


def latest_inbox_review(
    db: Session, *, character_id: str, since: datetime
) -> models.AgentActivityLog | None:
    return db.scalar(
        select(models.AgentActivityLog)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type == "inbox_reviewed",
            models.AgentActivityLog.created_at >= since,
        )
        .order_by(models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc())
        .limit(1)
    )


def recent_observation_notes(
    db: Session, *, character_id: str, since: datetime
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.created_at >= since,
                models.AgentActivityLog.action_type == OBSERVATION_NOTE_ACTION_TYPE,
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(),
                models.AgentActivityLog.id.desc(),
            )
            .limit(5)
        )
    )


def state_activity_id_since(
    db: Session, *, character_id: str, since: datetime
) -> int | None:
    return db.scalar(
        select(models.AgentActivityLog.id)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type.in_(
                ("state_saved", "state_save_suppressed")
            ),
            models.AgentActivityLog.created_at >= since,
        )
        .limit(1)
    )


def activity_id_since(
    db: Session, *, character_id: str, since: datetime, action_types: tuple[str, ...]
) -> int | None:
    return db.scalar(
        select(models.AgentActivityLog.id)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type.in_(action_types),
            models.AgentActivityLog.created_at >= since,
        )
        .limit(1)
    )


def tick_public_action_logs(
    db: Session, *, character_id: str, since: datetime
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.created_at >= since,
                models.AgentActivityLog.action_type.in_(
                    V6_STATE_PUBLIC_ACTION_LEDGER_TYPES
                ),
            )
            .order_by(
                models.AgentActivityLog.created_at.asc(),
                models.AgentActivityLog.id.asc(),
            )
            .limit(20)
        )
    )


def visible_tick_activity_logs(
    db: Session, *, character_id: str, since: datetime
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.created_at >= since,
                models.AgentActivityLog.action_type.not_in(
                    HIDDEN_ACTIVITY_ACTION_TYPES
                ),
            )
            .order_by(models.AgentActivityLog.created_at.asc(), models.AgentActivityLog.id.asc())
            .limit(20)
        )
    )


def tick_observation_logs(
    db: Session, *, character_id: str, since: datetime
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.created_at >= since,
                models.AgentActivityLog.action_type.in_(V6_OBSERVATION_CONTEXT_TYPES),
            )
            .order_by(
                models.AgentActivityLog.created_at.asc(),
                models.AgentActivityLog.id.asc(),
            )
            .limit(10)
        )
    )
