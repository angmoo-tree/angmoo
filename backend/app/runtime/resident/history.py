"""Read resident daypart history with the caller Session; no SNS engine."""
from __future__ import annotations
import logging
from functools import partial
from datetime import UTC, date, datetime, timedelta
from typing import Any
from app.domains.memory.service import daypart as daypart_memory
from app.domains.memory.policies import daypart as daypart_memory_policy
from app.domains.memory.contracts.daypart import DaypartEvent
from app.domains.memory.service.daypart import history as _daypart_history, latest_summary, seen_feed_post_ids, seen_notification_ids
from app.domains.routines.policies.handoff_coverage import _TOPIC_ARC_EVENT_TYPE
from app.domains.routines.policies.resident_clock import _yesterday_kst_window
from app.domains.routines.service import topic_arcs as topic_arc_service, writing_context as writing_context_service
from app.domains.routines.contracts.topic_arcs import TopicArcWorkflows
from app.domains.routines.contracts.context_reads import WritingContextWorkflows
from app.domains.relationships.service import points as relationship_points
from app.runtime.resident import langgraph_queries
from app.runtime.resident.context import LangGraphResidentContext
from app.runtime.routines import activity_policy as agent_activity_policy
from app.runtime.social.planned_actions import _clip
logger = logging.getLogger(__name__)
_TOPIC_ARC_LOOKBACK = timedelta(hours=48)
_topic_arc_workflows = TopicArcWorkflows(clip=_clip, last_post_created_at=langgraph_queries._topic_arc_last_post_created_at, latest_event=lambda ctx, arc_id: _latest_topic_arc_event(ctx, arc_id))
_coerce_topic_arc_payload = partial(topic_arc_service._coerce_topic_arc_payload, workflows=_topic_arc_workflows)
_today_own_root_posts_for_coverage = partial(langgraph_queries._today_own_root_posts_for_coverage, clip=_clip)
_writing_context_workflows = WritingContextWorkflows(clip=_clip, coerce_topic_arc=_coerce_topic_arc_payload,
    topic_arc_for_prompt=partial(topic_arc_service._topic_arc_for_prompt, workflows=_topic_arc_workflows),
    previous_handoff=lambda ctx: _yesterday_handoff_context(ctx), history_prompt=lambda ctx: _daypart_history_for_prompt(ctx),
    recent_own_posts=partial(langgraph_queries._recent_own_root_posts, clip=_clip),
    latest_summary=latest_summary, seen_feed_posts=seen_feed_post_ids, seen_notifications=seen_notification_ids)
_compact_yesterday_handoff_event = partial(writing_context_service._compact_yesterday_handoff_event, workflows=_writing_context_workflows)



def _yesterday_handoff_context(ctx: LangGraphResidentContext) -> list[dict[str, Any]]:
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return []
    start_utc, end_utc = _yesterday_kst_window(ctx)
    coverage_posts = _today_own_root_posts_for_coverage(ctx)
    try:
        events = daypart_memory.handoff_events(
            ctx.db, character_id=ctx.character.id,
            event_types=[_TOPIC_ARC_EVENT_TYPE, "langgraph_tick", "observation_feed", "observation_inbox", "relationship_review"],
            start_utc=start_utc, end_utc=end_utc,
        )
    except Exception:
        logger.debug(
            "Failed to load yesterday handoff context",
            exc_info=True,
            extra={"character_id": ctx.character.id},
        )
        return []
    items: list[dict[str, Any]] = []
    for event in events:
        item = _compact_yesterday_handoff_event(
            event, coverage_posts=coverage_posts
        )
        if item is not None:
            items.append(item)
        if len(items) >= 8:
            break
    return items

def _latest_topic_arc_event(
    ctx: LangGraphResidentContext, arc_id: str | None
) -> DaypartEvent | None:
    if not arc_id:
        return None
    db_scalars = getattr(getattr(ctx, "db", None), "scalars", None)
    if not callable(db_scalars):
        return None
    cutoff = ctx.run_started_at.astimezone(UTC) - _TOPIC_ARC_LOOKBACK
    try:
        events = daypart_memory.recent_topic_events(
            ctx.db, character_id=ctx.character.id, event_type=_TOPIC_ARC_EVENT_TYPE, cutoff=cutoff
        )
    except Exception:
        logger.debug(
            "Failed to load topic arc events for continuity context",
            exc_info=True,
            extra={"arc_id": arc_id, "character_id": ctx.character.id},
        )
        return None
    for event in events:
        payload = _coerce_topic_arc_payload(getattr(event, "payload", None) or {})
        if payload and payload.get("arc_id") == arc_id:
            return event
    return None

def _daypart_history_for_prompt(ctx: LangGraphResidentContext) -> list[dict[str, Any]]:
    return daypart_memory_policy.history_for_prompt(_daypart_history(ctx))

def _daypart_start_utc(
    daypart_start_date: date | None,
    activity_daypart: str | None,
) -> datetime | None:
    return daypart_memory_policy.daypart_start_utc(
        daypart_start_date,
        activity_daypart,
        timezone=agent_activity_policy.APP_TIMEZONE,
    )

def _finalize_closed_dayparts(ctx: LangGraphResidentContext) -> dict[str, Any]:
    current_start = _daypart_start_utc(ctx.daypart_start_date, ctx.activity_daypart)
    result: dict[str, Any] = {
        "status": "skipped" if current_start is None else "succeeded",
        "expired_relationship_points": 0,
        "summaries_created": 0,
        "summaries_skipped": 0,
    }
    try:
        result["expired_relationship_points"] = relationship_points.expire_relationship_points(
            ctx.db, now=ctx.run_started_at
        )
    except Exception as exc:
        ctx.db.rollback()
        result["relationship_point_expire_error"] = type(exc).__name__
    return daypart_memory.finalize_closed_dayparts(
        ctx, current_start=current_start, result=result
    )
