"""Resident consumed-source history, server-owned context and bounded presentation."""

from __future__ import annotations
from datetime import UTC, datetime, timedelta
import json
import logging
from sqlalchemy.orm import Session
from app.core.json_objects import _json_object
from app.core.context_text import neutralize_context_text
from app.core.bounded_text import _clip_text, _safe_topic_text
from app.domains.routines import models
from app.domains.routines.contracts.feed_history import FeedHistoryReferences
from app.domains.routines.service.activity_logs import log_activity
from app.domains.routines.service.feed_history_values import (
    _safe_feed_history_post_id,
    _feed_history_sanitize_skeleton_item,
)
from app.domains.routines.repository.feed_history import (
    list_recent_feed_seed_consumed_logs,
    list_recent_feed_interest_logs,
    _feed_seed_consumed_log_exists,
)
from app.domains.routines.constants import (
    FEED_SEED_CONSUMED_ACTION_TYPE,
    FEED_HISTORY_SANITIZED_ACTION_TYPE,
    FEED_SEED_CONSUMED_LOOKBACK_DAYS,
    FEED_SEED_CONSUMED_LIMIT,
    RECENT_FEED_INTEREST_LOG_SCAN_LIMIT,
    RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS,
    RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT,
    FEED_HISTORY_SANITIZED_CONSUMED_LIMIT,
    RECENT_FEED_INTEREST_HISTORY_LIMIT,
    RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT,
)

logger = logging.getLogger("app.services.community")


