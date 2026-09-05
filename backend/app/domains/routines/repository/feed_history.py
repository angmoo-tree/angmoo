"""Owned activity-log history queries in the caller Session."""

from __future__ import annotations
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.constants import (
    FEED_SEED_CONSUMED_ACTION_TYPE,
    FEED_HISTORY_SANITIZED_ACTION_TYPE,
    FEED_SEED_CONSUMED_LOOKBACK_DAYS,
    FEED_SEED_CONSUMED_LIMIT,
    RECENT_FEED_INTEREST_LOG_SCAN_LIMIT,
    RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS,
    RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT,
)


def _feed_seed_consumed_cutoff(*, lookback_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=max(1, lookback_days))


def list_recent_feed_seed_consumed_logs(
    db: Session,
    *,
    character_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
    limit: int = FEED_SEED_CONSUMED_LIMIT,
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == FEED_SEED_CONSUMED_ACTION_TYPE,
                models.AgentActivityLog.target_post_id.is_not(None),
                models.AgentActivityLog.created_at
                >= _feed_seed_consumed_cutoff(lookback_days=lookback_days),
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(),
                models.AgentActivityLog.id.desc(),
            )
            .limit(max(1, limit))
        )
    )


def find_recent_consumed_source_id(
    db: Session,
    *,
    character_id: str,
    source_post_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
) -> int | None:
    return db.scalar(
        select(models.AgentActivityLog.id)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type == FEED_SEED_CONSUMED_ACTION_TYPE,
            models.AgentActivityLog.target_post_id == source_post_id,
            models.AgentActivityLog.created_at
            >= _feed_seed_consumed_cutoff(lookback_days=lookback_days),
        )
        .limit(1)
    )


def list_recent_feed_interest_logs(
    db: Session,
    *,
    character_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
    limit: int = RECENT_FEED_INTEREST_LOG_SCAN_LIMIT,
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == "feed_interests_noted",
                models.AgentActivityLog.result.is_not(None),
                models.AgentActivityLog.created_at
                >= _feed_seed_consumed_cutoff(lookback_days=lookback_days),
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(),
                models.AgentActivityLog.id.desc(),
            )
            .limit(max(1, limit))
        )
    )


def _feed_seed_consumed_log_exists(
    db: Session, *, character_id: str, source_post_id: str
) -> bool:
    return (
        db.scalar(
            select(models.AgentActivityLog.id)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == FEED_SEED_CONSUMED_ACTION_TYPE,
                models.AgentActivityLog.target_post_id == source_post_id,
            )
            .limit(1)
        )
        is not None
    )


def latest_post_created_log(
    db: Session, *, character_id: str, post_id: str
) -> models.AgentActivityLog | None:
    log = db.scalar(
        select(models.AgentActivityLog)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type == "post_created",
            models.AgentActivityLog.target_post_id == post_id,
            models.AgentActivityLog.result.is_not(None),
        )
        .order_by(
            models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc()
        )
        .limit(1)
    )
    return log
