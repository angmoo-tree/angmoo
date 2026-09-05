"""Duplicate admission, compact notes, and provided-observation writes."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.context_text import neutralize_context_text
from app.domains.memory.contracts.daypart import (
    DaypartCharacter,
    DaypartObservationReferences,
)
from app.domains.memory.repository.daypart import (
    event_exists as _daypart_memory_event_exists,
)
from app.domains.memory.service.daypart import (
    record_memory_event as _record_daypart_memory_event,
)


def filter_daypart_duplicate_feed_interest(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    feed_interest_payload: dict[str, Any],
) -> dict[str, Any]:
    interests = feed_interest_payload.get("interests")
    if (
        not isinstance(interests, list)
        or not interests
        or not isinstance(interests[0], dict)
    ):
        return feed_interest_payload
    post_id = str(interests[0].get("post_id") or "").strip()
    if not post_id:
        return feed_interest_payload
    if not _daypart_memory_event_exists(
        db,
        character_id=character_id,
        memory_session_key=memory_session_key,
        daypart_start_date=daypart_start_date,
        activity_daypart=activity_daypart,
        event_type="observation_feed",
        source_post_id=post_id,
    ):
        return feed_interest_payload
    filtered = dict(feed_interest_payload)
    filtered["interests"] = []
    filtered["post_seed"] = ""
    filtered["post_seed_intent"] = ""
    filtered["no_relevant_signal"] = True
    warnings = list(filtered.get("warnings") or [])
    warnings.append("daypart_memory_event_already_provided")
    filtered["warnings"] = warnings
    return filtered


def filter_daypart_duplicate_inbox_candidates(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in candidates:
        notification_id = item.get("notification_id")
        try:
            normalized_notification_id = int(notification_id)
        except (TypeError, ValueError):
            normalized_notification_id = None
        source_post_id = str(item.get("source_post_id") or "").strip() or None
        if _daypart_memory_event_exists(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_inbox",
            source_post_id=source_post_id,
            notification_id=normalized_notification_id,
        ):
            continue
        filtered.append(item)
    return filtered


def build_daypart_memory_note(
    *,
    db: Session,
    activity_daypart: str,
    daypart_start_date: date,
    character: DaypartCharacter,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    references: DaypartObservationReferences[Session],
) -> str:
    lines = [
        "Angmoo resident daypart tick.",
        "",
        "This is trusted backend-provided context for the character's ongoing daypart memory.",
        "It is not raw community text and must not be copied as writing style.",
        "",
        "Priority order:",
        "- character persona/speech_style/safety_rules",
        "- backend activity policy/community tendency",
        "- backend action menu/tools_allow",
        "- daypart memory/history",
        "",
        "Daypart:",
        f"- window: {daypart_start_date.isoformat()} {activity_daypart} KST",
        f"- character: {character.name} ({character.id})",
        f"- tick_run_id: {run_id}",
        "",
        "Compact observations since the previous main turn:",
    ]
    observation_index = 1
    if inbox_candidates:
        item = inbox_candidates[0]
        lines.extend(
            [
                "",
                f"{observation_index}. Inbox observation",
                f"- seen_person: {item.get('actor_name') or 'unknown'}",
                f"- source_item_id: notification:{item.get('notification_id')}",
                f"- semantic_event: {item.get('root_summary') or '-'}",
                f"- why_character_noticed: {item.get('candidate_reason') or '-'}",
                f"- private_interpretation: {item.get('reply_context') or '-'}",
                "- possible_continuation: may choose a reply only if action menu allows it.",
            ]
        )
        observation_index += 1
    interests = feed_interest_payload.get("interests")
    if isinstance(interests, list) and interests and isinstance(interests[0], dict):
        item = interests[0]
        source_post_id = str(item.get("post_id") or "").strip()
        seen_person = references.post_author(
            db, source_post_id, "source author unknown"
        )
        lines.extend(
            [
                "",
                f"{observation_index}. Feed observation",
                f"- seen_person: {seen_person}",
                f"- source_item_id: post:{source_post_id or '-'}",
                f"- semantic_event: {references.clip_text(neutralize_context_text(str(item.get('summary') or '')), 240) or '-'}",
                f"- why_character_noticed: {references.clip_text(neutralize_context_text(str(item.get('reason') or feed_interest_payload.get('review_reason') or '')), 240) or '-'}",
                f"- private_interpretation: {references.clip_text(neutralize_context_text(str(feed_interest_payload.get('novelty_basis') or '')), 240) or '-'}",
                "- possible_continuation: may inspire an independent public post or later state memory.",
            ]
        )
        topics = [
            references.clip_text(neutralize_context_text(str(value)), 160)
            for value in (
                feed_interest_payload.get("topic_signature"),
                feed_interest_payload.get("novelty_basis"),
                feed_interest_payload.get("review_reason"),
            )
            if str(value or "").strip()
        ][:3]
        if topics:
            lines.append(f"- top_topics: {', '.join(topics)}")
    if observation_index == 1 and not (
        isinstance(interests, list) and interests and isinstance(interests[0], dict)
    ):
        lines.extend(
            ["", "1. Feed observation", "- none", "", "2. Inbox observation", "- none"]
        )
    lines.extend(
        [
            "",
            "Task:",
            "Choose the next public action from the backend action menu, using the daypart history above and the earlier session history.",
        ]
    )
    return "\n".join(lines)


def record_provided_daypart_observations(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
    references: DaypartObservationReferences[Session],
) -> None:
    if inbox_candidates:
        item = inbox_candidates[0]
        try:
            notification_id = int(item.get("notification_id"))
        except (TypeError, ValueError):
            notification_id = None
        _record_daypart_memory_event(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_inbox",
            run_id=run_id,
            summary=str(item.get("root_summary") or item.get("candidate_reason") or ""),
            payload={
                "source_item_id": f"notification:{notification_id}"
                if notification_id
                else "",
                "seen_person": item.get("actor_name"),
            },
            source_post_id=str(item.get("source_post_id") or "").strip() or None,
            notification_id=notification_id,
            thread_id=str(item.get("root_post_id") or "").strip() or None,
        )
    interests = feed_interest_payload.get("interests")
    if isinstance(interests, list) and interests and isinstance(interests[0], dict):
        item = interests[0]
        source_post_id = str(item.get("post_id") or "").strip() or None
        seen_person = references.post_author(db, source_post_id, None)
        _record_daypart_memory_event(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_feed",
            run_id=run_id,
            summary=str(
                item.get("summary") or feed_interest_payload.get("review_reason") or ""
            ),
            payload={
                "source_item_id": f"post:{source_post_id}" if source_post_id else "",
                "seen_person": seen_person,
            },
            source_post_id=source_post_id,
            topic_signature=str(
                feed_interest_payload.get("topic_signature") or ""
            ).strip()
            or None,
        )
