"""Writing and current-daypart context, preserving existing read order."""

from __future__ import annotations

import hashlib
from typing import Any

from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.contracts.context_reads import (
    ResidentReadContext,
    WritingContextWorkflows,
)
from app.domains.routines.policies.handoff_coverage import (
    _handoff_continuity_kind,
    _handoff_coverage,
)
from app.domains.routines.policies.resident_clock import (
    _aware_datetime,
    _format_current_time_reference,
)
from app.domains.routines.repository import (
    independent_topics as independent_topic_queries,
)
from app.domains.routines.service.independent_topics import (
    _base_independent_topic_candidates,
)


def _coverage_text_from_payload(
    payload: Any, *, workflows: WritingContextWorkflows
) -> str:
    if not isinstance(payload, dict):
        return ""
    parts: list[str] = []
    topic_arc = workflows.coerce_topic_arc(payload)
    if topic_arc:
        parts.append(workflows.clip(topic_arc.get("arc_title"), 300))
        parts.extend(
            workflows.clip(step.get("brief"), 300)
            for step in topic_arc.get("steps", [])
            if isinstance(step, dict)
        )
    for key in ("summary", "memory_note", "topic_signature", "title", "brief"):
        if key in payload:
            parts.append(workflows.clip(payload.get(key), 500))
    state_result = payload.get("state_result")
    if isinstance(state_result, dict):
        parts.append(workflows.clip(state_result.get("summary"), 500))
    publish_result = payload.get("publish_result")
    if isinstance(publish_result, dict):
        result = publish_result.get("result")
        if isinstance(result, dict):
            parts.append(workflows.clip(result.get("title"), 300))
            parts.append(workflows.clip(result.get("topic_key"), 120))
    return " ".join(part for part in parts if part)


