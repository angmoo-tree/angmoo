"""ActivityLog counts and latest-action queries on the caller Session."""
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.service.tick_schedule import APP_TIMEZONE
from app.domains.routines.utils.activity_actions import _normalize_action_types, _public_action_log_types


def count_public_actions_since(
    db: Session, *, character_id: str, since: datetime
) -> int:
    return (
        db.scalar(
            select(func.count(models.AgentActivityLog.id)).where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type.in_(_public_action_log_types()),
                models.AgentActivityLog.created_at >= since,
            )
        )
        or 0
    )



def _count_action_today(
    db: Session,
    character_id: str,
    action_types: str | tuple[str, ...],
    now: datetime,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> int:
    local_now = now.astimezone(timezone)
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=timezone)
    action_type_values = _normalize_action_types(action_types)
    return (
        db.scalar(
            select(func.count(models.AgentActivityLog.id)).where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type.in_(action_type_values),
                models.AgentActivityLog.created_at >= day_start.astimezone(UTC),
            )
        )
        or 0
    )



def _latest_action_at(
    db: Session, character_id: str, action_types: str | tuple[str, ...]
) -> datetime | None:
    action_type_values = _normalize_action_types(action_types)
    return db.scalar(
        select(models.AgentActivityLog.created_at)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type.in_(action_type_values),
        )
        .order_by(models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc())
        .limit(1)
    )

