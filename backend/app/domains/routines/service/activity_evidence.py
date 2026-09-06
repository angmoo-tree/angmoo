from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.context_text import neutralize_context_text
from app.domains.routines.constants import (
    GENERIC_OBSERVATION_RESULT,
    PUBLIC_ACTION_CLAIM_PATTERNS,
    V6_STATE_PUBLIC_ACTION_LEDGER_TYPES,
)
from app.domains.routines.repository import activity_evidence as evidence_queries
from app.domains.routines.utils.context_text import _clip_text


def _latest_v6_feed_interest_payload(
    db: Session, *, character_id: str, since: datetime
) -> dict[str, Any]:
    log = evidence_queries.latest_feed_interest(db, character_id=character_id, since=since)
    if log is None:
        return {"interests": [], "post_seed": "", "no_relevant_signal": True}
    try:
        payload = json.loads(log.result)
    except json.JSONDecodeError:
        return {"interests": [], "post_seed": "", "no_relevant_signal": True}
    return payload if isinstance(payload, dict) else {"interests": []}


def _latest_v6_feed_history_sanitize_payload(
    db: Session, *, character_id: str, since: datetime, action_type: str
) -> dict[str, Any] | None:
    log = evidence_queries.latest_feed_history_sanitize(db, character_id=character_id, since=since, action_type=action_type)
    if log is None:
        return None
    try:
        payload = json.loads(log.result)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _latest_v6_inbox_review_payload(
    db: Session, *, character_id: str, since: datetime
) -> dict[str, Any]:
    log = evidence_queries.latest_inbox_review(db, character_id=character_id, since=since)
    if log is None:
        return {"candidate_notification_id": None}
    try:
        payload = json.loads(log.result)
    except json.JSONDecodeError:
        return {"candidate_notification_id": None}
    return payload if isinstance(payload, dict) else {"candidate_notification_id": None}


def _format_observation_result(
    db: Session, *, character_id: str, since: datetime
) -> str:
    db.expire_all()
    logs = evidence_queries.recent_observation_notes(db, character_id=character_id, since=since)
    for log in logs:
        note = neutralize_context_text(log.result or "").strip()
        if note and not _has_public_action_claim(note):
            return note[:1000]
    return GENERIC_OBSERVATION_RESULT


def _has_public_action_claim(text: str) -> bool:
    return any(pattern.search(text) for pattern in PUBLIC_ACTION_CLAIM_PATTERNS)


def _has_state_saved_since(
    db: Session, *, character_id: str, since: datetime
) -> bool:
    db.expire_all()
    return (
        evidence_queries.state_activity_id_since(db, character_id=character_id, since=since)
        is not None
    )


def _has_activity_since(
    db: Session, *, character_id: str, since: datetime, action_types: tuple[str, ...]
) -> bool:
    db.expire_all()
    return (
        evidence_queries.activity_id_since(db, character_id=character_id, since=since, action_types=action_types)
        is not None
    )


def _has_tick_completed_since(
    db: Session, *, character_id: str, since: datetime
) -> bool:
    return _has_activity_since(
        db, character_id=character_id, since=since, action_types=("tick_completed",)
    )


def _has_thread_viewed_since(
    db: Session, *, character_id: str, since: datetime
) -> bool:
    return _has_activity_since(
        db, character_id=character_id, since=since, action_types=("thread_viewed",)
    )


def _format_tick_public_action_ledger_since(
    db: Session, *, character_id: str, since: datetime
) -> str:
    db.expire_all()
    logs = evidence_queries.tick_public_action_logs(db, character_id=character_id, since=since)
    grouped: dict[str, list[str]] = {
        action_type: [] for action_type in V6_STATE_PUBLIC_ACTION_LEDGER_TYPES
    }
    for log in logs:
        detail = log.target_post_id or _clip_text(
            neutralize_context_text(log.result or log.reason), 120
        )
        grouped[log.action_type].append(detail or "recorded")

    return "\n".join(
        f"- {action_type}: {', '.join(grouped[action_type]) if grouped[action_type] else 'none'}"
        for action_type in V6_STATE_PUBLIC_ACTION_LEDGER_TYPES
    )


def _format_tick_activity_since(
    db: Session, *, character_id: str, since: datetime
) -> str:
    db.expire_all()
    logs = evidence_queries.visible_tick_activity_logs(db, character_id=character_id, since=since)
    if not logs:
        return "- none"
    return "\n".join(
        (
            f"- {log.created_at.isoformat()} {log.action_type}; "
            f"target_post_id={log.target_post_id or '-'}; "
            f"{_clip_text(neutralize_context_text(log.result or log.reason), 500)}"
        )
        for log in logs
    )


def _format_tick_observation_context_since(
    db: Session, *, character_id: str, since: datetime
) -> str:
    db.expire_all()
    logs = evidence_queries.tick_observation_logs(db, character_id=character_id, since=since)
    if not logs:
        return "- none"
    return "\n".join(
        (
            f"- {log.action_type}; target_post_id={log.target_post_id or '-'}; "
            f"{_clip_text(neutralize_context_text(log.result or log.reason), 900)}"
        )
        for log in logs
    )
