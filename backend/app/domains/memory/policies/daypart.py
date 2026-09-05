"""Deterministic Daypart timestamps, summaries and prompt fields."""

from datetime import UTC, date, datetime, tzinfo
from typing import Any

from app.core.context_clipping import clip_context_text as _clip
from app.domains.memory.contracts.daypart import DaypartEvent


def compact_daypart_summary_event(
    event: DaypartEvent,
) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "memory_session_key": event.memory_session_key,
        "daypart_start_date": (
            event.daypart_start_date.isoformat() if event.daypart_start_date else None
        ),
        "activity_daypart": event.activity_daypart,
        "summary": _clip(event.summary, 600),
        "payload": event.payload or {},
        "provided_at": event.provided_at.isoformat() if event.provided_at else None,
    }


def daypart_start_utc(
    daypart_start_date: date | None,
    activity_daypart: str | None,
    *,
    timezone: tzinfo,
) -> datetime | None:
    if daypart_start_date is None or not activity_daypart:
        return None
    hour_by_daypart = {"morning": 6, "afternoon": 14, "night": 22}
    hour = hour_by_daypart.get(activity_daypart)
    if hour is None:
        return None
    return datetime(
        daypart_start_date.year,
        daypart_start_date.month,
        daypart_start_date.day,
        hour,
        tzinfo=timezone,
    ).astimezone(UTC)


def daypart_end_summary_payload(
    events: list[DaypartEvent],
) -> dict[str, Any]:
    seen_feed_post_ids: list[str] = []
    seen_notification_ids: list[int] = []
    root_posts: list[dict[str, Any]] = []
    public_action_counts: dict[str, int] = {}
    relationship_point_counts = {"created": 0, "consumed": 0, "skipped": 0}
    topic_keys: list[str] = []

    def _remember_topic_key(value: Any) -> None:
        topic_key = _clip(value, 80) or None
        if topic_key and topic_key not in topic_keys:
            topic_keys.append(topic_key)

    for event in events:
        if event.event_type == "observation_feed" and event.source_post_id:
            if event.source_post_id not in seen_feed_post_ids:
                seen_feed_post_ids.append(event.source_post_id)
        if (
            event.event_type == "observation_inbox"
            and event.notification_id is not None
        ):
            if event.notification_id not in seen_notification_ids:
                seen_notification_ids.append(event.notification_id)
        if event.topic_signature:
            _remember_topic_key(event.topic_signature)

        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.event_type == "relationship_point_update":
            for key in ("created", "consumed", "skipped"):
                value = payload.get(key)
                if isinstance(value, list):
                    relationship_point_counts[key] += len(value)
            continue

        publish_result = payload.get("publish_result")
        if not isinstance(publish_result, dict):
            continue
        actions = publish_result.get("actions")
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("status") not in {"succeeded", "reused"}:
                continue
            action_type = str(action.get("action_type") or "").strip() or "unknown"
            public_action_counts[action_type] = (
                public_action_counts.get(action_type, 0) + 1
            )
            result = (
                action.get("result") if isinstance(action.get("result"), dict) else {}
            )
            if action_type == "post":
                post_id = _clip(result.get("post_id"), 64) or None
                topic_key = _clip(result.get("topic_key"), 80) or None
                if topic_key:
                    _remember_topic_key(topic_key)
                root_posts.append(
                    {
                        "post_id": post_id,
                        "topic_key": topic_key,
                        "title": _clip(result.get("title"), 160) or None,
                    }
                )

    return {
        "source_event_count": len(events),
        "seen_feed_post_ids": seen_feed_post_ids[:50],
        "seen_notification_ids": seen_notification_ids[:50],
        "public_action_counts": public_action_counts,
        "root_posts": root_posts[:20],
        "used_topic_keys": topic_keys[:50],
        "relationship_point_counts": relationship_point_counts,
        "repetition_prevention": {
            "seen_feed_post_count": len(seen_feed_post_ids),
            "seen_notification_count": len(seen_notification_ids),
            "used_topic_key_count": len(topic_keys),
        },
    }


def daypart_end_summary_text(payload: dict[str, Any]) -> str:
    actions = payload.get("public_action_counts")
    action_text = (
        ", ".join(f"{key}={value}" for key, value in sorted(actions.items()))
        if isinstance(actions, dict) and actions
        else "none"
    )
    relationship_counts = payload.get("relationship_point_counts")
    created = consumed = 0
    if isinstance(relationship_counts, dict):
        created = int(relationship_counts.get("created") or 0)
        consumed = int(relationship_counts.get("consumed") or 0)
    return _clip(
        "daypart closed: "
        f"events={payload.get('source_event_count', 0)}; "
        f"actions={action_text}; "
        f"root_posts={len(payload.get('root_posts') or [])}; "
        f"relationship_points_created={created}; "
        f"relationship_points_consumed={consumed}",
        2000,
    )


def history_for_prompt(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_type": event.get("event_type"),
            "source_post_id": event.get("source_post_id"),
            "notification_id": event.get("notification_id"),
            "topic_signature": event.get("topic_signature"),
            "summary": _clip(event.get("summary"), 600),
            "provided_at": event.get("provided_at"),
        }
        for event in history
    ]
