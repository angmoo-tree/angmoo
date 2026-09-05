"""Daypart history and writes, preserving each original commit boundary.

These events record context actually supplied and actions already performed.
They are distinct from the scoped long-term Memory candidates/items API.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.context_clipping import clip_context_text as _clip
from app.domains.memory.contracts.daypart import DaypartContext, DaypartRun
from app.domains.memory.models.daypart import AgentDaypartMemoryEvent
from app.domains.memory.policies.daypart import (
    compact_daypart_summary_event as _compact_daypart_summary_event,
)
from app.domains.memory.policies.daypart import (
    daypart_end_summary_payload as _daypart_end_summary_payload,
)
from app.domains.memory.policies.daypart import (
    daypart_end_summary_text as _daypart_end_summary_text,
)
from app.domains.memory.repository.daypart import (
    event_exists,
    handoff_events,
    recent_topic_events,
)

__all__ = [
    "event_exists",
    "handoff_events",
    "recent_topic_events",
    "history",
    "latest_summary",
    "seen_feed_post_ids",
    "seen_notification_ids",
    "record_event",
    "record_memory_event",
    "record_action_memory",
    "purge_expired_events",
    "finalize_closed_dayparts",
]

logger = logging.getLogger("app.services.langgraph_resident")


def purge_expired_events(db: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(
        days=settings.resident_daypart_session_retention_days
    )
    db.execute(
        delete(AgentDaypartMemoryEvent).where(
            AgentDaypartMemoryEvent.provided_at < cutoff
        )
    )
    db.commit()


def record_memory_event(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    event_type: str,
    run_id: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    source_post_id: str | None = None,
    notification_id: int | None = None,
    thread_id: str | None = None,
    topic_signature: str | None = None,
) -> None:
    event = AgentDaypartMemoryEvent(
        character_id=character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=daypart_start_date,
        activity_daypart=activity_daypart,
        event_type=event_type,
        source_post_id=source_post_id,
        notification_id=notification_id,
        thread_id=thread_id,
        topic_signature=topic_signature,
        run_id=run_id,
        summary=summary[:2000],
        payload=payload,
    )
    db.add(event)
    db.commit()


def record_action_memory(
    db: Session, *, run: DaypartRun, action_memory: dict[str, Any]
) -> None:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    session_context = gateway_result.get("session_context")
    if not isinstance(session_context, dict) or not session_context.get(
        "daypart_persistent"
    ):
        return
    memory_session_key = session_context.get("memory_session_key")
    daypart_start_date = session_context.get("daypart_start_date")
    activity_daypart = session_context.get("activity_daypart")
    if not (
        isinstance(memory_session_key, str)
        and isinstance(daypart_start_date, str)
        and isinstance(activity_daypart, str)
    ):
        return
    try:
        parsed_daypart_start = datetime.fromisoformat(daypart_start_date).date()
    except ValueError:
        return
    event = AgentDaypartMemoryEvent(
        character_id=run.character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=parsed_daypart_start,
        activity_daypart=activity_daypart,
        event_type=f"action_{action_memory.get('action_type') or 'public'}",
        source_post_id=action_memory.get("source_post") or action_memory.get("post_id"),
        run_id=run.id,
        summary=str(action_memory.get("public_result_summary") or "")[:2000],
        payload=action_memory,
        topic_signature=str(action_memory.get("topic") or "")[:300] or None,
    )
    db.add(event)
    db.commit()


def history(ctx: DaypartContext[Session]) -> list[dict[str, Any]]:
    if not ctx.memory_session_key:
        return []
    events = list(
        ctx.db.scalars(
            select(AgentDaypartMemoryEvent)
            .where(
                AgentDaypartMemoryEvent.character_id == ctx.character.id,
                AgentDaypartMemoryEvent.memory_session_key == ctx.memory_session_key,
            )
            .order_by(
                AgentDaypartMemoryEvent.provided_at.asc(),
                AgentDaypartMemoryEvent.id.asc(),
            )
            .limit(64)
        )
    )
    return [
        {
            "event_type": event.event_type,
            "source_post_id": event.source_post_id,
            "notification_id": event.notification_id,
            "topic_signature": event.topic_signature,
            "summary": _clip(event.summary, 600),
            "payload": event.payload or {},
            "provided_at": event.provided_at.isoformat(),
        }
        for event in events
    ]


def latest_summary(
    ctx: DaypartContext[Session],
) -> dict[str, Any] | None:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return None
    try:
        query = (
            select(AgentDaypartMemoryEvent)
            .where(AgentDaypartMemoryEvent.character_id == ctx.character.id)
            .where(AgentDaypartMemoryEvent.event_type == "daypart_summary")
            .where(AgentDaypartMemoryEvent.provided_at <= ctx.run_started_at)
        )
        if ctx.memory_session_key:
            query = query.where(
                AgentDaypartMemoryEvent.memory_session_key != ctx.memory_session_key
            )
        event = next(
            iter(
                db_scalars(
                    query.order_by(
                        AgentDaypartMemoryEvent.provided_at.desc(),
                        AgentDaypartMemoryEvent.id.desc(),
                    ).limit(1)
                )
            ),
            None,
        )
    except Exception:
        logger.debug(
            "Failed to load latest daypart summary",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return None
    return _compact_daypart_summary_event(event) if event is not None else None


def seen_feed_post_ids(ctx: DaypartContext[Session]) -> set[str]:
    if not ctx.memory_session_key:
        return set()
    return set(
        ctx.db.scalars(
            select(AgentDaypartMemoryEvent.source_post_id).where(
                AgentDaypartMemoryEvent.character_id == ctx.character.id,
                AgentDaypartMemoryEvent.memory_session_key == ctx.memory_session_key,
                AgentDaypartMemoryEvent.event_type == "observation_feed",
                AgentDaypartMemoryEvent.source_post_id.is_not(None),
            )
        )
    )


def seen_notification_ids(ctx: DaypartContext[Session]) -> set[int]:
    if not ctx.memory_session_key:
        return set()
    return set(
        ctx.db.scalars(
            select(AgentDaypartMemoryEvent.notification_id).where(
                AgentDaypartMemoryEvent.character_id == ctx.character.id,
                AgentDaypartMemoryEvent.memory_session_key == ctx.memory_session_key,
                AgentDaypartMemoryEvent.event_type == "observation_inbox",
                AgentDaypartMemoryEvent.notification_id.is_not(None),
            )
        )
    )


def record_event(
    ctx: DaypartContext[Session],
    *,
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    source_post_id: str | None = None,
    notification_id: int | None = None,
    thread_id: str | None = None,
    topic_signature: str | None = None,
) -> None:
    if (
        ctx.memory_session_key is None
        or ctx.daypart_start_date is None
        or ctx.activity_daypart is None
    ):
        return
    event = AgentDaypartMemoryEvent(
        character_id=ctx.character.id,
        memory_session_key=ctx.memory_session_key,
        daypart_start_date=ctx.daypart_start_date,
        activity_daypart=ctx.activity_daypart,
        event_type=event_type,
        source_post_id=source_post_id,
        notification_id=notification_id,
        thread_id=thread_id,
        topic_signature=topic_signature,
        run_id=ctx.run_id,
        summary=summary[:2000],
        payload=payload,
    )
    ctx.db.add(event)
    ctx.db.commit()


def finalize_closed_dayparts(
    ctx: DaypartContext[Session],
    *,
    current_start: datetime | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    if current_start is None:
        return result
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        result["status"] = "skipped"
        result["reason"] = "db_scalars_unavailable"
        return result
    try:
        events = list(
            db_scalars(
                select(AgentDaypartMemoryEvent)
                .where(AgentDaypartMemoryEvent.character_id == ctx.character.id)
                .where(AgentDaypartMemoryEvent.provided_at < current_start)
                .where(
                    AgentDaypartMemoryEvent.provided_at
                    >= current_start - timedelta(days=3)
                )
                .order_by(
                    AgentDaypartMemoryEvent.daypart_start_date.asc(),
                    AgentDaypartMemoryEvent.activity_daypart.asc(),
                    AgentDaypartMemoryEvent.provided_at.asc(),
                    AgentDaypartMemoryEvent.id.asc(),
                )
            )
        )
    except Exception as exc:
        ctx.db.rollback()
        return {
            **result,
            "status": "failed",
            "failure_class": type(exc).__name__,
        }
    grouped: dict[tuple[str, date, str], list[AgentDaypartMemoryEvent]] = {}
    for event in events:
        key = (
            event.memory_session_key,
            event.daypart_start_date,
            event.activity_daypart,
        )
        grouped.setdefault(key, []).append(event)
    for (
        memory_session_key,
        daypart_start_date,
        activity_daypart,
    ), group_events in grouped.items():
        if any(event.event_type == "daypart_summary" for event in group_events):
            result["summaries_skipped"] += 1
            continue
        source_events = [
            event for event in group_events if event.event_type != "daypart_summary"
        ]
        if not source_events:
            result["summaries_skipped"] += 1
            continue
        payload = _daypart_end_summary_payload(source_events)
        summary = _daypart_end_summary_text(payload)
        payload["finalized_by_run_id"] = ctx.run_id
        payload["finalized_at"] = ctx.run_started_at.isoformat()
        try:
            ctx.db.add(
                AgentDaypartMemoryEvent(
                    character_id=ctx.character.id,
                    memory_session_key=memory_session_key,
                    daypart_start_date=daypart_start_date,
                    activity_daypart=activity_daypart,
                    event_type="daypart_summary",
                    run_id=ctx.run_id,
                    summary=summary,
                    payload=payload,
                    provided_at=current_start - timedelta(microseconds=1),
                )
            )
            ctx.db.commit()
            result["summaries_created"] += 1
        except Exception as exc:
            ctx.db.rollback()
            result.setdefault("summary_errors", []).append(
                {
                    "memory_session_key": memory_session_key,
                    "failure_class": type(exc).__name__,
                }
            )
    return result