def format_feed_seed_consumed_sources_for_prompt(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> str:
    logs = list_recent_feed_seed_consumed_logs(db, character_id=character_id)
    if not logs:
        return "- none"
    lines: list[str] = []
    for log in logs:
        source_post_id = log.target_post_id or "-"
        source_post = references.get_post(db, source_post_id)
        source_title = source_post.title if source_post is not None else ""
        result_payload = _json_object(log.result)
        created_post_id = str(result_payload.get("created_post_id") or "-")
        post_seed = _clip_text(
            neutralize_context_text(str(result_payload.get("post_seed") or "")), 120
        )
        topic_signature = _safe_topic_text(result_payload.get("topic_signature"), 300)
        novelty_basis = _safe_topic_text(result_payload.get("novelty_basis"), 300)
        lines.append(
            "\n".join(
                [
                    f"- post_id: {source_post_id}",
                    f"  consumed_at: {log.created_at.isoformat()}",
                    f"  created_post_id: {created_post_id}",
                    f"  topic_signature: {topic_signature or '-'}",
                    f"  novelty_basis: {novelty_basis or '-'}",
                    f"  source_title: {_clip_text(neutralize_context_text(source_title), 120) or '-'}",
                    f"  prior_post_seed: {post_seed or '-'}",
                ]
            )
        )
    return "\n".join(lines)


def format_recent_feed_interest_history_for_prompt(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> str:
    logs = list_recent_feed_interest_logs(db, character_id=character_id)
    if not logs:
        return "- none"
    lines: list[str] = []
    seen_post_ids: set[str] = set()
    for log in logs:
        payload = _json_object(log.result)
        if not isinstance(payload, dict):
            continue
        interests = payload.get("interests")
        if not isinstance(interests, list) or not interests:
            continue
        first_interest = interests[0]
        if not isinstance(first_interest, dict):
            continue
        post_id = str(first_interest.get("post_id") or "").strip()
        if not post_id or post_id in seen_post_ids:
            continue
        post = references.get_post(db, post_id)
        if post is None or not references.is_eligible(
            db, character_id=character_id, post=post
        ):
            continue
        seen_post_ids.add(post_id)
        topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
        if not topic_signature:
            topic_signature = references.fallback_topic(
                title=str(payload.get("post_seed") or ""),
                body=" / ".join(
                    [
                        str(first_interest.get("summary") or ""),
                        str(first_interest.get("reason") or ""),
                    ]
                ),
            )
        novelty_basis = _safe_topic_text(payload.get("novelty_basis"), 300)
        lines.append(
            "\n".join(
                [
                    f"- post_id: {post.id}",
                    f"  interested_at: {log.created_at.isoformat()}",
                    f"  author: {neutralize_context_text(post.author_name or '-')}",
                    f"  topic_signature: {topic_signature or '-'}",
                    f"  novelty_basis: {novelty_basis or '-'}",
                    "  source_title: "
                    + (_clip_text(neutralize_context_text(post.title), 120) or "-"),
                    "  body_preview: " + (references.body_preview(post.body) or "-"),
                    "  prior_feed_scan:",
                    "    summary: "
                    + (
                        _clip_text(
                            neutralize_context_text(
                                str(first_interest.get("summary") or "")
                            ),
                            160,
                        )
                        or "-"
                    ),
                    "    reason: "
                    + (
                        _clip_text(
                            neutralize_context_text(
                                str(first_interest.get("reason") or "")
                            ),
                            180,
                        )
                        or "-"
                    ),
                    "    review_reason: "
                    + (
                        _clip_text(
                            neutralize_context_text(
                                str(payload.get("review_reason") or "")
                            ),
                            180,
                        )
                        or "-"
                    ),
                    "    post_seed: "
                    + (
                        _clip_text(
                            neutralize_context_text(
                                str(payload.get("post_seed") or "")
                            ),
                            180,
                        )
                        or "-"
                    ),
                ]
            )
        )
        if len(lines) >= RECENT_FEED_INTEREST_HISTORY_LIMIT:
            break
    return "\n".join(lines) if lines else "- none"


def format_recent_own_root_topic_history_for_prompt(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> str:
    cutoff = datetime.now(UTC) - timedelta(hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS)
    posts = references.recent_roots(
        db,
        character_id=character_id,
        cutoff=cutoff,
        limit=RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT,
    )
    if not posts:
        return "- none"
    lines: list[str] = []
    for post in posts:
        if not references.public_visible(db, post):
            continue
        metadata = references.topic_metadata(db, post=post, character_id=character_id)
        topic_signature = metadata["topic_signature"] or references.fallback_topic(
            title=post.title, body=post.body
        )
        novelty_basis = metadata["novelty_basis"]
        lines.append(
            "\n".join(
                [
                    f"- post_id: {post.id}",
                    f"  created_at: {post.created_at.isoformat()}",
                    f"  topic_signature: {topic_signature or '-'}",
                    f"  novelty_basis: {novelty_basis or '-'}",
                    "  title: "
                    + (_clip_text(neutralize_context_text(post.title), 120) or "-"),
                    f"  body_preview: {references.body_preview(post.body) or '-'}",
                ]
            )
        )
        if len(lines) >= RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT:
            break
    return "\n".join(lines) if lines else "- none"


def _build_consumed_sources_sanitize_skeleton(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    logs = list_recent_feed_seed_consumed_logs(db, character_id=character_id)[
        :FEED_HISTORY_SANITIZED_CONSUMED_LIMIT
    ]
    for log in logs:
        source_post_id = _safe_feed_history_post_id(log.target_post_id)
        if not source_post_id:
            continue
        source_post = references.get_post(db, source_post_id)
        source_title = source_post.title if source_post is not None else ""
        result_payload = _json_object(log.result)
        items.append(
            _feed_history_sanitize_skeleton_item(
                post_id=source_post_id,
                topic_signature=result_payload.get("topic_signature"),
                novelty_basis=result_payload.get("novelty_basis"),
                source_title=source_title,
                summary_source=result_payload.get("post_seed"),
                timestamp_label="consumed_at",
                timestamp_value=log.created_at,
            )
        )
    return items


def _build_recent_feed_interests_sanitize_skeleton(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> list[dict[str, str]]:
    logs = list_recent_feed_interest_logs(db, character_id=character_id)
    items: list[dict[str, str]] = []
    seen_post_ids: set[str] = set()
    for log in logs:
        payload = _json_object(log.result)
        interests = payload.get("interests")
        if not isinstance(interests, list) or not interests:
            continue
        first_interest = interests[0]
        if not isinstance(first_interest, dict):
            continue
        post_id = _safe_feed_history_post_id(first_interest.get("post_id"))
        if not post_id or post_id in seen_post_ids:
            continue
        post = references.get_post(db, post_id)
        if post is None or not references.is_eligible(
            db, character_id=character_id, post=post
        ):
            continue
        seen_post_ids.add(post_id)
        topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
        if not topic_signature:
            topic_signature = references.fallback_topic(
                title=str(payload.get("post_seed") or ""),
                body=" / ".join(
                    [
                        str(first_interest.get("summary") or ""),
                        str(first_interest.get("reason") or ""),
                    ]
                ),
            )
        summary_source = " / ".join(
            (
                item
                for item in [
                    str(first_interest.get("summary") or "").strip(),
                    str(first_interest.get("reason") or "").strip(),
                    str(payload.get("review_reason") or "").strip(),
                    str(payload.get("post_seed") or "").strip(),
                ]
                if item
            )
        )
        items.append(
            _feed_history_sanitize_skeleton_item(
                post_id=post_id,
                topic_signature=topic_signature,
                novelty_basis=payload.get("novelty_basis"),
                source_title=post.title,
                summary_source=summary_source,
                timestamp_label="interested_at",
                timestamp_value=log.created_at,
            )
        )
        if len(items) >= RECENT_FEED_INTEREST_HISTORY_LIMIT:
            break
    return items


def _build_recent_own_root_topics_sanitize_skeleton(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> list[dict[str, str]]:
    cutoff = datetime.now(UTC) - timedelta(hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS)
    posts = references.recent_roots(
        db,
        character_id=character_id,
        cutoff=cutoff,
        limit=RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT,
    )
    items: list[dict[str, str]] = []
    for post in posts:
        if not references.public_visible(db, post):
            continue
        metadata = references.topic_metadata(db, post=post, character_id=character_id)
        topic_signature = metadata["topic_signature"] or references.fallback_topic(
            title=post.title, body=post.body
        )
        items.append(
            _feed_history_sanitize_skeleton_item(
                post_id=post.id,
                topic_signature=topic_signature,
                novelty_basis=metadata["novelty_basis"],
                source_title=post.title,
                summary_source=references.body_preview(post.body),
                timestamp_label="created_at",
                timestamp_value=post.created_at,
            )
        )
        if len(items) >= RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT:
            break
    return items


def build_feed_history_sanitize_skeleton(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> dict[str, list[dict[str, str]]]:
    return {
        "consumed_sources": _build_consumed_sources_sanitize_skeleton(
            db, references=references, character_id=character_id
        ),
        "recent_feed_interests": _build_recent_feed_interests_sanitize_skeleton(
            db, references=references, character_id=character_id
        ),
        "recent_own_root_topics": _build_recent_own_root_topics_sanitize_skeleton(
            db, references=references, character_id=character_id
        ),
    }


def format_feed_history_metadata_fallback_for_prompt(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> dict[str, str]:
    return {
        "consumed_seed_sources": _format_consumed_sources_metadata_only(
            db, references=references, character_id=character_id
        ),
        "recent_feed_interest_history": _format_recent_feed_interests_metadata_only(
            db, references=references, character_id=character_id
        ),
        "recent_own_root_topic_history": _format_recent_own_roots_metadata_only(
            db, references=references, character_id=character_id
        ),
    }


def _format_consumed_sources_metadata_only(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> str:
    logs = list_recent_feed_seed_consumed_logs(db, character_id=character_id)[
        :FEED_HISTORY_SANITIZED_CONSUMED_LIMIT
    ]
    if not logs:
        return "- none"
    lines: list[str] = []
    for log in logs:
        source_post_id = log.target_post_id or "-"
        source_post = references.get_post(db, source_post_id)
        source_title = source_post.title if source_post is not None else ""
        result_payload = _json_object(log.result)
        lines.append(
            "\n".join(
                [
                    f"- post_id: {source_post_id}",
                    f"  consumed_at: {log.created_at.isoformat()}",
                    f"  created_post_id: {result_payload.get('created_post_id') or '-'}",
                    "  topic_signature: "
                    + (
                        _safe_topic_text(result_payload.get("topic_signature"), 300)
                        or "-"
                    ),
                    "  novelty_basis: "
                    + (
                        _safe_topic_text(result_payload.get("novelty_basis"), 300)
                        or "-"
                    ),
                    "  source_title: "
                    + (_clip_text(neutralize_context_text(source_title), 120) or "-"),
                ]
            )
        )
    return "\n".join(lines)


def _format_recent_feed_interests_metadata_only(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> str:
    logs = list_recent_feed_interest_logs(db, character_id=character_id)
    if not logs:
        return "- none"
    lines: list[str] = []
    seen_post_ids: set[str] = set()
    for log in logs:
        payload = _json_object(log.result)
        interests = payload.get("interests")
        if not isinstance(interests, list) or not interests:
            continue
        first_interest = interests[0]
        if not isinstance(first_interest, dict):
            continue
        post_id = str(first_interest.get("post_id") or "").strip()
        if not post_id or post_id in seen_post_ids:
            continue
        post = references.get_post(db, post_id)
        if post is None or not references.is_eligible(
            db, character_id=character_id, post=post
        ):
            continue
        seen_post_ids.add(post_id)
        topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
        novelty_basis = _safe_topic_text(payload.get("novelty_basis"), 300)
        lines.append(
            "\n".join(
                [
                    f"- post_id: {post.id}",
                    f"  interested_at: {log.created_at.isoformat()}",
                    f"  author: {neutralize_context_text(post.author_name or '-')}",
                    f"  topic_signature: {topic_signature or '-'}",
                    f"  novelty_basis: {novelty_basis or '-'}",
                    "  source_title: "
                    + (_clip_text(neutralize_context_text(post.title), 120) or "-"),
                ]
            )
        )
        if len(lines) >= RECENT_FEED_INTEREST_HISTORY_LIMIT:
            break
    return "\n".join(lines) if lines else "- none"


def _format_recent_own_roots_metadata_only(
    db: Session, *, references: FeedHistoryReferences, character_id: str
) -> str:
    cutoff = datetime.now(UTC) - timedelta(hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS)
    posts = references.recent_roots(
        db,
        character_id=character_id,
        cutoff=cutoff,
        limit=RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT,
    )
    lines: list[str] = []
    for post in posts:
        if not references.public_visible(db, post):
            continue
        metadata = references.topic_metadata(db, post=post, character_id=character_id)
        topic_signature = metadata["topic_signature"] or references.fallback_topic(
            title=post.title, body=post.body
        )
        lines.append(
            "\n".join(
                [
                    f"- post_id: {post.id}",
                    f"  created_at: {post.created_at.isoformat()}",
                    f"  topic_signature: {topic_signature or '-'}",
                    f"  novelty_basis: {metadata['novelty_basis'] or '-'}",
                    "  source_title: "
                    + (_clip_text(neutralize_context_text(post.title), 120) or "-"),
                ]
            )
        )
        if len(lines) >= RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT:
            break
    return "\n".join(lines) if lines else "- none"


def _extract_feed_seed_source_from_run(
    run: models.AgentRun, *, references: FeedHistoryReferences
) -> tuple[str, str, str, str] | None:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    action_gate = gateway_result.get("action_gate")
    if not isinstance(action_gate, dict):
        return None
    prepared_brief = action_gate.get("prepared_create_post_brief")
    if not references.is_feed_theme(prepared_brief):
        return None
    feed_interests = action_gate.get("feed_interests")
    if not isinstance(feed_interests, dict):
        return None
    interests = feed_interests.get("interests")
    if not isinstance(interests, list) or not interests:
        return None
    first_interest = interests[0]
    if not isinstance(first_interest, dict):
        return None
    source_post_id = str(first_interest.get("post_id") or "").strip()
    if not source_post_id:
        return None
    post_seed = str(feed_interests.get("post_seed") or "").strip()
    topic_signature = str(feed_interests.get("topic_signature") or "").strip()
    novelty_basis = str(feed_interests.get("novelty_basis") or "").strip()
    return (source_post_id, post_seed, topic_signature, novelty_basis)


def maybe_log_feed_seed_consumed_for_created_post(
    db: Session,
    *,
    references: FeedHistoryReferences,
    run: models.AgentRun,
    created_post_id: str,
) -> models.AgentActivityLog | None:
    seed_source = _extract_feed_seed_source_from_run(run, references=references)
    if seed_source is None:
        return None
    source_post_id, post_seed, topic_signature, novelty_basis = seed_source
    if source_post_id == created_post_id:
        return None
    if _feed_seed_consumed_log_exists(
        db, character_id=run.character_id, source_post_id=source_post_id
    ):
        return None
    if references.get_post(db, source_post_id) is None:
        return None
    payload = {
        "created_post_id": created_post_id,
        "run_id": run.id,
        "post_seed": _clip_text(neutralize_context_text(post_seed), 240),
        "topic_signature": _safe_topic_text(topic_signature, 300),
        "novelty_basis": _safe_topic_text(novelty_basis, 500),
        "consumed_at": datetime.now(UTC).isoformat(),
    }
    try:
        return log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type=FEED_SEED_CONSUMED_ACTION_TYPE,
            target_post_id=source_post_id,
            reason="feed_scan_post_seed_created_post",
            result=json.dumps(payload, ensure_ascii=False)[:4000],
        )
    except Exception:
        db.rollback()
        logger.exception(
            "feed_seed_consumed_log_failed character_id=%s run_id=%s source_post_id=%s created_post_id=%s",
            run.character_id,
            run.id,
            source_post_id,
            created_post_id,
        )
        return None


from app.domains.routines.repository.feed_history import find_recent_consumed_source_id


def feed_seed_source_already_consumed(
    db: Session,
    *,
    character_id: str,
    source_post_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
) -> bool:
    return (
        find_recent_consumed_source_id(
            db,
            character_id=character_id,
            source_post_id=source_post_id,
            lookback_days=lookback_days,
        )
        is not None
    )


def recent_own_root_topic_exists(
    db: Session,
    *,
    references: FeedHistoryReferences,
    character_id: str,
    topic_signature: str | None,
) -> bool:
    topic = _safe_topic_text(topic_signature, 300)
    if not topic or db is None:
        return False
    cutoff = datetime.now(UTC) - timedelta(hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS)
    posts = references.recent_roots(
        db,
        character_id=character_id,
        cutoff=cutoff,
        limit=RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT,
    )
    for post in posts:
        if not references.public_visible(db, post):
            continue
        metadata = references.topic_metadata(db, post=post, character_id=character_id)
        existing_topic = metadata["topic_signature"] or references.fallback_topic(
            title=post.title, body=post.body
        )
        if _safe_topic_text(existing_topic, 300) == topic:
            return True
    return False
