"""Same-Session Daypart persistence queries; caller owns error handling."""

from datetime import date, datetime

from app.domains.memory.models.daypart import AgentDaypartMemoryEvent
from sqlalchemy import select
from sqlalchemy.orm import Session


def event_exists(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    event_type: str,
    source_post_id: str | None = None,
    notification_id: int | None = None,
    thread_id: str | None = None,
) -> bool:
    if not source_post_id and notification_id is None and not thread_id:
        return False
    query = select(AgentDaypartMemoryEvent.id).where(
        AgentDaypartMemoryEvent.character_id == character_id,
        AgentDaypartMemoryEvent.memory_session_key == memory_session_key,
        AgentDaypartMemoryEvent.daypart_start_date == daypart_start_date,
        AgentDaypartMemoryEvent.activity_daypart == activity_daypart,
        AgentDaypartMemoryEvent.event_type == event_type,
    )
    if source_post_id:
        query = query.where(AgentDaypartMemoryEvent.source_post_id == source_post_id)
    if notification_id is not None:
        query = query.where(AgentDaypartMemoryEvent.notification_id == notification_id)
    if thread_id:
        query = query.where(AgentDaypartMemoryEvent.thread_id == thread_id)
    return db.scalar(query.limit(1)) is not None


def recent_topic_events(
    db: Session, *, character_id: str, event_type: str, cutoff: datetime
) -> list[AgentDaypartMemoryEvent]:
    return list(
        db.scalars(
            select(AgentDaypartMemoryEvent)
            .where(AgentDaypartMemoryEvent.character_id == character_id)
            .where(AgentDaypartMemoryEvent.event_type == event_type)
            .where(AgentDaypartMemoryEvent.provided_at >= cutoff)
            .order_by(
                AgentDaypartMemoryEvent.provided_at.desc(),
                AgentDaypartMemoryEvent.id.desc(),
            )
            .limit(20)
        )
    )


def handoff_events(
    db: Session,
    *,
    character_id: str,
    event_types: list[str],
    start_utc: datetime,
    end_utc: datetime,
) -> list[AgentDaypartMemoryEvent]:
    return list(
        db.scalars(
            select(AgentDaypartMemoryEvent)
            .where(AgentDaypartMemoryEvent.character_id == character_id)
            .where(AgentDaypartMemoryEvent.event_type.in_(event_types))
            .where(AgentDaypartMemoryEvent.provided_at >= start_utc)
            .where(AgentDaypartMemoryEvent.provided_at < end_utc)
            .order_by(
                AgentDaypartMemoryEvent.provided_at.desc(),
                AgentDaypartMemoryEvent.id.desc(),
            )
            .limit(12)
        )
    )