def _compact_yesterday_handoff_event(
    event: Any,
    *,
    coverage_posts: list[dict[str, Any]],
    workflows: WritingContextWorkflows,
) -> dict[str, Any] | None:
    event_type = str(getattr(event, "event_type", "") or "").strip()
    summary = workflows.clip(getattr(event, "summary", ""), 300)
    topic_signature = workflows.clip(getattr(event, "topic_signature", ""), 300)
    payload = getattr(event, "payload", None)
    coverage_text = " ".join(
        part
        for part in (
            summary,
            topic_signature,
            _coverage_text_from_payload(payload, workflows=workflows),
        )
        if part
    )
    if not summary and not coverage_text:
        return None
    provided_at = _aware_datetime(getattr(event, "provided_at", None))
    material = "|".join(
        [
            event_type,
            str(getattr(event, "id", "") or ""),
            provided_at.isoformat() if provided_at else "",
            summary,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return {
        "handoff_id": f"handoff:{digest}",
        "event_type": event_type,
        "provided_at": provided_at.isoformat() if provided_at else None,
        "summary": summary or workflows.clip(topic_signature, 300),
        "continuity_kind": _handoff_continuity_kind(event_type),
        **_handoff_coverage(coverage_text or summary, coverage_posts),
    }


def _feed_mood_for_prompt(
    feed_observation: dict[str, Any], *, workflows: WritingContextWorkflows
) -> dict[str, Any]:
    items = feed_observation.get("selected_posts")
    if not isinstance(items, list):
        items = []
    return {
        "theme_topics": feed_observation.get("feed_theme_topics") or [],
        "returned_count": feed_observation.get("returned_count") or 0,
        "sample_summaries": [
            workflows.clip(
                item.get("semantic_summary") or item.get("topic_signature"), 180
            )
            for item in items[:5]
            if isinstance(item, dict)
        ],
    }


def _independent_post_context_for_prompt(
    ctx: ResidentReadContext,
    *,
    feed_observation: dict[str, Any],
    independent_post_roll: dict[str, Any],
    active_topic_arc: dict[str, Any] | None = None,
    workflows: WritingContextWorkflows,
) -> dict[str, Any]:
    current = ctx.run_started_at.astimezone(APP_TIMEZONE)
    return {
        "roll": independent_post_roll.get("roll"),
        "tick_probability": independent_post_roll.get("tick_probability"),
        "roll_passed": bool(independent_post_roll.get("passed")),
        "level": independent_post_roll.get("level"),
        "blocked_reason": independent_post_roll.get("blocked_reason"),
        "topic_pool_size": independent_post_roll.get("topic_pool_size"),
        "topic_prompt_count": independent_post_roll.get("topic_prompt_count"),
        "topics": independent_post_roll.get("topics") or [],
        "active_topic_arc": workflows.topic_arc_for_prompt(
            active_topic_arc,
            current_date=current.date(),
        ),
        "yesterday_handoff_context": workflows.previous_handoff(ctx),
        "current_time": current.isoformat(),
        "current_time_reference": _format_current_time_reference(ctx.run_started_at),
        "daypart": ctx.activity_daypart,
        "recent_daypart_memory": workflows.history_prompt(ctx)[-12:],
        "character_state": {
            "mood": workflows.clip(getattr(ctx.state, "mood", ""), 120),
            "summary": workflows.clip(getattr(ctx.state, "summary", ""), 600),
            "memory_note": workflows.clip(getattr(ctx.state, "memory_note", ""), 600),
        },
        "recent_own_root_posts": workflows.recent_own_posts(ctx),
        "persona": {
            "name": ctx.character.name,
            "handle": ctx.character.handle,
            "one_liner": workflows.clip(ctx.character.one_liner, 300),
            "personality": workflows.clip(ctx.character.personality, 900),
            "speech_style": workflows.clip(ctx.character.speech_style, 900),
            "worldview": workflows.clip(ctx.character.worldview, 900),
            "topic_preferences": workflows.clip(ctx.character.topic_preferences, 900),
            "persona_summary": workflows.clip(ctx.character.persona_summary, 900),
        },
        "today_feed_mood": _feed_mood_for_prompt(feed_observation, workflows=workflows),
    }


def _current_daypart_context(
    ctx: ResidentReadContext, *, workflows: WritingContextWorkflows
) -> dict[str, Any]:
    history = workflows.history_prompt(ctx)
    plan = next(
        (
            item
            for item in reversed(history)
            if item.get("event_type") == "daypart_plan"
        ),
        None,
    )
    summary = next(
        (
            item
            for item in reversed(history)
            if item.get("event_type") == "daypart_summary"
        ),
        None,
    ) or workflows.latest_summary(ctx)
    return {
        "status": "ready" if history else "missing",
        "memory_session_key": ctx.memory_session_key,
        "daypart_start_date": (
            ctx.daypart_start_date.isoformat() if ctx.daypart_start_date else None
        ),
        "activity_daypart": ctx.activity_daypart,
        "daypart_plan": plan,
        "previous_daypart_summary": summary,
        "recent_events": history[-20:],
        "seen_feed_post_ids": sorted(workflows.seen_feed_posts(ctx)),
        "seen_notification_ids": sorted(workflows.seen_notifications(ctx)),
        "used_topic_keys_today": sorted(
            independent_topic_queries._today_independent_topic_keys(ctx)
        ),
    }


def _mandatory_post_context(
    ctx: ResidentReadContext,
    *,
    relationship_points: list[dict[str, Any]],
    selected_feed_seed: dict[str, Any] | None,
    workflows: WritingContextWorkflows,
) -> dict[str, Any]:
    allowed = set(ctx.activity_policy.allowed_actions)
    run_mode = getattr(ctx, "run_mode", "scheduled") or "scheduled"
    post_required = "post" in allowed
    blocked_reason = None
    if "post" not in allowed:
        blocked_reason = "post_not_allowed"
    return {
        "run_mode": run_mode,
        "post_required": post_required,
        "blocked_reason": blocked_reason,
        "owner_feed_cue": (
            {
                "id": getattr(ctx.feed_cue, "id", None),
                "topic": workflows.clip(getattr(ctx.feed_cue, "topic", ""), 800),
            }
            if ctx.feed_cue is not None
            else None
        ),
        "base_topic_candidates": _base_independent_topic_candidates(
            ctx, clip=workflows.clip
        ),
        "relationship_point_candidates": relationship_points,
        "action_continuation_candidates": [],
        "selected_feed_seed": selected_feed_seed
        if isinstance(selected_feed_seed, dict)
        else {"mode": "none"},
        "current_time_reference": _format_current_time_reference(ctx.run_started_at),
        "daypart": ctx.activity_daypart,
        "recent_own_root_posts": workflows.recent_own_posts(ctx),
    }
