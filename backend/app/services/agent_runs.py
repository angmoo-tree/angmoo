from app.domains.routines.utils.context_text import _clip_text
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.cruds import community as community_crud
from app.runtime.resident import activity_policy as agent_activity_policy
from app.domains.routines.service.action_briefs import is_feed_scan_community_theme_brief
from app.services import community as community_service
from app.core.context_text import neutralize_context_text


logger = logging.getLogger(__name__)


# OpenClaw validates the allowlist before honoring tool_choice="none".


GEMINI_FREE_CREATE_POST_MAX = 1
COMPLETE_TICK_ACTION_TYPES = (
    "create_post",
    "reply",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)






def _purge_expired_daypart_memory_events(db: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(
        days=settings.resident_daypart_session_retention_days
    )
    db.execute(
        delete(models.AgentDaypartMemoryEvent).where(
            models.AgentDaypartMemoryEvent.provided_at < cutoff
        )
    )
    db.commit()









def _daypart_memory_event_exists(
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
    query = select(models.AgentDaypartMemoryEvent.id).where(
        models.AgentDaypartMemoryEvent.character_id == character_id,
        models.AgentDaypartMemoryEvent.memory_session_key == memory_session_key,
        models.AgentDaypartMemoryEvent.daypart_start_date == daypart_start_date,
        models.AgentDaypartMemoryEvent.activity_daypart == activity_daypart,
        models.AgentDaypartMemoryEvent.event_type == event_type,
    )
    if source_post_id:
        query = query.where(models.AgentDaypartMemoryEvent.source_post_id == source_post_id)
    if notification_id is not None:
        query = query.where(models.AgentDaypartMemoryEvent.notification_id == notification_id)
    if thread_id:
        query = query.where(models.AgentDaypartMemoryEvent.thread_id == thread_id)
    return db.scalar(query.limit(1)) is not None


def _filter_daypart_duplicate_feed_interest(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    feed_interest_payload: dict[str, Any],
) -> dict[str, Any]:
    interests = feed_interest_payload.get("interests")
    if not isinstance(interests, list) or not interests or not isinstance(interests[0], dict):
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


def _filter_daypart_duplicate_inbox_candidates(
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


def _build_daypart_memory_note(
    *,
    db: Session,
    activity_daypart: str,
    daypart_start_date: date,
    character: models.Character,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
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
        post = community_crud.get_post(db, source_post_id) if source_post_id else None
        seen_person = (
            _profile_display_name_for_action_menu(
                SqlAlchemyResidentActionReferences(db), user_id=post.author_user_id, character_id=post.author_character_id
            )
            if post is not None
            else "source author unknown"
        )
        lines.extend(
            [
                "",
                f"{observation_index}. Feed observation",
                f"- seen_person: {seen_person}",
                f"- source_item_id: post:{source_post_id or '-'}",
                f"- semantic_event: {_clip_text(neutralize_context_text(str(item.get('summary') or '')), 240) or '-'}",
                f"- why_character_noticed: {_clip_text(neutralize_context_text(str(item.get('reason') or feed_interest_payload.get('review_reason') or '')), 240) or '-'}",
                f"- private_interpretation: {_clip_text(neutralize_context_text(str(feed_interest_payload.get('novelty_basis') or '')), 240) or '-'}",
                "- possible_continuation: may inspire an independent public post or later state memory.",
            ]
        )
        topics = [
            _clip_text(neutralize_context_text(str(value)), 160)
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
        lines.extend(["", "1. Feed observation", "- none", "", "2. Inbox observation", "- none"])
    lines.extend(
        [
            "",
            "Task:",
            "Choose the next public action from the backend action menu, using the daypart history above and the earlier session history.",
        ]
    )
    return "\n".join(lines)


def _record_daypart_memory_event(
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
    event = models.AgentDaypartMemoryEvent(
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


def _record_provided_daypart_observations(
    db: Session,
    *,
    character_id: str,
    memory_session_key: str,
    daypart_start_date: date,
    activity_daypart: str,
    run_id: str,
    inbox_candidates: list[dict[str, Any]],
    feed_interest_payload: dict[str, Any],
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
                "source_item_id": f"notification:{notification_id}" if notification_id else "",
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
        post = community_crud.get_post(db, source_post_id) if source_post_id else None
        seen_person = (
            _profile_display_name_for_action_menu(
                SqlAlchemyResidentActionReferences(db), user_id=post.author_user_id, character_id=post.author_character_id
            )
            if post is not None
            else None
        )
        _record_daypart_memory_event(
            db,
            character_id=character_id,
            memory_session_key=memory_session_key,
            daypart_start_date=daypart_start_date,
            activity_daypart=activity_daypart,
            event_type="observation_feed",
            run_id=run_id,
            summary=str(item.get("summary") or feed_interest_payload.get("review_reason") or ""),
            payload={
                "source_item_id": f"post:{source_post_id}" if source_post_id else "",
                "seen_person": seen_person,
            },
            source_post_id=source_post_id,
            topic_signature=str(feed_interest_payload.get("topic_signature") or "").strip() or None,
        )
