"""Resident feed interest admission, server-locked sanitization and durable notes."""

import hashlib
import json
import logging
import time as time_module
from typing import Any
from sqlalchemy.orm import Session
from app.core.bounded_text import _safe_topic_text
from app.domains.routines.schemas import feed_history as schemas
from app.domains.routines.contracts.feed_history_notes import FeedHistoryNoteReferences
from app.domains.routines.constants import (
    FEED_HISTORY_SANITIZED_ACTION_TYPE,
    FEED_HISTORY_SANITIZED_CONSUMED_LIMIT,
    RECENT_FEED_INTEREST_HISTORY_LIMIT,
    RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT,
)
from app.domains.routines.service import activity_logs as agent_crud
from app.domains.routines.service.feed_history import (
    feed_seed_source_already_consumed,
    recent_own_root_topic_exists,
    build_feed_history_sanitize_skeleton,
)
from app.domains.routines.service.feed_history_values import (
    _feed_history_sanitize_skeleton_has_items,
    _merge_feed_history_sanitize_payload,
    _sanitize_feed_history_item,
    _feed_history_payload_json,
)

logger = logging.getLogger("app.services.community")


def _diagnostic_hash(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return hashlib.sha256(trimmed.encode("utf-8")).hexdigest()[:16]


def _json_byte_length(value: Any) -> int | None:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return None


def _feed_history_sanitize_payload_bytes(
    data: schemas.AgentFeedHistorySanitizeCreate,
) -> int | None:
    return _json_byte_length(data.model_dump())


def _elapsed_ms(started_at: float) -> int:
    return int((time_module.monotonic() - started_at) * 1000)


def note_agent_tool_feed_interests(
    db: Session,
    session_key: str,
    data: schemas.AgentFeedInterestsCreate,
    *,
    references: FeedHistoryNoteReferences,
) -> schemas.AgentToolNoteRead:
    run = references.authorize(
        db, session_key=session_key, action="note_feed_interests"
    )
    interests: list[schemas.AgentFeedInterestItem] = []
    hidden_interest_count = 0
    warnings: list[str] = []
    for item in data.interests[:1]:
        post = references.get_post(db, item.post_id)
        if post is None or not references.is_public_context_visible(db, post):
            hidden_interest_count += 1
            continue
        interests.append(item)
    post_seed = data.post_seed or ""
    post_seed_intent = references.normalize_post_seed_intent(
        data.post_seed_intent, post_seed=data.post_seed
    )
    if not interests:
        if post_seed.strip() or post_seed_intent:
            warnings.append("post_seed_dropped_without_feed_interest")
        post_seed = ""
        post_seed_intent = ""
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and (post_seed_intent == "public_reaction")
    ):
        warnings.append("legacy_reaction_seed_not_writable")
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and feed_seed_source_already_consumed(
            db, character_id=run.character_id, source_post_id=interests[0].post_id
        )
    ):
        post_seed = ""
        post_seed_intent = ""
        warnings.append("seed_source_already_consumed")
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and recent_own_root_topic_exists(
            db,
            character_id=run.character_id,
            topic_signature=data.topic_signature,
            references=references.history,
        )
    ):
        post_seed = ""
        post_seed_intent = ""
        warnings.append("post_seed_topic_repeated_recent_own_root")
    payload = {
        "interests": [item.model_dump() for item in interests],
        "post_seed": post_seed,
        "post_seed_intent": post_seed_intent,
        "topic_signature": _safe_topic_text(data.topic_signature, 300),
        "novelty_basis": _safe_topic_text(data.novelty_basis, 500),
        "no_relevant_signal": not interests,
        "review_reason": data.review_reason or "",
    }
    if hidden_interest_count:
        warnings.append("hidden_or_unavailable_interest_post_ignored")
    if warnings:
        payload["warnings"] = warnings
    result = json.dumps(payload, ensure_ascii=False)
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="feed_interests_noted",
        target_post_id=interests[0].post_id if interests else run.post_id,
        reason="agent_tool_note_feed_interests",
        result=result[:4000],
    )
    return schemas.AgentToolNoteRead(
        status="ok", action_type="feed_interests_noted", result=result
    )


def note_agent_tool_feed_history_sanitize(
    db: Session,
    session_key: str,
    data: schemas.AgentFeedHistorySanitizeCreate,
    *,
    references: FeedHistoryNoteReferences,
) -> schemas.AgentToolNoteRead:
    started_at = time_module.monotonic()
    session_key_hash = _diagnostic_hash(session_key)
    payload_bytes = _feed_history_sanitize_payload_bytes(data)
    logger.info(
        "feed_history_sanitize_tool_endpoint_started sessionKeyHash=%s consumedSourcesCount=%s recentFeedInterestsCount=%s recentOwnRootTopicsCount=%s requestPayloadBytes=%s",
        session_key_hash,
        len(data.consumed_sources),
        len(data.recent_feed_interests),
        len(data.recent_own_root_topics),
        payload_bytes,
    )
    run: Any | None = None
    try:
        run = references.authorize(
            db, session_key=session_key, action="note_feed_history_sanitize"
        )
        skeleton = (
            build_feed_history_sanitize_skeleton(
                db, character_id=run.character_id, references=references.history
            )
            if db is not None
            else {}
        )
        if _feed_history_sanitize_skeleton_has_items(skeleton):
            payload = _merge_feed_history_sanitize_payload(skeleton=skeleton, data=data)
        else:
            payload = {
                "consumed_sources": [
                    _sanitize_feed_history_item(item)
                    for item in data.consumed_sources[
                        :FEED_HISTORY_SANITIZED_CONSUMED_LIMIT
                    ]
                ],
                "recent_feed_interests": [
                    _sanitize_feed_history_item(item)
                    for item in data.recent_feed_interests[
                        :RECENT_FEED_INTEREST_HISTORY_LIMIT
                    ]
                ],
                "recent_own_root_topics": [
                    _sanitize_feed_history_item(item)
                    for item in data.recent_own_root_topics[
                        :RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT
                    ]
                ],
            }
        result = _feed_history_payload_json(payload)
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type=FEED_HISTORY_SANITIZED_ACTION_TYPE,
            target_post_id=run.post_id,
            reason="agent_tool_note_feed_history_sanitize",
            result=result[:4000],
        )
        logger.info(
            "feed_history_sanitize_tool_endpoint_finished sessionKeyHash=%s agentRunId=%s characterId=%s status=ok durationMs=%s resultBytes=%s",
            session_key_hash,
            getattr(run, "id", None),
            getattr(run, "character_id", None),
            _elapsed_ms(started_at),
            _json_byte_length(result),
        )
        return schemas.AgentToolNoteRead(
            status="ok", action_type=FEED_HISTORY_SANITIZED_ACTION_TYPE, result=result
        )
    except Exception as exc:
        failure_kind = (
            "authorization_error"
            if isinstance(exc, references.authorization_error)
            else "backend_exception"
        )
        logger.warning(
            "feed_history_sanitize_tool_endpoint_error sessionKeyHash=%s agentRunId=%s characterId=%s status=error durationMs=%s errorCategory=%s failureKind=%s",
            session_key_hash,
            getattr(run, "id", None),
            getattr(run, "character_id", None),
            _elapsed_ms(started_at),
            type(exc).__name__,
            failure_kind,
        )
        raise
