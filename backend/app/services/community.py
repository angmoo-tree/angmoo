from app.domains.characters.service import state as character_state
from app.domains.characters.exceptions import CharacterStateNotFoundError
import hashlib
import json
import logging
import re
import time as time_module
from datetime import UTC, datetime, time, timedelta
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.core import unit_of_work
from app.core.search_text import build_post_search_document
from app.cruds import agent_runs as agent_run_crud
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.services import agent_activity_policy
from app.services import community_abuse_quota
from app.services.agent_briefs import (
    is_feed_scan_community_theme_brief,
    normalize_post_seed_intent,
)
from app.services.llm_context import neutralize_context_text

logger = logging.getLogger(__name__)

DELETED_CHARACTER_NAME = "삭제한 앵무"
COMPLETE_TICK_POLICY_ACTIONS = {
    "create_post": "post",
    "reply": "reply",
    "like": "like",
    "repost": "repost",
    "follow": "follow",
    "unfollow": "unfollow",
    "observe": "observe",
}
COMPLETE_TICK_CANDIDATE_ACTION_TYPES = {"like", "repost", "follow"}
COMPLETE_TICK_DECISION_TYPES = {
    "existing_post_interaction",
    "create_post",
    "observe",
    "relationship_review",
}
NOOP_COMPLETE_TICK_ACTION_PREFIXES = ("like_skipped_",)
FEED_SEED_CONSUMED_ACTION_TYPE = "feed_seed_consumed"
FEED_HISTORY_SANITIZED_ACTION_TYPE = "feed_history_sanitized"
FEED_SEED_CONSUMED_LOOKBACK_DAYS = 7
FEED_SEED_CONSUMED_LIMIT = 20
FEED_HISTORY_SANITIZED_CONSUMED_LIMIT = 8
RECENT_FEED_INTEREST_HISTORY_LIMIT = 5
RECENT_FEED_INTEREST_LOG_SCAN_LIMIT = 20
RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS = 48
RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT = 5
RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT = 20
FEED_SCAN_BODY_PREVIEW_CHARS = 300
MENTION_HANDLE_RE = re.compile(
    r"(?<![A-Za-z0-9_.])@([a-z0-9_]{2,40})(?=$|[^A-Za-z0-9_.]|\.(?=$|[^A-Za-z0-9_]))"
)


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
REPORT_HIDDEN_TITLE = "숨김 처리된 글"
REPORT_HIDDEN_MESSAGE = "신고 누적으로 숨김 처리된 글입니다."
FEED_HISTORY_STYLE_MARKER_RE = re.compile(
    r"(냐하하|푸훽|ㅋㅋ+|ㅎㅎ+|하하하?|헤헤|히히|후훗|우효|앗싸)",
    re.IGNORECASE,
)


class CommunityServiceError(Exception):
    pass


class PostNotFoundError(CommunityServiceError):
    pass


class CharacterNotFoundError(CommunityServiceError):
    pass


class AgentRunAuthorizationError(CommunityServiceError):
    pass


class PostWorldScopeError(CommunityServiceError):
    pass


def _reject_complete_tick(
    db: Session,
    *,
    run: models.AgentRun,
    message: str,
    target_post_id: str | None = None,
) -> None:
    try:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="complete_tick_rejected",
            target_post_id=target_post_id or run.post_id,
            reason="agent_tool_complete_tick_rejected",
            result=message[:1000],
        )
    except Exception:
        logger.exception(
            "complete_tick_rejection_log_failed character_id=%s run_id=%s",
            run.character_id,
            run.id,
        )
    raise AgentRunAuthorizationError(message)


def _clip_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_topic_text(value: object, limit: int = 300) -> str:
    return _clip_text(neutralize_context_text(str(value or "")), limit)


def _safe_feed_history_post_id(value: object) -> str:
    return _clip_text(neutralize_context_text(str(value or "")).strip(), 64)


def _body_preview(value: str | None) -> str:
    return _safe_topic_text(value, FEED_SCAN_BODY_PREVIEW_CHARS)


def _fallback_topic_signature(*, title: str | None, body: str | None) -> str:
    title_text = _safe_topic_text(title, 120)
    body_text = _body_preview(body)
    if title_text and body_text:
        return _clip_text(f"{title_text} / {body_text}", 300)
    return _clip_text(title_text or body_text, 300)


def _topic_metadata_from_result(value: str | None) -> dict[str, str]:
    payload = _json_object(value)
    topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
    novelty_basis = _safe_topic_text(payload.get("novelty_basis"), 500)
    return {
        "topic_signature": topic_signature,
        "novelty_basis": novelty_basis,
    }


def _topic_metadata_from_post_columns(post: models.Post | None) -> dict[str, str]:
    if post is None:
        return {"topic_signature": "", "novelty_basis": ""}
    return {
        "topic_signature": _safe_topic_text(
            getattr(post, "topic_signature", None), 300
        ),
        "novelty_basis": _safe_topic_text(getattr(post, "novelty_basis", None), 500),
    }


def _store_post_topic_metadata(
    db: Session,
    *,
    post_id: str,
    topic_signature: str | None,
    novelty_basis: str | None,
) -> None:
    topic = _safe_topic_text(topic_signature, 300)
    novelty = _safe_topic_text(novelty_basis, 500)
    if not topic and not novelty:
        return
    post = db.get(models.Post, post_id)
    if post is None:
        return
    post.topic_signature = topic or None
    post.novelty_basis = novelty or None
    post.search_document = build_post_search_document(
        title=post.title,
        body=post.body,
        topic_signature=post.topic_signature,
    )
    db.add(post)
    unit_of_work.finish_write(db, post)


def activity_result_text_for_prompt(
    result: str | None, reason: str | None = None
) -> str:
    payload = _json_object(result)
    if payload:
        message = _safe_topic_text(payload.get("message"), 500)
        if message:
            return message
    return result or reason or "-"


def build_post_created_activity_result(
    *,
    post_id: str,
    title: str | None,
    body: str | None,
    topic_signature: str | None = None,
    novelty_basis: str | None = None,
    lore_chunk_ids: list[str] | None = None,
    retrieval_mode: str | None = None,
    lore_query_mode: str | None = None,
    message: str | None = None,
) -> str:
    topic = _safe_topic_text(topic_signature, 300) or _fallback_topic_signature(
        title=title, body=body
    )
    payload: dict[str, Any] = {
        "message": message or f"Created post {post_id}.",
        "created_post_id": post_id,
        "topic_signature": topic,
    }
    novelty = _safe_topic_text(novelty_basis, 500)
    if novelty:
        payload["novelty_basis"] = novelty
    clean_lore_ids = [
        item.strip()
        for item in (lore_chunk_ids or [])
        if isinstance(item, str) and item.strip()
    ]
    if clean_lore_ids:
        payload["lore_chunk_ids"] = clean_lore_ids[:5]
    clean_retrieval_mode = _safe_topic_text(retrieval_mode, 80)
    if clean_retrieval_mode:
        payload["retrieval_mode"] = clean_retrieval_mode
    clean_lore_query_mode = _safe_topic_text(lore_query_mode, 80)
    if clean_lore_query_mode:
        payload["lore_query_mode"] = clean_lore_query_mode
    return json.dumps(payload, ensure_ascii=False)[:4000]


def _feed_seed_consumed_cutoff(*, lookback_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=max(1, lookback_days))


def list_recent_feed_seed_consumed_logs(
    db: Session,
    *,
    character_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
    limit: int = FEED_SEED_CONSUMED_LIMIT,
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == FEED_SEED_CONSUMED_ACTION_TYPE,
                models.AgentActivityLog.target_post_id.is_not(None),
                models.AgentActivityLog.created_at
                >= _feed_seed_consumed_cutoff(lookback_days=lookback_days),
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(),
                models.AgentActivityLog.id.desc(),
            )
            .limit(max(1, limit))
        )
    )


def feed_seed_source_already_consumed(
    db: Session,
    *,
    character_id: str,
    source_post_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
) -> bool:
    return (
        db.scalar(
            select(models.AgentActivityLog.id)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == FEED_SEED_CONSUMED_ACTION_TYPE,
                models.AgentActivityLog.target_post_id == source_post_id,
                models.AgentActivityLog.created_at
                >= _feed_seed_consumed_cutoff(lookback_days=lookback_days),
            )
            .limit(1)
        )
        is not None
    )


def format_feed_seed_consumed_sources_for_prompt(
    db: Session, *, character_id: str
) -> str:
    logs = list_recent_feed_seed_consumed_logs(db, character_id=character_id)
    if not logs:
        return "- none"
    lines: list[str] = []
    for log in logs:
        source_post_id = log.target_post_id or "-"
        source_post = community_crud.get_post(db, source_post_id)
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


def list_recent_feed_interest_logs(
    db: Session,
    *,
    character_id: str,
    lookback_days: int = FEED_SEED_CONSUMED_LOOKBACK_DAYS,
    limit: int = RECENT_FEED_INTEREST_LOG_SCAN_LIMIT,
) -> list[models.AgentActivityLog]:
    return list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == "feed_interests_noted",
                models.AgentActivityLog.result.is_not(None),
                models.AgentActivityLog.created_at
                >= _feed_seed_consumed_cutoff(lookback_days=lookback_days),
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(),
                models.AgentActivityLog.id.desc(),
            )
            .limit(max(1, limit))
        )
    )


def _recent_feed_interest_post_is_eligible(
    db: Session, *, character_id: str, post: models.Post
) -> bool:
    if post.author_character_id == character_id:
        return False
    if post.reply_to_post_id is not None:
        return False
    if post.post_type != "post":
        return False
    return _is_post_public_context_visible(db, post)


def _latest_post_created_topic_metadata(
    db: Session, *, character_id: str | None, post_id: str
) -> dict[str, str]:
    if db is not None:
        column_metadata = _topic_metadata_from_post_columns(db.get(models.Post, post_id))
        if column_metadata["topic_signature"] or column_metadata["novelty_basis"]:
            return column_metadata
    if db is None or character_id is None:
        return {"topic_signature": "", "novelty_basis": ""}
    log = db.scalar(
        select(models.AgentActivityLog)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type == "post_created",
            models.AgentActivityLog.target_post_id == post_id,
            models.AgentActivityLog.result.is_not(None),
        )
        .order_by(
            models.AgentActivityLog.created_at.desc(),
            models.AgentActivityLog.id.desc(),
        )
        .limit(1)
    )
    if log is None:
        return {"topic_signature": "", "novelty_basis": ""}
    return _topic_metadata_from_result(log.result)


def _topic_metadata_for_post(
    db: Session, *, post: models.Post, character_id: str | None = None
) -> dict[str, str]:
    column_metadata = _topic_metadata_from_post_columns(post)
    if column_metadata["topic_signature"] or column_metadata["novelty_basis"]:
        return column_metadata
    return _latest_post_created_topic_metadata(
        db,
        character_id=character_id if character_id is not None else post.author_character_id,
        post_id=post.id,
    )


def post_topic_signature_for_prompt(db: Session, post: models.Post) -> str:
    metadata = _topic_metadata_for_post(db, post=post)
    return metadata["topic_signature"] or _fallback_topic_signature(
        title=post.title, body=post.body
    )


def format_recent_feed_interest_history_for_prompt(
    db: Session, *, character_id: str
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
        post = community_crud.get_post(db, post_id)
        if post is None or not _recent_feed_interest_post_is_eligible(
            db, character_id=character_id, post=post
        ):
            continue
        seen_post_ids.add(post_id)
        topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
        if not topic_signature:
            topic_signature = _fallback_topic_signature(
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
                    "  body_preview: " + (_body_preview(post.body) or "-"),
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
                            neutralize_context_text(str(payload.get("post_seed") or "")),
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
    db: Session, *, character_id: str
) -> str:
    cutoff = datetime.now(UTC) - timedelta(
        hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS
    )
    posts = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.reply_to_post_id.is_(None),
                models.Post.post_type != "repost",
                models.Post.repost_of_post_id.is_(None),
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.created_at >= cutoff,
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT)
        )
    )
    if not posts:
        return "- none"
    lines: list[str] = []
    for post in posts:
        if not _is_post_public_context_visible(db, post):
            continue
        metadata = _topic_metadata_for_post(db, post=post, character_id=character_id)
        topic_signature = metadata["topic_signature"] or _fallback_topic_signature(
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
                    f"  body_preview: {_body_preview(post.body) or '-'}",
                ]
            )
        )
        if len(lines) >= RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT:
            break
    return "\n".join(lines) if lines else "- none"


def _feed_history_sanitize_skeleton_item(
    *,
    post_id: object,
    topic_signature: object,
    novelty_basis: object,
    source_title: object,
    summary_source: object,
    timestamp_label: str | None = None,
    timestamp_value: datetime | None = None,
) -> dict[str, str]:
    item = {
        "post_id": _safe_feed_history_post_id(post_id),
        "topic_signature": _safe_topic_text(topic_signature, 300),
        "novelty_basis": _safe_topic_text(novelty_basis, 500),
        "source_title": _clip_text(
            neutralize_context_text(str(source_title or "")), 160
        ),
        "summary_source": _clip_text(
            neutralize_context_text(str(summary_source or "")), 500
        ),
    }
    if timestamp_label and timestamp_value is not None:
        item[timestamp_label] = timestamp_value.isoformat()
    return item


def _build_consumed_sources_sanitize_skeleton(
    db: Session, *, character_id: str
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    logs = list_recent_feed_seed_consumed_logs(db, character_id=character_id)[
        :FEED_HISTORY_SANITIZED_CONSUMED_LIMIT
    ]
    for log in logs:
        source_post_id = _safe_feed_history_post_id(log.target_post_id)
        if not source_post_id:
            continue
        source_post = community_crud.get_post(db, source_post_id)
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
    db: Session, *, character_id: str
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
        post = community_crud.get_post(db, post_id)
        if post is None or not _recent_feed_interest_post_is_eligible(
            db, character_id=character_id, post=post
        ):
            continue
        seen_post_ids.add(post_id)
        topic_signature = _safe_topic_text(payload.get("topic_signature"), 300)
        if not topic_signature:
            topic_signature = _fallback_topic_signature(
                title=str(payload.get("post_seed") or ""),
                body=" / ".join(
                    [
                        str(first_interest.get("summary") or ""),
                        str(first_interest.get("reason") or ""),
                    ]
                ),
            )
        summary_source = " / ".join(
            item
            for item in [
                str(first_interest.get("summary") or "").strip(),
                str(first_interest.get("reason") or "").strip(),
                str(payload.get("review_reason") or "").strip(),
                str(payload.get("post_seed") or "").strip(),
            ]
            if item
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
    db: Session, *, character_id: str
) -> list[dict[str, str]]:
    cutoff = datetime.now(UTC) - timedelta(
        hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS
    )
    posts = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.reply_to_post_id.is_(None),
                models.Post.post_type != "repost",
                models.Post.repost_of_post_id.is_(None),
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.created_at >= cutoff,
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT)
        )
    )
    items: list[dict[str, str]] = []
    for post in posts:
        if not _is_post_public_context_visible(db, post):
            continue
        metadata = _topic_metadata_for_post(db, post=post, character_id=character_id)
        topic_signature = metadata["topic_signature"] or _fallback_topic_signature(
            title=post.title, body=post.body
        )
        items.append(
            _feed_history_sanitize_skeleton_item(
                post_id=post.id,
                topic_signature=topic_signature,
                novelty_basis=metadata["novelty_basis"],
                source_title=post.title,
                summary_source=_body_preview(post.body),
                timestamp_label="created_at",
                timestamp_value=post.created_at,
            )
        )
        if len(items) >= RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT:
            break
    return items


def build_feed_history_sanitize_skeleton(
    db: Session, *, character_id: str
) -> dict[str, list[dict[str, str]]]:
    return {
        "consumed_sources": _build_consumed_sources_sanitize_skeleton(
            db, character_id=character_id
        ),
        "recent_feed_interests": _build_recent_feed_interests_sanitize_skeleton(
            db, character_id=character_id
        ),
        "recent_own_root_topics": _build_recent_own_root_topics_sanitize_skeleton(
            db, character_id=character_id
        ),
    }


def _format_feed_history_sanitize_task_items(items: list[dict[str, str]]) -> str:
    if not items:
        return "- none"
    lines: list[str] = []
    for item in items:
        timestamp_lines = [
            f"  {key}: {item[key]}"
            for key in ("consumed_at", "interested_at", "created_at")
            if item.get(key)
        ]
        lines.append(
            "\n".join(
                [
                    f"- post_id: {item.get('post_id') or '-'}",
                    *timestamp_lines,
                    f"  locked_topic_signature: {item.get('topic_signature') or '-'}",
                    f"  locked_novelty_basis: {item.get('novelty_basis') or '-'}",
                    f"  locked_source_title: {item.get('source_title') or '-'}",
                    f"  text_to_sanitize: {item.get('summary_source') or '-'}",
                ]
            )
        )
    return "\n".join(lines)


def format_feed_history_sanitize_skeleton_for_prompt(
    skeleton: dict[str, list[dict[str, str]]] | None,
) -> dict[str, str]:
    source = skeleton if isinstance(skeleton, dict) else {}
    return {
        "consumed_seed_sources": _format_feed_history_sanitize_task_items(
            source.get("consumed_sources") or []
        ),
        "recent_feed_interest_history": _format_feed_history_sanitize_task_items(
            source.get("recent_feed_interests") or []
        ),
        "recent_own_root_topic_history": _format_feed_history_sanitize_task_items(
            source.get("recent_own_root_topics") or []
        ),
    }


def _clean_feed_history_summary(
    value: str | None, *, limit: int = 240
) -> tuple[str, list[str]]:
    text = neutralize_context_text(str(value or ""))
    warnings: list[str] = []
    if FEED_HISTORY_STYLE_MARKER_RE.search(text):
        warnings.append("style_marker_removed")
        text = FEED_HISTORY_STYLE_MARKER_RE.sub("", text)
    text = re.sub(r"\s*([!?~])\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -:;,.!?~")
    return _clip_text(text, limit), warnings


def _safe_feed_history_warnings(value: list[str]) -> list[str]:
    result: list[str] = []
    for item in value:
        warning = _clip_text(neutralize_context_text(str(item or "")), 80)
        if warning and warning not in result:
            result.append(warning)
        if len(result) >= 5:
            break
    return result


def _sanitize_feed_history_item(
    item: schemas.AgentFeedHistorySanitizeItem,
) -> dict[str, object]:
    warnings = _safe_feed_history_warnings(item.warnings)
    cleaned: dict[str, object] = {
        "topic_signature": _safe_topic_text(item.topic_signature, 300),
        "novelty_basis": _safe_topic_text(item.novelty_basis, 500),
        "source_title": _clip_text(neutralize_context_text(item.source_title), 160),
        "seed_semantic_summary": "",
        "own_root_semantic_summary": "",
        "interest_reason_summary": "",
        "warnings": warnings,
    }
    post_id = _safe_feed_history_post_id(item.post_id)
    if post_id:
        cleaned["post_id"] = post_id
    for key in (
        "seed_semantic_summary",
        "own_root_semantic_summary",
        "interest_reason_summary",
    ):
        value, found_warnings = _clean_feed_history_summary(
            getattr(item, key), limit=500
        )
        cleaned[key] = value
        for warning in found_warnings:
            if warning not in warnings:
                warnings.append(warning)
    cleaned["warnings"] = warnings[:5]
    return cleaned


def _feed_history_items_by_post_id(
    items: list[schemas.AgentFeedHistorySanitizeItem],
) -> dict[str, schemas.AgentFeedHistorySanitizeItem]:
    result: dict[str, schemas.AgentFeedHistorySanitizeItem] = {}
    for item in items:
        post_id = _safe_feed_history_post_id(item.post_id)
        if post_id and post_id not in result:
            result[post_id] = item
    return result


def _feed_history_metadata_only_summary(item: dict[str, str]) -> str:
    return _clip_text(
        " / ".join(
            value
            for value in [
                item.get("topic_signature") or "",
                item.get("novelty_basis") or "",
                item.get("source_title") or "",
            ]
            if value
        ),
        500,
    )


def _merge_feed_history_sanitize_group(
    *,
    skeleton_items: list[dict[str, str]],
    llm_items: list[schemas.AgentFeedHistorySanitizeItem],
    summary_key: str,
    limit: int,
) -> list[dict[str, object]]:
    llm_by_post_id = _feed_history_items_by_post_id(llm_items)
    result: list[dict[str, object]] = []
    for skeleton_item in skeleton_items[:limit]:
        post_id = _safe_feed_history_post_id(skeleton_item.get("post_id"))
        llm_item = llm_by_post_id.get(post_id)
        summary = (
            str(getattr(llm_item, summary_key) or "") if llm_item is not None else ""
        )
        if not summary:
            summary = _feed_history_metadata_only_summary(skeleton_item)
        warnings = llm_item.warnings if llm_item is not None else []
        merged_item = schemas.AgentFeedHistorySanitizeItem(
            post_id=post_id,
            topic_signature=skeleton_item.get("topic_signature") or "",
            novelty_basis=skeleton_item.get("novelty_basis") or "",
            source_title=skeleton_item.get("source_title") or "",
            seed_semantic_summary=(
                summary if summary_key == "seed_semantic_summary" else None
            ),
            own_root_semantic_summary=(
                summary if summary_key == "own_root_semantic_summary" else None
            ),
            interest_reason_summary=(
                summary if summary_key == "interest_reason_summary" else None
            ),
            warnings=warnings,
        )
        result.append(_sanitize_feed_history_item(merged_item))
    return result


def _feed_history_sanitize_skeleton_has_items(
    skeleton: dict[str, list[dict[str, str]]] | None,
) -> bool:
    if not isinstance(skeleton, dict):
        return False
    return any(
        bool(skeleton.get(key))
        for key in (
            "consumed_sources",
            "recent_feed_interests",
            "recent_own_root_topics",
        )
    )


def _merge_feed_history_sanitize_payload(
    *,
    skeleton: dict[str, list[dict[str, str]]],
    data: schemas.AgentFeedHistorySanitizeCreate,
) -> dict[str, list[dict[str, object]]]:
    return {
        "consumed_sources": _merge_feed_history_sanitize_group(
            skeleton_items=skeleton.get("consumed_sources") or [],
            llm_items=data.consumed_sources,
            summary_key="seed_semantic_summary",
            limit=FEED_HISTORY_SANITIZED_CONSUMED_LIMIT,
        ),
        "recent_feed_interests": _merge_feed_history_sanitize_group(
            skeleton_items=skeleton.get("recent_feed_interests") or [],
            llm_items=data.recent_feed_interests,
            summary_key="interest_reason_summary",
            limit=RECENT_FEED_INTEREST_HISTORY_LIMIT,
        ),
        "recent_own_root_topics": _merge_feed_history_sanitize_group(
            skeleton_items=skeleton.get("recent_own_root_topics") or [],
            llm_items=data.recent_own_root_topics,
            summary_key="own_root_semantic_summary",
            limit=RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT,
        ),
    }


def _format_sanitized_feed_history_items(
    items: list[dict[str, object]], *, summary_key: str
) -> str:
    if not items:
        return "- none"
    lines: list[str] = []
    for item in items:
        summary = _clip_text(
            neutralize_context_text(str(item.get(summary_key) or "")), 500
        )
        warnings = item.get("warnings")
        warning_text = (
            ", ".join(str(value) for value in warnings)
            if isinstance(warnings, list) and warnings
            else "-"
        )
        post_id = _safe_feed_history_post_id(item.get("post_id"))
        if post_id:
            item_lines = [
                f"- post_id: {post_id}",
                f"  topic_signature: {item.get('topic_signature') or '-'}",
                f"  novelty_basis: {item.get('novelty_basis') or '-'}",
                f"  source_title: {item.get('source_title') or '-'}",
                f"  semantic_summary: {summary or '-'}",
                f"  warnings: {warning_text}",
            ]
        else:
            item_lines = [
                f"- topic_signature: {item.get('topic_signature') or '-'}",
                f"  novelty_basis: {item.get('novelty_basis') or '-'}",
                f"  source_title: {item.get('source_title') or '-'}",
                f"  semantic_summary: {summary or '-'}",
                f"  warnings: {warning_text}",
            ]
        lines.append(
            "\n".join(item_lines)
        )
    return "\n".join(lines)


def _feed_history_payload_json(payload: dict[str, list[dict[str, object]]]) -> str:
    compact = {
        "consumed_sources": list(payload.get("consumed_sources") or []),
        "recent_feed_interests": list(payload.get("recent_feed_interests") or []),
        "recent_own_root_topics": list(payload.get("recent_own_root_topics") or []),
    }
    result = json.dumps(compact, ensure_ascii=False)
    while len(result) > 3800 and (
        compact["consumed_sources"]
        or compact["recent_feed_interests"]
        or compact["recent_own_root_topics"]
    ):
        if compact["consumed_sources"]:
            compact["consumed_sources"].pop()
        elif compact["recent_feed_interests"]:
            compact["recent_feed_interests"].pop()
        else:
            compact["recent_own_root_topics"].pop()
        result = json.dumps(compact, ensure_ascii=False)
    return result


def format_feed_history_sanitize_payload_for_prompt(
    payload: dict[str, Any] | None,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {
            "consumed_seed_sources": "- none",
            "recent_feed_interest_history": "- none",
            "recent_own_root_topic_history": "- none",
        }
    consumed_sources = payload.get("consumed_sources")
    recent_feed_interests = payload.get("recent_feed_interests")
    recent_own_root_topics = payload.get("recent_own_root_topics")
    return {
        "consumed_seed_sources": _format_sanitized_feed_history_items(
            consumed_sources if isinstance(consumed_sources, list) else [],
            summary_key="seed_semantic_summary",
        ),
        "recent_feed_interest_history": _format_sanitized_feed_history_items(
            recent_feed_interests if isinstance(recent_feed_interests, list) else [],
            summary_key="interest_reason_summary",
        ),
        "recent_own_root_topic_history": _format_sanitized_feed_history_items(
            recent_own_root_topics if isinstance(recent_own_root_topics, list) else [],
            summary_key="own_root_semantic_summary",
        ),
    }


def format_feed_history_metadata_fallback_for_prompt(
    db: Session, *, character_id: str
) -> dict[str, str]:
    return {
        "consumed_seed_sources": _format_consumed_sources_metadata_only(
            db, character_id=character_id
        ),
        "recent_feed_interest_history": _format_recent_feed_interests_metadata_only(
            db, character_id=character_id
        ),
        "recent_own_root_topic_history": _format_recent_own_roots_metadata_only(
            db, character_id=character_id
        ),
    }


def _format_consumed_sources_metadata_only(
    db: Session, *, character_id: str
) -> str:
    logs = list_recent_feed_seed_consumed_logs(db, character_id=character_id)[
        :FEED_HISTORY_SANITIZED_CONSUMED_LIMIT
    ]
    if not logs:
        return "- none"
    lines: list[str] = []
    for log in logs:
        source_post_id = log.target_post_id or "-"
        source_post = community_crud.get_post(db, source_post_id)
        source_title = source_post.title if source_post is not None else ""
        result_payload = _json_object(log.result)
        lines.append(
            "\n".join(
                [
                    f"- post_id: {source_post_id}",
                    f"  consumed_at: {log.created_at.isoformat()}",
                    f"  created_post_id: {result_payload.get('created_post_id') or '-'}",
                    "  topic_signature: "
                    + (_safe_topic_text(result_payload.get("topic_signature"), 300) or "-"),
                    "  novelty_basis: "
                    + (_safe_topic_text(result_payload.get("novelty_basis"), 300) or "-"),
                    "  source_title: "
                    + (_clip_text(neutralize_context_text(source_title), 120) or "-"),
                ]
            )
        )
    return "\n".join(lines)


def _format_recent_feed_interests_metadata_only(
    db: Session, *, character_id: str
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
        post = community_crud.get_post(db, post_id)
        if post is None or not _recent_feed_interest_post_is_eligible(
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
    db: Session, *, character_id: str
) -> str:
    cutoff = datetime.now(UTC) - timedelta(
        hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS
    )
    posts = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.reply_to_post_id.is_(None),
                models.Post.post_type != "repost",
                models.Post.repost_of_post_id.is_(None),
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.created_at >= cutoff,
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT)
        )
    )
    lines: list[str] = []
    for post in posts:
        if not _is_post_public_context_visible(db, post):
            continue
        metadata = _topic_metadata_for_post(db, post=post, character_id=character_id)
        topic_signature = metadata["topic_signature"] or _fallback_topic_signature(
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


def recent_own_root_topic_exists(
    db: Session, *, character_id: str, topic_signature: str | None
) -> bool:
    topic = _safe_topic_text(topic_signature, 300)
    if not topic or db is None:
        return False
    cutoff = datetime.now(UTC) - timedelta(
        hours=RECENT_OWN_ROOT_TOPIC_HISTORY_HOURS
    )
    posts = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.author_character_id == character_id,
                models.Post.reply_to_post_id.is_(None),
                models.Post.post_type != "repost",
                models.Post.repost_of_post_id.is_(None),
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.created_at >= cutoff,
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.desc())
            .limit(RECENT_OWN_ROOT_TOPIC_SCAN_LIMIT)
        )
    )
    for post in posts:
        if not _is_post_public_context_visible(db, post):
            continue
        metadata = _topic_metadata_for_post(db, post=post, character_id=character_id)
        existing_topic = metadata["topic_signature"] or _fallback_topic_signature(
            title=post.title, body=post.body
        )
        if _safe_topic_text(existing_topic, 300) == topic:
            return True
    return False


def _feed_seed_consumed_log_exists(
    db: Session, *, character_id: str, source_post_id: str
) -> bool:
    return (
        db.scalar(
            select(models.AgentActivityLog.id)
            .where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type == FEED_SEED_CONSUMED_ACTION_TYPE,
                models.AgentActivityLog.target_post_id == source_post_id,
            )
            .limit(1)
        )
        is not None
    )


def _extract_feed_seed_source_from_run(
    run: models.AgentRun,
) -> tuple[str, str, str, str] | None:
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    action_gate = gateway_result.get("action_gate")
    if not isinstance(action_gate, dict):
        return None
    prepared_brief = action_gate.get("prepared_create_post_brief")
    if not is_feed_scan_community_theme_brief(prepared_brief):
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
    return source_post_id, post_seed, topic_signature, novelty_basis


def maybe_log_feed_seed_consumed_for_created_post(
    db: Session, *, run: models.AgentRun, created_post_id: str
) -> models.AgentActivityLog | None:
    seed_source = _extract_feed_seed_source_from_run(run)
    if seed_source is None:
        return None
    source_post_id, post_seed, topic_signature, novelty_basis = seed_source
    if source_post_id == created_post_id:
        return None
    if _feed_seed_consumed_log_exists(
        db, character_id=run.character_id, source_post_id=source_post_id
    ):
        return None
    if community_crud.get_post(db, source_post_id) is None:
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
        return agent_crud.log_activity(
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


def _complete_tick_representative_target(
    current: str | None, candidate: str | None
) -> str | None:
    return current or candidate


class CharacterOwnershipError(CommunityServiceError):
    pass


class CharacterSuspendedError(CharacterOwnershipError):
    pass


class ProfileNotFoundError(CommunityServiceError):
    pass


class FollowSelfError(CommunityServiceError):
    pass


class NotificationNotFoundError(CommunityServiceError):
    pass


class LegacyCommentsDisabledError(CommunityServiceError):
    pass


class PostReportNotAllowedError(CommunityServiceError):
    pass


class CommunityRateLimitedError(CommunityServiceError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("Community action temporarily rate limited")


def _session_fingerprint(session_key: str) -> str:
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:12]


def _agent_tool_lookup_session_key(session_key: str) -> str:
    for marker in (":scratch:", ":run-main:"):
        if marker in session_key:
            return session_key.split(marker, 1)[0]
    return session_key


def _is_daypart_memory_session_key(session_key: str) -> bool:
    return ":resident-daypart:" in session_key


def _agent_tool_scratch_lane(session_key: str) -> str | None:
    marker = ":scratch:"
    if marker not in session_key:
        return None
    suffix = session_key.split(marker, 1)[1]
    lane = suffix.split(":", 1)[0].strip()
    return lane or None


def _clip_agent_context_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    text = neutralize_context_text(value).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _raise_agent_tool_authorization_error(
    *,
    action: str,
    reason: str,
    session_key: str,
    run,
    requested_post_id: str | None = None,
    requested_character_id: str | None = None,
) -> None:
    detail = (
        f"Agent run is not authorized for this {action} "
        f"(reason={reason}, session={_session_fingerprint(session_key)}, "
        f"requested_post={requested_post_id or '-'}, "
        f"requested_character={requested_character_id or '-'}, "
        f"run_id={getattr(run, 'id', '-') if run else '-'}, "
        f"run_status={getattr(run, 'status', '-') if run else '-'}, "
        f"run_post={getattr(run, 'post_id', '-') if run else '-'}, "
        f"run_character={getattr(run, 'character_id', '-') if run else '-'})"
    )
    logger.warning("agent tool authorization denied: %s", detail)
    raise AgentRunAuthorizationError(detail)


def list_posts(db: Session, *, limit: int = 20) -> list[schemas.PostSummary]:
    return list_feed(db, limit=limit, content="all").items


def list_feed(
    db: Session,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.FeedPage:
    posts, next_cursor = community_crud.list_timeline_posts(
        db, limit=_safe_limit(limit), cursor=cursor, content_filter=content
    )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def list_today_popular_posts(
    db: Session, *, limit: int = 2
) -> list[schemas.PostSummary]:
    day_start = _today_start_utc()
    posts = list(
        db.scalars(
            select(models.Post)
            .where(
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.reply_to_post_id.is_(None),
                models.Post.created_at >= day_start,
            )
            .order_by(models.Post.created_at.desc(), models.Post.id.asc())
        )
    )
    ranked_posts = [
        summary
        for summary in (
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        )
        if _post_reaction_score(summary) > 0
    ]
    safe_limit = max(1, min(limit, 10))
    return sorted(
        ranked_posts,
        key=lambda post: (-_post_reaction_score(post), post.created_at),
    )[:safe_limit]


def list_today_activity(db: Session, *, limit: int = 3) -> list[schemas.TodayActivityRead]:
    day_start = _today_start_utc()
    post_types = ("post_created", "quoted")
    reply_types = ("commented", "replied")
    like_types = ("liked",)

    rows = db.execute(
        select(
            models.Character.id,
            models.Character.name,
            models.Character.handle,
            models.Character.avatar_url,
            func.sum(
                case((models.AgentActivityLog.action_type.in_(post_types), 1), else_=0)
            ).label("post_count"),
            func.sum(
                case((models.AgentActivityLog.action_type.in_(reply_types), 1), else_=0)
            ).label("reply_count"),
            func.sum(
                case((models.AgentActivityLog.action_type.in_(like_types), 1), else_=0)
            ).label("like_count"),
        )
        .join(
            models.AgentActivityLog,
            models.AgentActivityLog.character_id == models.Character.id,
        )
        .where(models.AgentActivityLog.created_at >= day_start)
        .where(
            models.AgentActivityLog.action_type.not_in(
                agent_crud.HIDDEN_ACTIVITY_ACTION_TYPES
            )
        )
        .group_by(
            models.Character.id,
            models.Character.name,
            models.Character.handle,
            models.Character.avatar_url,
        )
    ).all()

    rankings = []
    for row in rows:
        post_count = int(row.post_count or 0)
        reply_count = int(row.reply_count or 0)
        like_count = int(row.like_count or 0)
        score = post_count * 3 + reply_count * 2 + like_count
        if score <= 0:
            continue
        rankings.append(
            schemas.TodayActivityRead(
                character_id=row.id,
                name=row.name,
                handle=row.handle,
                avatar_url=row.avatar_url,
                post_count=post_count,
                reply_count=reply_count,
                like_count=like_count,
                score=score,
            )
        )

    safe_limit = max(1, min(limit, 50))
    return sorted(rankings, key=lambda item: (-item.score, item.name))[:safe_limit]


def _today_start_utc() -> datetime:
    local_now = datetime.now(tz=agent_activity_policy.APP_TIMEZONE)
    return datetime.combine(
        local_now.date(), time.min, tzinfo=agent_activity_policy.APP_TIMEZONE
    ).astimezone(UTC)


def _post_reaction_score(post: schemas.PostSummary) -> int:
    return (
        post.like_count * 2
        + post.reply_count
        + post.repost_count * 2
        + post.quote_count * 2
    )


def search_nest(
    db: Session, *, query: str, limit: int = 20, offset: int = 0
) -> schemas.SearchResults:
    normalized_query = query.strip()
    if not normalized_query:
        return schemas.SearchResults(query="", posts=[], characters=[])
    safe_limit = _safe_limit(limit)
    safe_offset = max(0, offset)
    posts, posts_next_offset = community_crud.search_posts(
        db, normalized_query, limit=safe_limit, offset=safe_offset
    )
    characters, characters_next_offset = community_crud.search_characters(
        db, normalized_query, limit=safe_limit, offset=safe_offset
    )
    return schemas.SearchResults(
        query=normalized_query,
        posts=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        characters=[_character_search_result(character) for character in characters],
        posts_next_offset=posts_next_offset,
        characters_next_offset=characters_next_offset,
    )


def list_following_feed(
    db: Session,
    user: models.User,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.FeedPage:
    followed_user_ids, followed_character_ids = community_crud.get_followed_profiles_for_user(
        db, user.id
    )
    posts, next_cursor = community_crud.list_timeline_posts(
        db,
        limit=_safe_limit(limit),
        cursor=cursor,
        content_filter=content,
        followed_user_ids=followed_user_ids,
        followed_character_ids=followed_character_ids,
    )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def list_character_following_feed(
    db: Session,
    user: models.User,
    character_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.FeedPage:
    character = community_crud.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise CharacterNotFoundError(character_id)
    if character.owner_id != user.id:
        raise CharacterOwnershipError(
            f"user {user.id} cannot read following feed for character {character.id}"
        )
    followed_user_ids, followed_character_ids = (
        community_crud.get_followed_profiles_for_character(db, character.id)
    )
    posts, next_cursor = community_crud.list_timeline_posts(
        db,
        limit=_safe_limit(limit),
        cursor=cursor,
        content_filter=content,
        followed_user_ids=followed_user_ids,
        followed_character_ids=followed_character_ids,
    )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def get_post(db: Session, post_id: str) -> schemas.PostDetail:
    post = community_crud.get_post_including_report_hidden(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    if not _is_post_public_context_visible(db, post):
        return _hidden_post_detail(db, post)
    return _post_detail(db, post)


def get_post_thread(db: Session, post_id: str) -> schemas.PostThreadRead:
    post = community_crud.get_post_including_report_hidden(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    if not _is_post_public_context_visible(db, post):
        return schemas.PostThreadRead(post=_hidden_post_detail(db, post), replies=[])
    replies = community_crud.list_post_thread_replies(db, post_id)
    return schemas.PostThreadRead(
        post=_post_detail(db, post),
        replies=[
            _post_summary(db, reply)
            for reply in replies
            if _is_post_public_context_visible(db, reply)
        ],
    )


def report_post(
    db: Session, user: models.User, post_id: str, data: schemas.PostReportCreate
) -> schemas.PostReportRead:
    post = community_crud.get_post_including_report_hidden(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    if community_crud.is_report_hidden(post):
        raise PostNotFoundError(post_id)
    if _can_delete_post(db, user, post):
        raise PostReportNotAllowedError("cannot report your own post")
    try:
        community_abuse_quota.consume(
            db,
            user_id=user.id,
            action="report",
        )
    except community_abuse_quota.CommunityQuotaExceeded as exc:
        raise CommunityRateLimitedError(exc.retry_after_seconds) from exc

    _report, created = community_crud.create_post_report(
        db, post=post, reporter_user=user, data=data
    )
    if not created:
        return schemas.PostReportRead(
            status="already_reported",
            already_reported=True,
            report_hidden=community_crud.is_report_hidden(post),
        )

    report_count = community_crud.count_post_reports(db, post.id)
    post.report_count = report_count
    db.commit()
    db.refresh(post)
    return schemas.PostReportRead(
        status="reported",
        already_reported=False,
        report_hidden=community_crud.is_report_hidden(post),
    )


def delete_post(db: Session, user: models.User, post_id: str) -> None:
    post = community_crud.get_post(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    if not _can_delete_post(db, user, post):
        raise CharacterOwnershipError(f"user {user.id} cannot delete post {post.id}")

    deleted_at = datetime.now(UTC)
    if post.post_type == "repost":
        community_crud.delete_repost_event_for_timeline_post(db, post=post)

    deleted_posts = community_crud.soft_delete_post_tree(
        db, post=post, deleted_at=deleted_at
    )
    index = 0
    while index < len(deleted_posts):
        deleted_post = deleted_posts[index]
        community_crud.delete_repost_events_for_post(db, post=deleted_post)
        timeline_reposts = community_crud.soft_delete_timeline_reposts_for_source(
            db, post=deleted_post, deleted_at=deleted_at
        )
        for timeline_repost in timeline_reposts:
            deleted_posts.extend(
                community_crud.soft_delete_post_tree(
                    db, post=timeline_repost, deleted_at=deleted_at
                )
            )
        index += 1

    from app.runtime.relationships import (
        sqlalchemy_social_event as social_event_runtime,
    )

    social_event_runtime.exclude_events_for_posts(
        db,
        post_ids=[deleted_post.id for deleted_post in deleted_posts],
        reason="source_deleted",
        invalidated_at=deleted_at,
    )
    db.commit()


def create_post(
    db: Session,
    user: models.User,
    data: schemas.PostCreate,
    *,
    log_manual_activity: bool = True,
    post_info: schemas.PostInfoMetadata | None = None,
    world_id: str | None = None,
    author_world_character_id: str | None = None,
) -> schemas.PostDetail:
    character = None
    if data.author_character_id:
        character = community_crud.get_character(db, data.author_character_id)
        if character is None or character.deleted_at is not None:
            raise CharacterNotFoundError(data.author_character_id)
        if character.owner_id != user.id:
            raise CharacterOwnershipError(
                f"user {user.id} cannot post as character {character.id}"
            )
        if character.moderation_status == "suspended":
            raise CharacterSuspendedError("character_suspended")
    if (world_id is None) != (author_world_character_id is None):
        raise PostWorldScopeError("world_scope_pair_required")
    if world_id is not None and author_world_character_id is not None:
        if character is None:
            raise PostWorldScopeError("world_scope_requires_character")
        world_character = db.get(models.WorldCharacter, author_world_character_id)
        if (
            world_character is None
            or world_character.world_id != world_id
            or world_character.character_id != character.id
            or world_character.status != "active"
        ):
            raise PostWorldScopeError("world_scope_invalid")
    post = community_crud.create_post(
        db,
        post_id=f"post-{uuid4().hex[:12]}",
        user=user,
        character=character,
        data=data,
        post_info=post_info,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
    )
    if character is not None and log_manual_activity:
        result = build_post_created_activity_result(
            post_id=post.id,
            title=post.title,
            body=post.body,
            message=f"Created post {post.id}.",
        )
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="post_created",
            target_post_id=post.id,
            reason="manual_post",
            result=result,
        )
    _notify_mentioned_characters(
        db,
        post=post,
        actor_user_id=user.id if character is None else None,
        actor_character_id=character.id if character else None,
    )
    return _post_detail(db, post)


def _timeline_world_scope(
    db: Session,
    *,
    target: models.Post,
    character: models.Character | None,
) -> tuple[str | None, str | None]:
    """Derive a timeline mutation's World from its canonical target.

    A scoped target must never trust a client supplied World id. The acting
    character must currently be active in the target World and its membership
    must still be active. Legacy unscoped targets remain unscoped until the
    canonical backfill is applied.
    """

    if target.world_id is None:
        return None, None
    if character is None:
        raise PostWorldScopeError("world_scope_requires_character")
    active_world = db.get(models.CharacterActiveWorld, character.id)
    if active_world is None:
        raise PostWorldScopeError("active_world_required")
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if (
        world_character is None
        or world_character.character_id != character.id
        or world_character.world_id != target.world_id
        or world_character.status != "active"
    ):
        raise PostWorldScopeError("target_world_not_active")
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != target.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
    ):
        raise PostWorldScopeError("world_membership_not_active")
    return target.world_id, world_character.id


def create_reply(
    db: Session,
    user: models.User,
    post_id: str,
    data: schemas.TimelineReplyCreate,
    *,
    activity_reason: str = "manual_reply",
    enforce_user_quota: bool = True,
) -> schemas.PostDetail:
    parent = community_crud.get_post(db, post_id)
    if parent is None or not _is_post_public_context_visible(db, parent):
        raise PostNotFoundError(post_id)
    if enforce_user_quota:
        try:
            community_abuse_quota.consume(
                db,
                user_id=user.id,
                action="reply",
            )
        except community_abuse_quota.CommunityQuotaExceeded as exc:
            raise CommunityRateLimitedError(exc.retry_after_seconds) from exc
    character = _resolve_author_character(db, user, data.author_character_id)
    world_id, author_world_character_id = _timeline_world_scope(
        db,
        target=parent,
        character=character,
    )
    reply = community_crud.create_timeline_post(
        db,
        post_id=f"post-{uuid4().hex[:12]}",
        user=user,
        character=character,
        title=_reply_title(parent.title),
        body=data.body,
        post_type="reply",
        reply_to_post_id=parent.id,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
    )
    if character is not None:
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="replied",
            target_post_id=parent.id,
            reason=activity_reason,
            result=f"Created reply {reply.id}.",
        )
    _notify_post_owner(
        db,
        notification_type="reply",
        post=parent,
        source_post_id=reply.id,
        actor_user_id=user.id if character is None else None,
        actor_character_id=character.id if character else None,
    )
    _notify_mentioned_characters(
        db,
        post=reply,
        actor_user_id=user.id if character is None else None,
        actor_character_id=character.id if character else None,
        skip_character_ids=[parent.author_character_id],
    )
    return _post_detail(db, reply)


def create_quote(
    db: Session,
    user: models.User,
    post_id: str,
    data: schemas.TimelineQuoteCreate,
    *,
    activity_reason: str = "manual_quote",
) -> schemas.PostDetail:
    quoted = community_crud.get_post(db, post_id)
    if quoted is None or not _is_post_public_context_visible(db, quoted):
        raise PostNotFoundError(post_id)
    character = _resolve_author_character(db, user, data.author_character_id)
    world_id, author_world_character_id = _timeline_world_scope(
        db,
        target=quoted,
        character=character,
    )
    quote = community_crud.create_timeline_post(
        db,
        post_id=f"post-{uuid4().hex[:12]}",
        user=user,
        character=character,
        title=(data.title or _quote_title(quoted.title)),
        body=data.body,
        post_type="quote",
        quote_post_id=quoted.id,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
    )
    if character is not None:
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="quoted",
            target_post_id=quoted.id,
            reason=activity_reason,
            result=f"Created quote {quote.id}.",
        )
    _notify_post_owner(
        db,
        notification_type="quote",
        post=quoted,
        source_post_id=quote.id,
        actor_user_id=user.id if character is None else None,
        actor_character_id=character.id if character else None,
    )
    _notify_mentioned_characters(
        db,
        post=quote,
        actor_user_id=user.id if character is None else None,
        actor_character_id=character.id if character else None,
        skip_character_ids=[quoted.author_character_id],
    )
    return _post_detail(db, quote)


def create_comment(
    db: Session, post_id: str, data: schemas.CommentCreate
) -> schemas.CommentRead:
    raise LegacyCommentsDisabledError(
        "Legacy comments are disabled. Use /posts/{post_id}/replies."
    )


def like_post(
    db: Session,
    user: models.User,
    post_id: str,
    data: schemas.PostLikeCreate,
    *,
    activity_reason: str = "manual_like",
) -> schemas.PostDetail:
    post = community_crud.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        raise PostNotFoundError(post_id)
    character = _resolve_author_character(db, user, data.character_id)
    _like, created = community_crud.like_post(
        db, post=post, user=user, character=character
    )
    if character is not None and created:
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="liked",
            target_post_id=post.id,
            reason=activity_reason,
            result=f"Liked post {post.id}.",
        )
    if created:
        _notify_post_owner(
            db,
            notification_type="like",
            post=post,
            source_post_id=None,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
        )
    return _post_detail(db, post)


def unlike_post(
    db: Session, user: models.User, post_id: str, data: schemas.PostLikeCreate
) -> schemas.PostDetail:
    post = community_crud.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        raise PostNotFoundError(post_id)
    character = _resolve_author_character(db, user, data.character_id)
    community_crud.unlike_post(db, post=post, user=user, character=character)
    return _post_detail(db, post)


def repost_post(
    db: Session,
    user: models.User,
    post_id: str,
    data: schemas.PostLikeCreate,
    *,
    activity_reason: str = "manual_repost",
) -> schemas.PostDetail:
    post = community_crud.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        raise PostNotFoundError(post_id)
    character = _resolve_author_character(db, user, data.character_id)
    world_id, author_world_character_id = _timeline_world_scope(
        db,
        target=post,
        character=character,
    )
    existing_timeline_repost = community_crud.get_timeline_repost(
        db, post=post, user=user, character=character
    )
    _repost, created = community_crud.create_repost(
        db, post=post, user=user, character=character
    )
    if existing_timeline_repost is not None:
        return _post_detail(db, existing_timeline_repost)
    timeline_repost = community_crud.create_timeline_post(
        db,
        post_id=f"post-{uuid4().hex[:12]}",
        user=user,
        character=character,
        title=f"Repost: {post.title}"[:160],
        body="",
        post_type="repost",
        repost_of_post_id=post.id,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
    )
    if character is not None and created:
        agent_crud.log_activity(
            db,
            user_id=user.id,
            character_id=character.id,
            action_type="reposted",
            target_post_id=post.id,
            reason=activity_reason,
            result=f"Reposted post {post.id} as {timeline_repost.id}.",
        )
    if created:
        _notify_post_owner(
            db,
            notification_type="repost",
            post=post,
            source_post_id=timeline_repost.id,
            actor_user_id=user.id if character is None else None,
            actor_character_id=character.id if character else None,
        )
    return _post_detail(db, timeline_repost)


def unrepost_post(
    db: Session, user: models.User, post_id: str, data: schemas.PostLikeCreate
) -> schemas.PostDetail:
    post = community_crud.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        raise PostNotFoundError(post_id)
    character = _resolve_author_character(db, user, data.character_id)
    community_crud.delete_repost(db, post=post, user=user, character=character)
    community_crud.delete_timeline_reposts(db, post=post, user=user, character=character)
    return _post_detail(db, post)


def follow_profile(
    db: Session, user: models.User, data: schemas.FollowCreate
) -> schemas.FollowRead:
    follower_user, follower_character = _resolve_follower(db, user, data)
    target_user, target_character = _resolve_target_profile(db, data.target_type, data.target_id)
    _ensure_not_self_follow(follower_user, follower_character, target_user, target_character)
    follow, created = community_crud.create_follow(
        db,
        follower_user=follower_user,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )
    if created:
        community_crud.create_notification(
            db,
            notification_type="follow",
            recipient_user_id=target_user.id if target_user else None,
            recipient_character_id=target_character.id if target_character else None,
            actor_user_id=follower_user.id if follower_user else None,
            actor_character_id=follower_character.id if follower_character else None,
        )
    return schemas.FollowRead(
        follower=_profile_ref(follower_user, follower_character),
        target=_profile_ref(target_user, target_character),
        created_at=follow.created_at,
    )


def get_follow_status(
    db: Session, user: models.User, data: schemas.FollowCreate
) -> schemas.FollowStatusRead:
    follower_user, follower_character = _resolve_follower(db, user, data)
    target_user, target_character = _resolve_target_profile(db, data.target_type, data.target_id)
    _ensure_not_self_follow(follower_user, follower_character, target_user, target_character)
    return schemas.FollowStatusRead(
        following=community_crud.profile_follow_exists(
            db,
            follower_user=follower_user,
            follower_character=follower_character,
            target_user=target_user,
            target_character=target_character,
        )
    )


def unfollow_profile(db: Session, user: models.User, data: schemas.FollowCreate) -> None:
    follower_user, follower_character = _resolve_follower(db, user, data)
    target_user, target_character = _resolve_target_profile(db, data.target_type, data.target_id)
    community_crud.delete_follow(
        db,
        follower_user=follower_user,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )


def get_user_profile(db: Session, user_id: str) -> schemas.ProfileRead:
    user = community_crud.get_user(db, user_id)
    if user is None:
        raise ProfileNotFoundError(user_id)
    return schemas.ProfileRead(
        profile=_profile_ref(user, None),
        post_count=community_crud.count_profile_posts(db, user_id=user.id),
        reply_count=community_crud.count_profile_replies(db, user_id=user.id),
        liked_post_count=community_crud.count_profile_likes(db, user_id=user.id),
        received_like_count=community_crud.count_profile_received_likes(db, user_id=user.id),
        follower_count=community_crud.count_profile_followers(db, user_id=user.id),
        user_follower_count=community_crud.count_profile_followers(
            db, user_id=user.id, follower_type="user"
        ),
        character_follower_count=community_crud.count_profile_followers(
            db, user_id=user.id, follower_type="character"
        ),
        following_count=community_crud.count_profile_following(db, user_id=user.id),
    )


def get_character_profile(db: Session, character_id: str) -> schemas.ProfileRead:
    character = community_crud.get_character(db, character_id)
    if character is None:
        raise ProfileNotFoundError(character_id)
    return schemas.ProfileRead(
        profile=_profile_ref(None, character),
        execution_mode=character.execution_mode,  # type: ignore[arg-type]
        post_count=community_crud.count_profile_posts(db, character_id=character.id),
        reply_count=community_crud.count_profile_replies(db, character_id=character.id),
        liked_post_count=community_crud.count_profile_likes(
            db, character_id=character.id
        ),
        received_like_count=community_crud.count_profile_received_likes(
            db, character_id=character.id
        ),
        follower_count=community_crud.count_profile_followers(db, character_id=character.id),
        user_follower_count=community_crud.count_profile_followers(
            db, character_id=character.id, follower_type="user"
        ),
        character_follower_count=community_crud.count_profile_followers(
            db, character_id=character.id, follower_type="character"
        ),
        following_count=community_crud.count_profile_following(
            db, character_id=character.id
        ),
        one_liner=character.one_liner,
    )


def get_user_profile_feed(
    db: Session,
    user_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    tab: str = "posts",
) -> schemas.FeedPage:
    if community_crud.get_user(db, user_id) is None:
        raise ProfileNotFoundError(user_id)
    safe_limit = _safe_limit(limit)
    if tab == "replies":
        posts, next_cursor = community_crud.list_profile_posts(
            db, limit=safe_limit, cursor=cursor, author_user_id=user_id, replies=True
        )
    elif tab == "likes":
        posts, next_cursor = community_crud.list_liked_profile_posts(
            db, limit=safe_limit, cursor=cursor, user_id=user_id
        )
    else:
        posts, next_cursor = community_crud.list_profile_posts(
            db, limit=safe_limit, cursor=cursor, author_user_id=user_id
        )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def get_character_profile_feed(
    db: Session,
    character_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    tab: str = "posts",
) -> schemas.FeedPage:
    if community_crud.get_character(db, character_id) is None:
        raise ProfileNotFoundError(character_id)
    safe_limit = _safe_limit(limit)
    if tab == "replies":
        posts, next_cursor = community_crud.list_profile_posts(
            db,
            limit=safe_limit,
            cursor=cursor,
            author_character_id=character_id,
            replies=True,
        )
    elif tab == "likes":
        posts, next_cursor = community_crud.list_liked_profile_posts(
            db, limit=safe_limit, cursor=cursor, character_id=character_id
        )
    else:
        posts, next_cursor = community_crud.list_profile_posts(
            db, limit=safe_limit, cursor=cursor, author_character_id=character_id
        )
    return schemas.FeedPage(
        items=[
            _post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def get_user_profile_connections(
    db: Session,
    user_id: str,
    *,
    tab: str = "following",
    limit: int = 10,
    cursor: str | None = None,
    viewer_user: models.User | None = None,
) -> schemas.ProfileListPage:
    if community_crud.get_user(db, user_id) is None:
        raise ProfileNotFoundError(user_id)
    return _profile_connections_page(
        db,
        user_id=user_id,
        tab=tab,
        limit=limit,
        cursor=cursor,
        viewer_user=viewer_user,
    )


def get_character_profile_connections(
    db: Session,
    character_id: str,
    *,
    tab: str = "following",
    limit: int = 10,
    cursor: str | None = None,
    viewer_user: models.User | None = None,
) -> schemas.ProfileListPage:
    if community_crud.get_character(db, character_id) is None:
        raise ProfileNotFoundError(character_id)
    return _profile_connections_page(
        db,
        character_id=character_id,
        tab=tab,
        limit=limit,
        cursor=cursor,
        viewer_user=viewer_user,
    )


def list_notifications(
    db: Session, user: models.User, *, limit: int = 50, cursor: str | None = None
) -> schemas.NotificationPage:
    notifications, next_cursor = community_crud.list_notifications(
        db, user=user, limit=max(1, min(limit, 100)), cursor=cursor
    )
    return schemas.NotificationPage(
        items=[_notification_read(db, item) for item in notifications],
        next_cursor=next_cursor,
    )


def mark_notification_read(
    db: Session, user: models.User, notification_id: int
) -> schemas.NotificationRead:
    notification = community_crud.get_notification_for_user(
        db, user=user, notification_id=notification_id
    )
    if notification is None:
        raise NotificationNotFoundError(notification_id)
    return _notification_read(db, community_crud.mark_notification_read(db, notification))


def list_notifications_for_character(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    limit: int = 50,
    cursor: str | None = None,
) -> schemas.NotificationPage:
    notifications, next_cursor = community_crud.list_notifications_for_agent_page(
        db,
        user_id=user_id,
        character_id=character_id,
        limit=max(1, min(limit, 100)),
        cursor=cursor,
    )
    return schemas.NotificationPage(
        items=[_notification_read(db, item) for item in notifications],
        next_cursor=next_cursor,
    )


def mark_character_notification_read(
    db: Session, *, user_id: str, character_id: str, notification_id: int
) -> schemas.NotificationRead:
    notification = community_crud.get_notification_for_agent(
        db, user_id=user_id, character_id=character_id, notification_id=notification_id
    )
    if notification is None:
        raise NotificationNotFoundError(notification_id)
    return _notification_read(db, community_crud.mark_notification_read(db, notification))


def create_agent_tool_comment(
    db: Session, session_key: str, post_id: str, data: schemas.CommentCreate
) -> schemas.CommentRead:
    raise LegacyCommentsDisabledError(
        "Legacy comments are disabled. Use /posts/{post_id}/replies."
    )


def create_agent_tool_post(
    db: Session,
    session_key: str,
    data: schemas.PostCreate,
    *,
    topic_signature: str | None = None,
    novelty_basis: str | None = None,
    lore_chunk_ids: list[str] | None = None,
    retrieval_mode: str | None = None,
    lore_query_mode: str | None = None,
    consume_pending_feed_cue: bool = False,
    feed_cue_id: int | None = None,
    world_id: str | None = None,
    author_world_character_id: str | None = None,
) -> schemas.PostDetail:
    lookup_session_key = _agent_tool_lookup_session_key(session_key)
    run = agent_run_crud.get_active_run_for_session(db, lookup_session_key)
    if run is None:
        latest_run = agent_run_crud.get_latest_run_for_session(db, lookup_session_key)
        _raise_agent_tool_authorization_error(
            action="post",
            reason="no_active_run",
            session_key=session_key,
            run=latest_run,
            requested_character_id=data.author_character_id,
        )
    author_character_id = data.author_character_id or run.character_id
    if run.character_id != author_character_id:
        _raise_agent_tool_authorization_error(
            action="post",
            reason="character_mismatch",
            session_key=session_key,
            run=run,
            requested_character_id=author_character_id,
        )
    user = db.get(models.User, run.user_id)
    if user is None:
        _raise_agent_tool_authorization_error(
            action="post",
            reason="user_missing",
            session_key=session_key,
            run=run,
            requested_character_id=author_character_id,
        )
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="post")
    post = create_post(
        db,
        user,
        schemas.PostCreate(
            title=data.title,
            body=data.body,
            author_character_id=author_character_id,
        ),
        log_manual_activity=False,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
    )
    result = build_post_created_activity_result(
        post_id=post.id,
        title=post.title,
        body=post.body,
        topic_signature=topic_signature,
        novelty_basis=novelty_basis,
        lore_chunk_ids=lore_chunk_ids,
        retrieval_mode=retrieval_mode,
        lore_query_mode=lore_query_mode,
        message=f"Created post {post.id}.",
    )
    topic_metadata = _topic_metadata_from_result(result)
    _store_post_topic_metadata(
        db,
        post_id=post.id,
        topic_signature=topic_metadata["topic_signature"],
        novelty_basis=topic_metadata["novelty_basis"],
    )
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="post_created",
        target_post_id=post.id,
        reason="agent_tool_post",
        result=result,
    )
    maybe_log_feed_seed_consumed_for_created_post(
        db, run=run, created_post_id=post.id
    )
    if consume_pending_feed_cue:
        cue = agent_crud.get_pending_feed_cue(db, run.character_id)
        if feed_cue_id is None or (cue is not None and cue.id == feed_cue_id):
            agent_crud.mark_pending_feed_cue_used(
                db, character_id=run.character_id, run_id=run.id, post_id=post.id
            )
    return post


def like_agent_tool_post(
    db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
) -> schemas.PostDetail:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="like",
        requested_post_id=post_id,
        requested_character_id=data.character_id,
    )
    character_id = _agent_tool_character_id(
        run,
        data.character_id,
        action="like",
        session_key=session_key,
        post_id=post_id,
    )
    user = _agent_tool_user(db, run, action="like", session_key=session_key)
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="like")
    if _character_already_liked_post(db, character_id=character_id, post_id=post_id):
        raise AgentRunAuthorizationError("like is already recorded for this post")
    return like_post(
        db,
        user,
        post_id,
        schemas.PostLikeCreate(character_id=character_id),
        activity_reason="agent_tool_like",
    )


def list_agent_tool_feed(
    db: Session, session_key: str, *, limit: int = 20, cursor: str | None = None
) -> schemas.AgentFeedPage:
    run = _get_agent_tool_run(db, session_key=session_key, action="list_feed")
    scratch_lane = _agent_tool_scratch_lane(session_key)
    effective_limit = (
        max(1, min(limit, 30))
        if scratch_lane == "feed-scan"
        else max(1, min(limit, 100))
    )
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="feed_viewed",
        target_post_id=run.post_id,
        reason="agent_tool_list_feed",
        result=f"Read feed limit={effective_limit}.",
    )
    if scratch_lane == "feed-scan":
        return _list_resident_feed_scan_page(
            db, run=run, limit=effective_limit, cursor=cursor
        )
    posts, next_cursor = community_crud.list_timeline_posts(
        db, limit=effective_limit, cursor=cursor
    )
    return schemas.AgentFeedPage(
        items=[
            _agent_feed_post_summary(db, post)
            for post in posts
            if _is_post_public_context_visible(db, post)
        ],
        next_cursor=next_cursor,
    )


def _character_already_liked_post(
    db: Session, *, character_id: str, post_id: str
) -> bool:
    return (
        db.scalar(
            select(models.PostLike.id)
            .where(
                models.PostLike.post_id == post_id,
                models.PostLike.character_id == character_id,
            )
            .limit(1)
        )
        is not None
    )


def _character_already_reposted_post(
    db: Session, *, character_id: str, post_id: str
) -> bool:
    return (
        db.scalar(
            select(models.PostRepost.id)
            .where(
                models.PostRepost.post_id == post_id,
                models.PostRepost.character_id == character_id,
            )
            .limit(1)
        )
        is not None
    )


def _character_already_following_profile(
    db: Session, *, character_id: str, target_type: str, target_id: str
) -> bool:
    follower_character = community_crud.get_character(db, character_id)
    target_user, target_character = _resolve_target_profile(db, target_type, target_id)
    return community_crud.profile_follow_exists(
        db,
        follower_user=None,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )


def _character_can_follow_profile_for_resident_scan(
    db: Session, *, character_id: str, target_type: str | None, target_id: str | None
) -> bool:
    if target_type is None or target_id is None:
        return False
    if target_type == "character":
        if target_id == character_id:
            return False
        target_character = community_crud.get_character(db, target_id)
        if target_character is None or target_character.deleted_at is not None:
            return False
        existing_follow_id = db.scalar(
            select(models.ProfileFollow.id)
            .where(
                models.ProfileFollow.follower_character_id == character_id,
                models.ProfileFollow.target_character_id == target_id,
            )
            .limit(1)
        )
        return existing_follow_id is None
    return False


def _character_can_reply_to_post_for_resident_scan(
    db: Session, *, character_id: str, post_id: str
) -> bool:
    post = community_crud.get_post(db, post_id)
    if (
        post is None
        or post.author_character_id == character_id
        or not _is_post_public_context_visible(db, post)
    ):
        return False
    try:
        root_post_id = _thread_root_post_id(db, post_id)
    except PostNotFoundError:
        return False
    reply_ids = _thread_reply_post_ids(db, root_post_id)
    if not reply_ids:
        return True
    existing_own_reply_id = db.scalar(
        select(models.Post.id)
        .where(
            models.Post.id.in_(reply_ids),
            models.Post.author_character_id == character_id,
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        .limit(1)
    )
    if existing_own_reply_id is None:
        return True
    return _is_direct_reply_to_character_post(
        db, post_id=post_id, character_id=character_id
    )


def _post_has_resident_feed_action(
    db: Session,
    *,
    post: models.Post,
    character_id: str,
    allowed_actions: set[str],
) -> bool:
    author_target_type = "character" if post.author_character_id else None
    author_target_id = post.author_character_id
    self_authored = post.author_character_id == character_id
    if (
        "like" in allowed_actions
        and not self_authored
        and not _character_already_liked_post(
            db, character_id=character_id, post_id=post.id
        )
    ):
        return True
    if "reply" in allowed_actions and _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=post.id
    ):
        return True
    if (
        "repost" in allowed_actions
        and not self_authored
        and not _character_already_reposted_post(
            db, character_id=character_id, post_id=post.id
        )
    ):
        return True
    if (
        "follow" in allowed_actions
        and _character_can_follow_profile_for_resident_scan(
            db,
            character_id=character_id,
            target_type=author_target_type,
            target_id=author_target_id,
        )
    ):
        return True
    return False


def resident_feed_action_affordance(
    db: Session,
    *,
    post: models.Post,
    character_id: str,
    allowed_actions: tuple[str, ...] | set[str],
) -> dict[str, object]:
    allowed = set(allowed_actions)
    available: list[str] = []
    blocked: dict[str, str] = {}
    targets: dict[str, dict[str, str]] = {}
    author_target_type = "character" if post.author_character_id else None
    author_target_id = post.author_character_id
    self_authored = post.author_character_id == character_id

    if "like" not in allowed:
        blocked["like"] = "policy_disabled"
    elif self_authored:
        blocked["like"] = "self_authored"
    elif _character_already_liked_post(db, character_id=character_id, post_id=post.id):
        blocked["like"] = "already_liked"
    else:
        available.append("like")
        targets["like"] = {"post_id": post.id}

    if "reply" not in allowed:
        blocked["reply"] = "policy_disabled"
    elif _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=post.id
    ):
        available.append("reply")
        targets["reply"] = {"post_id": post.id}
    else:
        blocked["reply"] = "reply_not_available"

    if "repost" not in allowed:
        blocked["repost"] = "policy_disabled"
    elif self_authored:
        blocked["repost"] = "self_authored"
    elif _character_already_reposted_post(
        db, character_id=character_id, post_id=post.id
    ):
        blocked["repost"] = "already_reposted"
    else:
        available.append("repost")
        targets["repost"] = {"post_id": post.id}

    if "follow" not in allowed:
        blocked["follow"] = "policy_disabled"
    elif _character_can_follow_profile_for_resident_scan(
        db,
        character_id=character_id,
        target_type=author_target_type,
        target_id=author_target_id,
    ):
        available.append("follow")
        targets["follow"] = {
            "target_type": author_target_type or "",
            "target_id": author_target_id or "",
        }
    else:
        blocked["follow"] = "follow_not_available"

    return {
        "available_actions": available,
        "blocked_actions": blocked,
        "action_targets": targets,
    }


def _list_resident_feed_scan_page(
    db: Session,
    *,
    run: models.AgentRun,
    limit: int,
    cursor: str | None = None,
) -> schemas.AgentFeedPage:
    allowed_actions = set(
        agent_activity_policy.build_activity_policy(
            db, character_id=run.character_id
        ).allowed_actions
    )
    items: list[models.Post] = []
    page_cursor = cursor
    last_scanned_id: str | None = cursor
    scanned = 0
    while len(items) < limit and scanned < 500:
        posts, next_cursor = community_crud.list_resident_scan_posts(
            db, limit=100, cursor=page_cursor
        )
        if not posts:
            break
        scanned += len(posts)
        for post in posts:
            last_scanned_id = post.id
            if _post_has_resident_feed_action(
                db,
                post=post,
                character_id=run.character_id,
                allowed_actions=allowed_actions,
            ):
                items.append(post)
                if len(items) >= limit:
                    break
        if next_cursor is None or len(items) >= limit:
            break
        page_cursor = next_cursor
    return schemas.AgentFeedPage(
        items=[_agent_feed_post_summary(db, post) for post in items],
        next_cursor=last_scanned_id if len(items) >= limit else None,
    )


def resident_inbox_action_affordance(
    db: Session,
    *,
    notification: models.Notification,
    character_id: str,
    allowed_actions: tuple[str, ...] | set[str],
) -> dict[str, object]:
    inbox_allowed = set(allowed_actions) - {"post", "repost", "unfollow", "observe"}
    source_post_id = notification.source_post_id or notification.post_id
    source = community_crud.get_post(db, source_post_id) if source_post_id else None
    actor_target_type, actor_target_id = _candidate_target_parts(
        user_id=notification.actor_user_id,
        character_id=notification.actor_character_id,
    )
    available: list[str] = []
    blocked: dict[str, str] = {}
    targets: dict[str, dict[str, str]] = {}

    if source is None or not _is_post_public_context_visible(db, source):
        return {
            "available_actions": [],
            "blocked_actions": {
                "like": "source_post_not_available",
                "reply": "source_post_not_available",
                "follow": "source_post_not_available",
            },
            "action_targets": {},
        }

    self_authored = source.author_character_id == character_id
    if "like" not in inbox_allowed:
        blocked["like"] = "policy_disabled"
    elif self_authored:
        blocked["like"] = "self_authored"
    elif _character_already_liked_post(
        db, character_id=character_id, post_id=source.id
    ):
        blocked["like"] = "already_liked"
    else:
        available.append("like")
        targets["like"] = {"post_id": source.id}

    if "reply" not in inbox_allowed:
        blocked["reply"] = "policy_disabled"
    elif _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=source.id
    ):
        available.append("reply")
        targets["reply"] = {"post_id": source.id}
    else:
        blocked["reply"] = "reply_not_available"

    if "follow" not in inbox_allowed:
        blocked["follow"] = "policy_disabled"
    elif _character_can_follow_profile_for_resident_scan(
        db,
        character_id=character_id,
        target_type=actor_target_type,
        target_id=actor_target_id,
    ):
        available.append("follow")
        targets["follow"] = {
            "target_type": actor_target_type or "",
            "target_id": actor_target_id or "",
        }
    else:
        blocked["follow"] = "follow_not_available"

    return {
        "available_actions": available,
        "blocked_actions": blocked,
        "action_targets": targets,
    }


def _notification_has_resident_inbox_action(
    db: Session,
    *,
    notification: models.Notification,
    character_id: str,
    allowed_actions: set[str],
) -> bool:
    source_post_id = notification.source_post_id or notification.post_id
    if source_post_id is None:
        return False
    source = community_crud.get_post(db, source_post_id)
    if source is None or not _is_post_public_context_visible(db, source):
        return False
    actor_target_type, actor_target_id = _candidate_target_parts(
        user_id=notification.actor_user_id,
        character_id=notification.actor_character_id,
    )
    self_authored = source.author_character_id == character_id
    if (
        "like" in allowed_actions
        and not self_authored
        and not _character_already_liked_post(
            db, character_id=character_id, post_id=source.id
        )
    ):
        return True
    if "reply" in allowed_actions and _character_can_reply_to_post_for_resident_scan(
        db, character_id=character_id, post_id=source.id
    ):
        return True
    if (
        "follow" in allowed_actions
        and _character_can_follow_profile_for_resident_scan(
            db,
            character_id=character_id,
            target_type=actor_target_type,
            target_id=actor_target_id,
        )
    ):
        return True
    return False


def _notification_source_is_public_context_visible(
    db: Session, notification: models.Notification
) -> bool:
    source_post_id = notification.source_post_id or notification.post_id
    if source_post_id is None:
        return False
    source = community_crud.get_post(db, source_post_id)
    return source is not None and _is_post_public_context_visible(db, source)


def list_resident_actionable_inbox_notifications(
    db: Session,
    *,
    character_id: str,
    allowed_actions: tuple[str, ...],
    limit: int = 10,
) -> list[models.Notification]:
    inbox_allowed = set(allowed_actions) - {"post", "repost", "unfollow", "observe"}
    candidates: list[models.Notification] = []
    per_type_limit = min(5, max(1, limit))
    scan_limit = max(10, min(per_type_limit * 5, 50))
    for notification_type in ("reply", "mention", "joint_activity_started"):
        notifications = community_crud.list_unread_notifications_for_character(
            db,
            character_id=character_id,
            notification_type=notification_type,
            limit=scan_limit,
        )
        added = 0
        for notification in notifications:
            if _notification_has_resident_inbox_action(
                db,
                notification=notification,
                character_id=character_id,
                allowed_actions=inbox_allowed,
            ):
                candidates.append(notification)
                added += 1
                if added >= per_type_limit:
                    break
    candidates.sort(
        key=lambda notification: (notification.created_at, notification.id),
        reverse=True,
    )
    return candidates[:limit]


def list_agent_tool_following_feed(
    db: Session, session_key: str, *, limit: int = 20, cursor: str | None = None
) -> schemas.FeedPage:
    run = _get_agent_tool_run(db, session_key=session_key, action="list_following_feed")
    followed_user_ids, followed_character_ids = (
        community_crud.get_followed_profiles_for_character(db, run.character_id)
    )
    posts, next_cursor = community_crud.list_timeline_posts(
        db,
        limit=_safe_limit(limit),
        cursor=cursor,
        followed_user_ids=followed_user_ids,
        followed_character_ids=followed_character_ids,
    )
    return _neutralize_feed_page_for_agent(
        schemas.FeedPage(
            items=[
                _post_summary(db, post)
                for post in posts
                if _is_post_public_context_visible(db, post)
            ],
            next_cursor=next_cursor,
        )
    )


def _neutralize_post_reference_for_agent(
    post: schemas.PostReference | None,
) -> schemas.PostReference | None:
    if post is None:
        return None
    return post.model_copy(
        update={
            "title": neutralize_context_text(post.title),
            "body": neutralize_context_text(post.body),
        }
    )


def _neutralize_post_summary_for_agent(
    post: schemas.PostSummary,
) -> schemas.PostSummary:
    return post.model_copy(
        update={
            "title": neutralize_context_text(post.title),
            "body": neutralize_context_text(post.body),
            "quoted_post": _neutralize_post_reference_for_agent(post.quoted_post),
            "reposted_post": _neutralize_post_reference_for_agent(post.reposted_post),
        }
    )


def _neutralize_post_detail_for_agent(post: schemas.PostDetail) -> schemas.PostDetail:
    return post.model_copy(
        update={
            "title": neutralize_context_text(post.title),
            "body": neutralize_context_text(post.body),
            "quoted_post": _neutralize_post_reference_for_agent(post.quoted_post),
            "reposted_post": _neutralize_post_reference_for_agent(post.reposted_post),
        }
    )


def _neutralize_post_thread_for_agent(
    thread: schemas.PostThreadRead,
) -> schemas.PostThreadRead:
    return schemas.PostThreadRead(
        post=_neutralize_post_detail_for_agent(thread.post),
        replies=[_neutralize_post_summary_for_agent(reply) for reply in thread.replies],
    )


def _neutralize_feed_page_for_agent(page: schemas.FeedPage) -> schemas.FeedPage:
    return schemas.FeedPage(
        items=[_neutralize_post_summary_for_agent(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def _agent_feed_post_summary(
    db: Session, post: models.Post
) -> schemas.AgentFeedPostSummary:
    author = _post_author_identity(db, post)
    return schemas.AgentFeedPostSummary(
        post_id=post.id,
        author=neutralize_context_text(author["name"] or "-"),
        created_at=post.created_at,
        topic_signature=post_topic_signature_for_prompt(db, post),
        title=_safe_topic_text(post.title, 120),
        body_preview=_body_preview(post.body),
    )


def get_agent_tool_post_thread(
    db: Session, session_key: str, post_id: str
) -> schemas.PostThreadRead:
    run = _get_agent_tool_run(
        db, session_key=session_key, action="get_thread", requested_post_id=post_id
    )
    post = community_crud.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        raise PostNotFoundError(post_id)
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="thread_viewed",
        target_post_id=_thread_root_post_id(db, post_id),
        reason="agent_tool_get_thread",
        result=f"Read thread {post_id}.",
    )
    return _neutralize_post_thread_for_agent(get_post_thread(db, post_id))


def reply_agent_tool_post(
    db: Session, session_key: str, post_id: str, data: schemas.TimelineReplyCreate
) -> schemas.PostDetail:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="reply",
        requested_post_id=post_id,
        requested_character_id=data.author_character_id,
    )
    character_id = _agent_tool_character_id(
        run,
        data.author_character_id,
        action="reply",
        session_key=session_key,
        post_id=post_id,
    )
    user = _agent_tool_user(db, run, action="reply", session_key=session_key)
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="reply")
    target_post = community_crud.get_post(db, post_id)
    if target_post is None or not _is_post_public_context_visible(db, target_post):
        raise PostNotFoundError(post_id)
    if target_post.author_character_id == character_id:
        raise AgentRunAuthorizationError(
            "reply target is self-authored. Reply to another character's post in the viewed thread instead."
        )
    _ensure_agent_can_reply_to_thread(db, post_id=post_id, character_id=character_id)
    return create_reply(
        db,
        user,
        post_id,
        schemas.TimelineReplyCreate(body=data.body, author_character_id=character_id),
        activity_reason="agent_tool_reply",
        enforce_user_quota=False,
    )


def quote_agent_tool_post(
    db: Session, session_key: str, post_id: str, data: schemas.TimelineQuoteCreate
) -> schemas.PostDetail:
    raise AgentRunAuthorizationError("Quote is disabled for agent activity")


def _ensure_agent_can_reply_to_thread(
    db: Session, *, post_id: str, character_id: str
) -> None:
    root_post_id = _thread_root_post_id(db, post_id)
    reply_ids = _thread_reply_post_ids(db, root_post_id)
    if not reply_ids:
        return

    existing_own_reply_id = db.scalar(
        select(models.Post.id)
        .where(
            models.Post.id.in_(reply_ids),
            models.Post.author_character_id == character_id,
            models.Post.deleted_at.is_(None),
            models.Post.report_hidden_at.is_(None),
        )
        .order_by(models.Post.created_at.asc(), models.Post.id.asc())
        .limit(1)
    )
    if existing_own_reply_id is None:
        return
    if _is_direct_reply_to_character_post(db, post_id=post_id, character_id=character_id):
        return

    raise AgentRunAuthorizationError(
        "이미 이 스레드에 대꾸를 남겼습니다. 직접 받은 새 대꾸는 inbox lane에서만 다시 검토합니다."
    )


def _is_direct_reply_to_character_post(
    db: Session, *, post_id: str, character_id: str
) -> bool:
    post = community_crud.get_post(db, post_id)
    if post is None or post.reply_to_post_id is None:
        return False
    parent = community_crud.get_post(db, post.reply_to_post_id)
    return parent is not None and parent.author_character_id == character_id


def _thread_root_post_id(db: Session, post_id: str) -> str:
    post = community_crud.get_post(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    seen = {post.id}
    while post.reply_to_post_id is not None:
        parent = community_crud.get_post(db, post.reply_to_post_id)
        if parent is None or parent.id in seen:
            break
        post = parent
        seen.add(post.id)
    return post.id


def _thread_reply_post_ids(db: Session, root_post_id: str) -> list[str]:
    seen = {root_post_id}
    reply_ids: list[str] = []
    frontier = [root_post_id]
    while frontier:
        children = list(
            db.scalars(
                select(models.Post.id).where(
                    models.Post.reply_to_post_id.in_(frontier),
                    models.Post.deleted_at.is_(None),
                    models.Post.report_hidden_at.is_(None),
                )
            )
        )
        next_frontier = [post_id for post_id in children if post_id not in seen]
        if not next_frontier:
            break
        seen.update(next_frontier)
        reply_ids.extend(next_frontier)
        frontier = next_frontier
    return reply_ids


def unlike_agent_tool_post(
    db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
) -> schemas.PostDetail:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="unlike",
        requested_post_id=post_id,
        requested_character_id=data.character_id,
    )
    character_id = _agent_tool_character_id(
        run,
        data.character_id,
        action="unlike",
        session_key=session_key,
        post_id=post_id,
    )
    user = _agent_tool_user(db, run, action="unlike", session_key=session_key)
    return unlike_post(
        db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
    )


def repost_agent_tool_post(
    db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
) -> schemas.PostDetail:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="repost",
        requested_post_id=post_id,
        requested_character_id=data.character_id,
    )
    character_id = _agent_tool_character_id(
        run,
        data.character_id,
        action="repost",
        session_key=session_key,
        post_id=post_id,
    )
    user = _agent_tool_user(db, run, action="repost", session_key=session_key)
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="repost")
    if _character_already_reposted_post(
        db, character_id=character_id, post_id=post_id
    ):
        raise AgentRunAuthorizationError("repost is already recorded for this post")
    return repost_post(
        db,
        user,
        post_id,
        schemas.PostLikeCreate(character_id=character_id),
        activity_reason="agent_tool_repost",
    )


def unrepost_agent_tool_post(
    db: Session, session_key: str, post_id: str, data: schemas.PostLikeCreate
) -> schemas.PostDetail:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="unrepost",
        requested_post_id=post_id,
        requested_character_id=data.character_id,
    )
    character_id = _agent_tool_character_id(
        run,
        data.character_id,
        action="unrepost",
        session_key=session_key,
        post_id=post_id,
    )
    user = _agent_tool_user(db, run, action="unrepost", session_key=session_key)
    return unrepost_post(
        db, user, post_id, schemas.PostLikeCreate(character_id=character_id)
    )


def follow_agent_tool_profile(
    db: Session, session_key: str, data: schemas.FollowCreate
) -> schemas.FollowRead:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="follow",
        requested_character_id=data.follower_character_id,
    )
    follower_character_id = _agent_tool_character_id(
        run,
        data.follower_character_id,
        action="follow",
        session_key=session_key,
    )
    user = _agent_tool_user(db, run, action="follow", session_key=session_key)
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="follow")
    follower_character = community_crud.get_character(db, follower_character_id)
    target_user, target_character = _resolve_target_profile(
        db, data.target_type, data.target_id
    )
    already_following = community_crud.profile_follow_exists(
        db,
        follower_user=None,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )
    if already_following:
        raise AgentRunAuthorizationError("follow is already recorded for this profile")
    follow = follow_profile(
        db,
        user,
        schemas.FollowCreate(
            target_type=data.target_type,
            target_id=data.target_id,
            follower_character_id=follower_character_id,
        ),
    )
    if not already_following:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="followed",
            target_post_id=None,
            reason="agent_tool_follow",
            result=f"Followed {data.target_type}:{data.target_id}.",
        )
    return follow


def unfollow_agent_tool_profile(
    db: Session, session_key: str, data: schemas.FollowCreate
) -> None:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="unfollow",
        requested_character_id=data.follower_character_id,
    )
    follower_character_id = _agent_tool_character_id(
        run,
        data.follower_character_id,
        action="unfollow",
        session_key=session_key,
    )
    user = _agent_tool_user(db, run, action="unfollow", session_key=session_key)
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="unfollow")
    unfollow_profile(
        db,
        user,
        schemas.FollowCreate(
            target_type=data.target_type,
            target_id=data.target_id,
            follower_character_id=follower_character_id,
        ),
    )
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="unfollowed",
        target_post_id=None,
        reason="agent_tool_unfollow",
        result=f"Unfollowed {data.target_type}:{data.target_id}.",
    )


def get_agent_tool_profile(
    db: Session, session_key: str, profile_type: str, profile_id: str
) -> schemas.ProfileRead:
    _get_agent_tool_run(db, session_key=session_key, action="get_profile")
    if profile_type == "user":
        return get_user_profile(db, profile_id)
    if profile_type == "character":
        return get_character_profile(db, profile_id)
    raise ProfileNotFoundError(profile_id)


def _log_inbox_notifications_provided(
    db: Session,
    *,
    run: models.AgentRun,
    session_key: str,
    notifications: list[models.Notification],
) -> None:
    payload = {
        "session_fingerprint": _session_fingerprint(session_key),
        "notification_ids": [notification.id for notification in notifications[:10]],
    }
    first = notifications[0] if notifications else None
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="inbox_notifications_provided",
        target_post_id=(first.source_post_id or first.post_id) if first else run.post_id,
        reason="agent_tool_get_notifications",
        result=json.dumps(payload, ensure_ascii=False)[:4000],
    )


def _latest_inbox_delivery_notification_ids(
    db: Session, *, run: models.AgentRun, session_key: str
) -> list[int]:
    fingerprint = _session_fingerprint(session_key)
    logs = list(
        db.scalars(
            select(models.AgentActivityLog)
            .where(
                models.AgentActivityLog.user_id == run.user_id,
                models.AgentActivityLog.character_id == run.character_id,
                models.AgentActivityLog.action_type == "inbox_notifications_provided",
                models.AgentActivityLog.created_at >= run.created_at,
            )
            .order_by(
                models.AgentActivityLog.created_at.desc(),
                models.AgentActivityLog.id.desc(),
            )
            .limit(5)
        )
    )
    for log in logs:
        try:
            payload = json.loads(log.result)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("session_fingerprint") != fingerprint:
            continue
        ids = payload.get("notification_ids")
        if not isinstance(ids, list):
            return []
        normalized: list[int] = []
        for item in ids[:10]:
            if isinstance(item, bool):
                continue
            try:
                normalized.append(int(item))
            except (TypeError, ValueError):
                continue
        return normalized
    return []


def _mark_provided_inbox_notifications_read(
    db: Session, *, run: models.AgentRun, session_key: str
) -> None:
    for notification_id in _latest_inbox_delivery_notification_ids(
        db, run=run, session_key=session_key
    ):
        notification = community_crud.get_notification_for_agent(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            notification_id=notification_id,
        )
        if (
            notification is not None
            and notification.notification_type == "reply"
            and notification.read_at is None
        ):
            community_crud.mark_notification_read(db, notification)


def list_agent_tool_notifications(
    db: Session, session_key: str, *, limit: int = 50
) -> list[schemas.NotificationRead]:
    run = _get_agent_tool_run(db, session_key=session_key, action="get_notifications")
    if _agent_tool_scratch_lane(session_key) == "inbox":
        policy = agent_activity_policy.build_activity_policy(
            db, character_id=run.character_id
        )
        notifications = list_resident_actionable_inbox_notifications(
            db,
            character_id=run.character_id,
            allowed_actions=policy.allowed_actions,
            limit=max(1, min(limit, 10)),
        )
        _log_inbox_notifications_provided(
            db, run=run, session_key=session_key, notifications=notifications
        )
        return [
            _compact_agent_notification_read(_notification_read(db, item))
            for item in notifications
        ]
    else:
        notifications = [
            item
            for item in community_crud.list_notifications_for_agent(
                db,
                user_id=run.user_id,
                character_id=run.character_id,
                limit=max(1, min(limit, 100)),
            )
            if _notification_source_is_public_context_visible(db, item)
        ]
    return [_notification_read(db, item) for item in notifications]


def mark_agent_tool_notification_read(
    db: Session, session_key: str, notification_id: int
) -> schemas.NotificationRead:
    run = _get_agent_tool_run(db, session_key=session_key, action="read_notification")
    notification = community_crud.get_notification_for_agent(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        notification_id=notification_id,
    )
    if notification is None or not _notification_source_is_public_context_visible(
        db, notification
    ):
        raise NotificationNotFoundError(notification_id)
    return _notification_read(db, community_crud.mark_notification_read(db, notification))


def note_agent_tool_feed_interests(
    db: Session, session_key: str, data: schemas.AgentFeedInterestsCreate
) -> schemas.AgentToolNoteRead:
    run = _get_agent_tool_run(db, session_key=session_key, action="note_feed_interests")
    interests: list[schemas.AgentFeedInterestItem] = []
    hidden_interest_count = 0
    warnings: list[str] = []
    for item in data.interests[:1]:
        post = community_crud.get_post(db, item.post_id)
        if post is None or not _is_post_public_context_visible(db, post):
            hidden_interest_count += 1
            continue
        interests.append(item)
    post_seed = data.post_seed or ""
    post_seed_intent = normalize_post_seed_intent(
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
        and post_seed_intent == "public_reaction"
    ):
        warnings.append("legacy_reaction_seed_not_writable")
    if (
        interests
        and (post_seed.strip() or post_seed_intent)
        and feed_seed_source_already_consumed(
            db,
            character_id=run.character_id,
            source_post_id=interests[0].post_id,
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
    db: Session, session_key: str, data: schemas.AgentFeedHistorySanitizeCreate
) -> schemas.AgentToolNoteRead:
    started_at = time_module.monotonic()
    session_key_hash = _diagnostic_hash(session_key)
    payload_bytes = _feed_history_sanitize_payload_bytes(data)
    logger.info(
        "feed_history_sanitize_tool_endpoint_started "
        "sessionKeyHash=%s consumedSourcesCount=%s recentFeedInterestsCount=%s "
        "recentOwnRootTopicsCount=%s requestPayloadBytes=%s",
        session_key_hash,
        len(data.consumed_sources),
        len(data.recent_feed_interests),
        len(data.recent_own_root_topics),
        payload_bytes,
    )
    run: Any | None = None
    try:
        run = _get_agent_tool_run(
            db, session_key=session_key, action="note_feed_history_sanitize"
        )
        skeleton = (
            build_feed_history_sanitize_skeleton(db, character_id=run.character_id)
            if db is not None
            else {}
        )
        if _feed_history_sanitize_skeleton_has_items(skeleton):
            payload = _merge_feed_history_sanitize_payload(
                skeleton=skeleton,
                data=data,
            )
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
            "feed_history_sanitize_tool_endpoint_finished "
            "sessionKeyHash=%s agentRunId=%s characterId=%s status=ok "
            "durationMs=%s resultBytes=%s",
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
            if isinstance(exc, AgentRunAuthorizationError)
            else "backend_exception"
        )
        logger.warning(
            "feed_history_sanitize_tool_endpoint_error "
            "sessionKeyHash=%s agentRunId=%s characterId=%s status=error "
            "durationMs=%s errorCategory=%s failureKind=%s",
            session_key_hash,
            getattr(run, "id", None),
            getattr(run, "character_id", None),
            _elapsed_ms(started_at),
            type(exc).__name__,
            failure_kind,
        )
        raise


def _single_post_id_hint(value: str | None) -> str | None:
    if value is None:
        return None
    post_id = value.strip()
    if not post_id:
        return None
    if "," in post_id or any(ch.isspace() for ch in post_id):
        return None
    return post_id


def _resolve_inbox_review_target_post_id(
    db: Session, *, run: models.AgentRun, data: schemas.AgentInboxReviewCreate
) -> tuple[str | None, str, list[str]]:
    warnings: list[str] = []
    raw_candidate_post_id = data.candidate_post_id or ""
    candidate_post_id = _single_post_id_hint(data.candidate_post_id)
    resolved_post_id: str | None = None

    if raw_candidate_post_id and candidate_post_id is None:
        warnings.append("candidate_post_id_invalid_format")

    if data.candidate_notification_id is not None:
        notification = community_crud.get_notification_for_agent(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            notification_id=data.candidate_notification_id,
        )
        if notification is None:
            warnings.append("candidate_notification_id_not_found")
        elif notification.notification_type != "reply":
            warnings.append("candidate_notification_id_not_reply")
        else:
            source_post_id = notification.source_post_id or notification.post_id
            source = community_crud.get_post(db, source_post_id) if source_post_id else None
            if source is not None and _is_post_public_context_visible(db, source):
                resolved_post_id = source_post_id
            else:
                warnings.append("candidate_notification_source_post_not_found")

    if candidate_post_id is not None:
        candidate = community_crud.get_post(db, candidate_post_id)
        if candidate is None or not _is_post_public_context_visible(db, candidate):
            warnings.append("candidate_post_id_not_found")
        elif resolved_post_id is None:
            resolved_post_id = candidate_post_id
        elif candidate_post_id != resolved_post_id:
            warnings.append("candidate_post_id_mismatch_used_notification_source")

    stored_candidate_post_id = resolved_post_id or ""
    return resolved_post_id or run.post_id, stored_candidate_post_id, warnings


def note_agent_tool_inbox_review(
    db: Session, session_key: str, data: schemas.AgentInboxReviewCreate
) -> schemas.AgentToolNoteRead:
    run = _get_agent_tool_run(db, session_key=session_key, action="note_inbox_review")
    target_post_id, stored_candidate_post_id, warnings = _resolve_inbox_review_target_post_id(
        db, run=run, data=data
    )
    payload = {
        "notification_ids": data.notification_ids[:10],
        "reviewed_thread_ids": data.reviewed_thread_ids[:5],
        "response_plan": data.response_plan or "",
        "no_public_response_reason": data.no_public_response_reason or "",
        "candidate_notification_id": data.candidate_notification_id,
        "candidate_post_id": stored_candidate_post_id,
        "candidate_summary": data.candidate_summary or "",
        "candidate_reason": data.candidate_reason or "",
        "reply_context": data.reply_context or "",
    }
    if warnings:
        payload["warnings"] = warnings
    result = json.dumps(payload, ensure_ascii=False)
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="inbox_reviewed",
        target_post_id=target_post_id,
        reason="agent_tool_note_inbox_review",
        result=result[:4000],
    )
    if _agent_tool_scratch_lane(session_key) == "inbox":
        _mark_provided_inbox_notifications_read(
            db, run=run, session_key=session_key
        )
    return schemas.AgentToolNoteRead(
        status="ok", action_type="inbox_reviewed", result=result
    )


def observe_agent_tool_community(
    db: Session, session_key: str, data: schemas.AgentObserveCreate
) -> schemas.AgentToolNoteRead:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="observe",
        requested_post_id=data.target_post_id,
    )
    _ensure_tick_action_allowed(db, session_key=session_key, run=run, action="observe")
    if data.target_post_id:
        target_post = community_crud.get_post(db, data.target_post_id)
        if target_post is None or not _is_post_public_context_visible(db, target_post):
            raise PostNotFoundError(data.target_post_id)
    result = data.summary
    if data.memory_hint:
        result = f"{result}\n메모 힌트: {data.memory_hint}"
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="observed",
        target_post_id=data.target_post_id or run.post_id,
        reason="agent_tool_observe",
        result=result[:2000],
    )
    return schemas.AgentToolNoteRead(
        status="ok", action_type="observed", result=result
    )


def _complete_tick_target_post(
    db: Session,
    *,
    run: models.AgentRun,
    action_type: str,
    post_id: str | None,
) -> models.Post:
    if not post_id:
        _reject_complete_tick(
            db,
            run=run,
            message=f"{action_type} requires post_id.",
            target_post_id=post_id,
        )
    post = community_crud.get_post(db, post_id)
    if (
        post is None
        or post.deleted_at is not None
        or not _is_post_public_context_visible(db, post)
    ):
        _reject_complete_tick(
            db,
            run=run,
            message=f"{action_type} target post was not found.",
            target_post_id=post_id,
        )
    return post


def _ensure_complete_tick_reply_target_is_not_self(
    db: Session, *, run: models.AgentRun, post: models.Post
) -> None:
    if post.author_character_id == run.character_id:
        _reject_complete_tick(
            db,
            run=run,
            message=(
                "reply target is self-authored. Reply to another character's "
                "post in the viewed thread instead."
            ),
            target_post_id=post.id,
        )


def _complete_tick_follow_status(
    db: Session,
    *,
    run: models.AgentRun,
    target_type: str | None,
    target_id: str | None,
    action_type: str,
) -> bool:
    if not target_type or not target_id:
        _reject_complete_tick(
            db,
            run=run,
            message=(
                f"{action_type} requires target_type and target_id. Use the exact "
                f"{action_type}_payload target_type/target_id shown in actionable_feed_candidates."
            ),
        )
    follower_character = community_crud.get_character(db, run.character_id)
    if follower_character is None or follower_character.deleted_at is not None:
        _reject_complete_tick(
            db,
            run=run,
            message=f"{action_type} follower character was not found.",
        )
    try:
        target_user, target_character = _resolve_target_profile(db, target_type, target_id)
        _ensure_not_self_follow(None, follower_character, target_user, target_character)
    except ProfileNotFoundError:
        _reject_complete_tick(
            db,
            run=run,
            message=(
                f"{action_type} target was not found. Use the exact "
                f"{action_type}_payload target_type/target_id shown in actionable_feed_candidates; "
                "do not mix user and character ids."
            ),
        )
    except FollowSelfError as exc:
        _reject_complete_tick(db, run=run, message=str(exc))
    return community_crud.profile_follow_exists(
        db,
        follower_user=None,
        follower_character=follower_character,
        target_user=target_user,
        target_character=target_character,
    )


def _resident_action_candidate_id(
    *,
    run_id: str,
    character_id: str,
    action_type: str,
    target_key: str,
) -> str:
    digest = hashlib.sha256(
        f"{run_id}:{character_id}:{action_type}:{target_key}".encode("utf-8")
    ).hexdigest()[:12]
    return f"cand_{action_type}_{digest}"


def _candidate_target_parts(
    *, user_id: str | None, character_id: str | None
) -> tuple[str | None, str | None]:
    if character_id:
        return "character", character_id
    return None, None


def _put_candidate_action(
    candidate_actions: dict[str, schemas.AgentCompleteTickAction],
    *,
    run: models.AgentRun,
    action_type: str,
    target_key: str,
    action: schemas.AgentCompleteTickAction,
) -> None:
    candidate_id = _resident_action_candidate_id(
        run_id=run.id,
        character_id=run.character_id,
        action_type=action_type,
        target_key=target_key,
    )
    candidate_actions.setdefault(candidate_id, action)


def _build_complete_tick_candidate_actions(
    db: Session,
    *,
    run: models.AgentRun,
    policy: agent_activity_policy.ActivityPolicy | None,
) -> dict[str, schemas.AgentCompleteTickAction]:
    allowed_actions = (
        policy.allowed_actions
        if policy is not None
        else ("like", "repost", "follow")
    )
    allowed = set(allowed_actions)
    candidate_actions: dict[str, schemas.AgentCompleteTickAction] = {}

    feed = list_feed(db, limit=50)
    for post in feed.items:
        self_authored = post.author_character_id == run.character_id
        if "like" in allowed and not _character_already_liked_post(
            db, character_id=run.character_id, post_id=post.id
        ):
            _put_candidate_action(
                candidate_actions,
                run=run,
                action_type="like",
                target_key=f"post:{post.id}",
                action=schemas.AgentCompleteTickAction(
                    action_type="like", post_id=post.id
                ),
            )
        if "repost" in allowed and not _character_already_reposted_post(
            db, character_id=run.character_id, post_id=post.id
        ):
            _put_candidate_action(
                candidate_actions,
                run=run,
                action_type="repost",
                target_key=f"post:{post.id}",
                action=schemas.AgentCompleteTickAction(
                    action_type="repost", post_id=post.id
                ),
            )
        target_type, target_id = _candidate_target_parts(
            user_id=post.author_user_id, character_id=post.author_character_id
        )
        if (
            "follow" in allowed
            and not self_authored
            and target_type is not None
            and target_id is not None
        ):
            try:
                already_following = _character_already_following_profile(
                    db,
                    character_id=run.character_id,
                    target_type=target_type,
                    target_id=target_id,
                )
            except ProfileNotFoundError:
                already_following = True
            if not already_following:
                _put_candidate_action(
                    candidate_actions,
                    run=run,
                    action_type="follow",
                    target_key=f"{target_type}:{target_id}",
                    action=schemas.AgentCompleteTickAction(
                        action_type="follow",
                        target_type=target_type,
                        target_id=target_id,
                    ),
                )

    if "follow" in allowed:
        notifications = list(
            db.scalars(
                select(models.Notification)
                .where(
                    models.Notification.recipient_character_id == run.character_id,
                    models.Notification.notification_type == "reply",
                    models.Notification.read_at.is_(None),
                )
                .order_by(
                    models.Notification.created_at.desc(),
                    models.Notification.id.desc(),
                )
                .limit(30)
            )
        )
        for notification in notifications:
            target_type, target_id = _candidate_target_parts(
                user_id=notification.actor_user_id,
                character_id=notification.actor_character_id,
            )
            if target_type is None or target_id is None:
                continue
            if target_type == "character" and target_id == run.character_id:
                continue
            try:
                already_following = _character_already_following_profile(
                    db,
                    character_id=run.character_id,
                    target_type=target_type,
                    target_id=target_id,
                )
            except ProfileNotFoundError:
                already_following = True
            if already_following:
                continue
            _put_candidate_action(
                candidate_actions,
                run=run,
                action_type="follow",
                target_key=f"{target_type}:{target_id}",
                action=schemas.AgentCompleteTickAction(
                    action_type="follow",
                    target_type=target_type,
                    target_id=target_id,
                ),
            )

    return candidate_actions


def _resolve_complete_tick_candidate_actions(
    db: Session,
    *,
    run: models.AgentRun,
    data: schemas.AgentCompleteTickCreate,
    policy: agent_activity_policy.ActivityPolicy | None,
) -> list[schemas.AgentCompleteTickAction]:
    candidate_ids = data.selected_candidate_ids
    if not candidate_ids:
        return []
    if len(set(candidate_ids)) != len(candidate_ids):
        _reject_complete_tick(
            db,
            run=run,
            message="selected_candidate_ids contains a duplicate candidate_id.",
        )
    candidate_actions = _build_complete_tick_candidate_actions(
        db, run=run, policy=policy
    )
    resolved: list[schemas.AgentCompleteTickAction] = []
    for candidate_id in candidate_ids:
        action = candidate_actions.get(candidate_id)
        if action is None:
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "selected_candidate_ids contains an unknown or no-longer-valid "
                    f"candidate_id: {candidate_id}"
                ),
            )
        resolved.append(action)
    return resolved


def _validate_complete_tick_decision_type(
    db: Session, *, run: models.AgentRun, data: schemas.AgentCompleteTickCreate
) -> None:
    decision_type = data.decision_type
    if decision_type is None:
        return
    if decision_type not in COMPLETE_TICK_DECISION_TYPES:
        _reject_complete_tick(
            db,
            run=run,
            message=f"Unknown resident tick decision_type: {decision_type}",
        )
    action_types = [action.action_type for action in data.actions]
    if decision_type == "existing_post_interaction":
        if any(action_type in {"create_post", "observe", "unfollow"} for action_type in action_types):
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "existing_post_interaction can only use selected_candidate_ids "
                    "and optional reply actions."
                ),
            )
        return
    if data.selected_candidate_ids:
        _reject_complete_tick(
            db,
            run=run,
            message=f"{decision_type} cannot include selected_candidate_ids.",
        )
    if decision_type == "create_post" and action_types != ["create_post"]:
        _reject_complete_tick(
            db,
            run=run,
            message="create_post decision_type requires exactly one create_post action.",
        )
    if decision_type == "observe" and action_types != ["observe"]:
        _reject_complete_tick(
            db,
            run=run,
            message="observe decision_type requires exactly one observe action.",
        )
    if decision_type == "relationship_review":
        data.relationship_review = True
        if any(action_type not in {"observe", "unfollow"} for action_type in action_types):
            _reject_complete_tick(
                db,
                run=run,
                message="relationship_review decision_type can only observe or unfollow.",
            )


def _validate_complete_tick_actions_before_execution(
    db: Session, *, run: models.AgentRun, data: schemas.AgentCompleteTickCreate
) -> None:
    seen_likes: set[str] = set()
    seen_reposts: set[str] = set()
    seen_follows: set[tuple[str, str]] = set()
    seen_unfollows: set[tuple[str, str]] = set()
    for action in data.actions:
        if action.action_type == "observe":
            continue
        if action.action_type == "create_post":
            if not action.title or not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="create_post requires title and body.",
                )
            continue
        if action.action_type == "reply":
            post = _complete_tick_target_post(
                db, run=run, action_type="reply", post_id=action.post_id
            )
            _ensure_complete_tick_reply_target_is_not_self(db, run=run, post=post)
            if not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply requires body.",
                    target_post_id=action.post_id,
                )
            if len(action.body) > 1000:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply body must be 1000 chars or less.",
                    target_post_id=action.post_id,
                )
            root_post_id = _thread_root_post_id(db, post.id)
            thread_viewed = db.scalar(
                select(models.AgentActivityLog.id)
                .where(
                    models.AgentActivityLog.character_id == run.character_id,
                    models.AgentActivityLog.action_type == "thread_viewed",
                    models.AgentActivityLog.target_post_id == root_post_id,
                    models.AgentActivityLog.created_at >= run.created_at,
                )
                .limit(1)
            )
            if thread_viewed is None:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "reply requires angmoo_get_post_thread before complete_tick. "
                        f"Call angmoo_get_post_thread({root_post_id}) first, then retry reply."
                    ),
                    target_post_id=root_post_id,
                )
            try:
                _ensure_agent_can_reply_to_thread(
                    db, post_id=action.post_id, character_id=run.character_id
                )
            except AgentRunAuthorizationError as exc:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=str(exc),
                    target_post_id=root_post_id,
                )
            continue
        if action.action_type == "like":
            post = _complete_tick_target_post(
                db, run=run, action_type="like", post_id=action.post_id
            )
            if post.id in seen_likes:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="like is duplicated for this post in the same complete_tick payload.",
                    target_post_id=post.id,
                )
            seen_likes.add(post.id)
            if _character_already_liked_post(
                db, character_id=run.character_id, post_id=post.id
            ):
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "like is blocked for this post: already_liked. "
                        "Do not retry like for this same post_id in this tick."
                    ),
                    target_post_id=post.id,
                )
            continue
        if action.action_type == "repost":
            post = _complete_tick_target_post(
                db, run=run, action_type="repost", post_id=action.post_id
            )
            if post.id in seen_reposts:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="repost is duplicated for this post in the same complete_tick payload.",
                    target_post_id=post.id,
                )
            seen_reposts.add(post.id)
            if _character_already_reposted_post(
                db, character_id=run.character_id, post_id=post.id
            ):
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "repost is blocked for this post: already_reposted. "
                        "Do not retry repost for this same post_id in this tick."
                    ),
                    target_post_id=post.id,
                )
            continue
        if action.action_type == "follow":
            key = (action.target_type or "", action.target_id or "")
            if key in seen_follows:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="follow is duplicated for this target in the same complete_tick payload.",
                )
            seen_follows.add(key)
            already_following = _complete_tick_follow_status(
                db,
                run=run,
                target_type=action.target_type,
                target_id=action.target_id,
                action_type="follow",
            )
            if already_following:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow is blocked for this profile: already_following. "
                        "Do not retry follow for this same target_type/target_id in this tick."
                    ),
                )
            continue
        if action.action_type == "unfollow":
            key = (action.target_type or "", action.target_id or "")
            if key in seen_unfollows:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="unfollow is duplicated for this target in the same complete_tick payload.",
                )
            seen_unfollows.add(key)
            already_following = _complete_tick_follow_status(
                db,
                run=run,
                target_type=action.target_type,
                target_id=action.target_id,
                action_type="unfollow",
            )
            if not already_following:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="unfollow is blocked for this profile: not_following.",
                )


def complete_agent_tool_tick(
    db: Session, session_key: str, data: schemas.AgentCompleteTickCreate
) -> schemas.AgentCompleteTickRead:
    run = _get_agent_tool_run(db, session_key=session_key, action="complete_tick")
    _agent_tool_user(db, run, action="complete_tick", session_key=session_key)
    policy: agent_activity_policy.ActivityPolicy | None = None
    policy_enforced = agent_activity_policy.is_policy_enforced_session(run.session_key)
    if policy_enforced:
        policy = agent_activity_policy.build_activity_policy(
            db,
            character_id=run.character_id,
            ignore_active_hours=agent_activity_policy.is_manual_policy_session(
                run.session_key
            ),
        )
        raw_candidate_actions = [
            action.action_type
            for action in data.actions
            if action.action_type in COMPLETE_TICK_CANDIDATE_ACTION_TYPES
        ]
        if raw_candidate_actions:
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "Resident ticks must submit like/repost/follow through "
                    "selected_candidate_ids, not raw action objects."
                ),
            )
        resolved_candidate_actions = _resolve_complete_tick_candidate_actions(
            db, run=run, data=data, policy=policy
        )
        if resolved_candidate_actions:
            data.actions = [*resolved_candidate_actions, *data.actions]
        if len(data.actions) > 4:
            _reject_complete_tick(
                db,
                run=run,
                message="A resident tick can execute at most 4 actions total.",
            )
        _validate_complete_tick_decision_type(db, run=run, data=data)

    action_types = [action.action_type for action in data.actions]
    writing_actions = [
        action_type
        for action_type in action_types
        if action_type in {"create_post", "reply"}
    ]
    if len(writing_actions) > 1:
        _reject_complete_tick(
            db,
            run=run,
            message="A resident tick can write at most one create_post or reply action.",
        )
    if "create_post" in action_types and len(action_types) > 1:
        _reject_complete_tick(
            db,
            run=run,
            message="create_post must be the only action in a resident tick.",
        )
    if "observe" in action_types and len(action_types) > 1:
        _reject_complete_tick(
            db,
            run=run,
            message="observe cannot be combined with public actions.",
        )
    if "unfollow" in action_types and not data.relationship_review:
        _reject_complete_tick(
            db,
            run=run,
            message="unfollow is only allowed in a relationship review tick.",
        )
    if data.relationship_review and any(
        action_type not in {"observe", "unfollow"} for action_type in action_types
    ):
        _reject_complete_tick(
            db,
            run=run,
            message="relationship review ticks can only observe or unfollow.",
        )
    pending_cue = agent_crud.get_pending_feed_cue(db, run.character_id)
    if pending_cue is not None and action_types != ["create_post"]:
        _reject_complete_tick(
            db,
            run=run,
            message="A pending feed cue requires exactly one create_post action.",
        )
    if policy_enforced and policy is not None:
        for action_type in action_types:
            policy_action = COMPLETE_TICK_POLICY_ACTIONS.get(action_type)
            if policy_action is None:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        f"{action_type} is not a valid complete_tick action_type. "
                        "For a new post, use action_type=create_post; post is only an activity policy name."
                    ),
                )
            if policy_action in policy.allowed_actions:
                continue
            reason = policy.blocked_reasons.get(
                policy_action, "action is not allowed for this tick"
            )
            _reject_complete_tick(
                db,
                run=run,
                message=f"{action_type} is not allowed in this resident tick: {reason}",
            )
        if (
            not action_types
            and "observe" not in policy.allowed_actions
            and "post" in policy.allowed_actions
        ):
            _reject_complete_tick(
                db,
                run=run,
                message=(
                    "A resident tick with observe disabled and policy action post allowed "
                    "cannot finish without actions. If no existing-post reaction fits, "
                    "submit action_type=create_post as self_update_post or community_theme_post."
                ),
            )

    _validate_complete_tick_actions_before_execution(db, run=run, data=data)

    executed_actions: list[str] = []
    representative_target_post_id: str | None = None
    for action in data.actions:
        if action.action_type == "observe":
            executed_actions.append("observe")
            continue
        if action.action_type == "create_post":
            if not action.title or not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="create_post requires title and body.",
                )
            created = create_agent_tool_post(
                db,
                session_key,
                schemas.PostCreate(
                    title=action.title,
                    body=action.body,
                    author_character_id=run.character_id,
                ),
                consume_pending_feed_cue=pending_cue is not None,
                feed_cue_id=pending_cue.id if pending_cue is not None else None,
            )
            executed_actions.append(f"create_post:{created.id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, created.id
            )
            continue
        if action.action_type == "reply":
            if not action.post_id or not action.body:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply requires post_id and body.",
                    target_post_id=action.post_id,
                )
            if len(action.body) > 1000:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="reply body must be 1000 chars or less.",
                    target_post_id=action.post_id,
                )
            post = _complete_tick_target_post(
                db, run=run, action_type="reply", post_id=action.post_id
            )
            _ensure_complete_tick_reply_target_is_not_self(db, run=run, post=post)
            root_post_id = _thread_root_post_id(db, post.id)
            thread_viewed = db.scalar(
                select(models.AgentActivityLog.id)
                .where(
                    models.AgentActivityLog.character_id == run.character_id,
                    models.AgentActivityLog.action_type == "thread_viewed",
                    models.AgentActivityLog.target_post_id == root_post_id,
                    models.AgentActivityLog.created_at >= run.created_at,
                )
                .limit(1)
            )
            if thread_viewed is None:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "reply requires angmoo_get_post_thread before complete_tick. "
                        f"Call angmoo_get_post_thread({root_post_id}) first, then retry reply."
                    ),
                    target_post_id=root_post_id,
                )
            reply = reply_agent_tool_post(
                db,
                session_key,
                action.post_id,
                schemas.TimelineReplyCreate(
                    body=action.body,
                    author_character_id=run.character_id,
                ),
            )
            executed_actions.append(f"reply:{reply.id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, action.post_id
            )
            continue
        if action.action_type == "like":
            if not action.post_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="like requires post_id.",
                )
            already_liked = _character_already_liked_post(
                db, character_id=run.character_id, post_id=action.post_id
            )
            if already_liked:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "like is blocked for this post: already_liked. "
                        "Do not retry like for this same post_id in this tick."
                    ),
                    target_post_id=action.post_id,
                )
            like_agent_tool_post(
                db,
                session_key,
                action.post_id,
                schemas.PostLikeCreate(character_id=run.character_id),
            )
            executed_actions.append(f"like:{action.post_id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, action.post_id
            )
            continue
        if action.action_type == "repost":
            if not action.post_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="repost requires post_id.",
                )
            if _character_already_reposted_post(
                db, character_id=run.character_id, post_id=action.post_id
            ):
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "repost is blocked for this post: already_reposted. "
                        "Do not retry repost for this same post_id in this tick."
                    ),
                    target_post_id=action.post_id,
                )
            repost_agent_tool_post(
                db,
                session_key,
                action.post_id,
                schemas.PostLikeCreate(character_id=run.character_id),
            )
            executed_actions.append(f"repost:{action.post_id}")
            representative_target_post_id = _complete_tick_representative_target(
                representative_target_post_id, action.post_id
            )
            continue
        if action.action_type == "follow":
            if not action.target_type or not action.target_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow requires target_type and target_id. Resident ticks must "
                        "use selected_candidate_ids for follow; direct follow payloads are "
                        "only accepted outside resident candidate mode."
                    ),
                )
            already_following = False
            try:
                already_following = _character_already_following_profile(
                    db,
                    character_id=run.character_id,
                    target_type=action.target_type,
                    target_id=action.target_id,
                )
            except ProfileNotFoundError:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow target was not found. Use a backend candidate_id when "
                        "following during resident ticks; do not mix user and character ids."
                    ),
                )
            if already_following:
                _reject_complete_tick(
                    db,
                    run=run,
                    message=(
                        "follow is blocked for this profile: already_following. "
                        "Do not retry follow for this same target_type/target_id in this tick."
                    ),
                )
            follow_agent_tool_profile(
                db,
                session_key,
                schemas.FollowCreate(
                    target_type=action.target_type,
                    target_id=action.target_id,
                    follower_character_id=run.character_id,
                ),
            )
            executed_actions.append(f"follow:{action.target_type}:{action.target_id}")
            continue
        if action.action_type == "unfollow":
            if not action.target_type or not action.target_id:
                _reject_complete_tick(
                    db,
                    run=run,
                    message="unfollow requires target_type and target_id.",
                )
            unfollow_agent_tool_profile(
                db,
                session_key,
                schemas.FollowCreate(
                    target_type=action.target_type,
                    target_id=action.target_id,
                    follower_character_id=run.character_id,
                ),
            )
            executed_actions.append(f"unfollow:{action.target_type}:{action.target_id}")

    if (
        policy is not None
        and action_types
        and "observe" not in policy.allowed_actions
        and "post" in policy.allowed_actions
        and not _has_effective_complete_tick_action(executed_actions)
    ):
        _reject_complete_tick(
            db,
            run=run,
            message=(
                "A resident tick with observe disabled and policy action post allowed "
                "cannot finish with only skipped/no-op actions. Choose an available "
                "existing-post action or submit action_type=create_post."
            ),
        )

    handled_ids: list[int] = []
    for notification_id in dict.fromkeys(data.handled_notification_ids):
        notification = community_crud.get_notification_for_agent(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            notification_id=notification_id,
        )
        if notification is None:
            raise NotificationNotFoundError(notification_id)
        if not _notification_source_is_public_context_visible(db, notification):
            raise NotificationNotFoundError(notification_id)
        community_crud.mark_notification_read(db, notification)
        handled_ids.append(notification_id)

    state = save_agent_tool_character_state(
        db,
        session_key,
        run.character_id,
        schemas.CharacterStateWrite(
            mood=data.state.mood,
            summary=data.state.summary,
            memory_note=data.state.memory_note,
        ),
    )
    if data.relationship_review:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="relationship_reviewed",
            target_post_id=None,
            reason="agent_tool_complete_tick",
            result=data.selection_reason[:1000],
        )
    tick_target_post_id = representative_target_post_id
    if not executed_actions or executed_actions == ["observe"]:
        tick_target_post_id = run.post_id
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="tick_completed",
        target_post_id=tick_target_post_id,
        reason="agent_tool_complete_tick",
        result=(
            f"actions={','.join(executed_actions) or 'none'}; "
            f"handled_notifications={','.join(str(item) for item in handled_ids) or 'none'}; "
            f"selection_reason={data.selection_reason[:700]}"
        ),
    )
    return schemas.AgentCompleteTickRead(
        status="ok",
        executed_actions=executed_actions,
        handled_notification_ids=handled_ids,
        selection_reason=data.selection_reason,
        state=schemas.AgentTickStateRead.model_validate(state),
    )


def _has_effective_complete_tick_action(executed_actions: list[str]) -> bool:
    return any(
        not action.startswith(NOOP_COMPLETE_TICK_ACTION_PREFIXES)
        for action in executed_actions
    )


def save_character_state(
    db: Session, character_id: str, data: schemas.CharacterStateWrite
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state(db, character_id, data)
    except CharacterStateNotFoundError as exc:
        raise CharacterNotFoundError(str(exc)) from exc


def save_character_state_for_user(
    db: Session,
    user: models.User,
    character_id: str,
    data: schemas.CharacterStateWrite,
) -> schemas.CharacterStateRead:
    try:
        return character_state.save_character_state_for_user(db, user, character_id, data)
    except CharacterStateNotFoundError as exc:
        raise CharacterNotFoundError(str(exc)) from exc


def _normalize_state_memory_note(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_duplicate_memory_note(
    state: models.CharacterState | None, data: schemas.CharacterStateWrite
) -> bool:
    if state is None:
        return False
    incoming_note = _normalize_state_memory_note(data.memory_note)
    saved_note = _normalize_state_memory_note(state.memory_note)
    return bool(incoming_note and incoming_note == saved_note)


def _state_observation_note(data: schemas.CharacterStateWrite) -> str:
    note = getattr(data, "observation_note", None)
    return note.strip() if isinstance(note, str) else ""


def save_agent_tool_character_state(
    db: Session, session_key: str, character_id: str, data: schemas.CharacterStateWrite
) -> schemas.CharacterStateRead:
    run = _get_agent_tool_run(
        db,
        session_key=session_key,
        action="state",
        requested_character_id=character_id,
    )
    if run.character_id != character_id:
        _raise_agent_tool_authorization_error(
            action="state",
            reason="character_mismatch",
            session_key=session_key,
            run=run,
            requested_character_id=character_id,
        )
    existing_state = db.get(models.CharacterState, character_id)
    observation_note = _state_observation_note(data)
    if observation_note:
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="observation_note_saved",
            target_post_id=run.post_id,
            reason="agent_tool_state_observation_note",
            result=observation_note[:1000],
        )
    if _is_duplicate_memory_note(existing_state, data):
        agent_crud.log_activity(
            db,
            user_id=run.user_id,
            character_id=run.character_id,
            action_type="state_save_suppressed",
            target_post_id=run.post_id,
            reason="agent_tool_state_duplicate_memory_note",
            result="Suppressed duplicate memory_note state save.",
        )
        logger.info(
            "duplicate_state_save_suppressed character_id=%s run_id=%s session_key=%s",
            character_id,
            run.id,
            session_key,
        )
        return schemas.CharacterStateRead.model_validate(existing_state)
    state = save_character_state(db, character_id, data)
    agent_crud.log_activity(
        db,
        user_id=run.user_id,
        character_id=run.character_id,
        action_type="state_saved",
        target_post_id=run.post_id,
        reason="agent_tool_state",
        result=(
            f"Saved state mood={state.mood}; "
            f"summary={state.summary[:300]}; memory_note={state.memory_note[:700]}"
        ),
    )
    return state


def get_character_activity(
    db: Session, character_id: str
) -> schemas.CharacterActivityRead:
    character = community_crud.get_character(db, character_id)
    if character is None or character.deleted_at is not None:
        raise CharacterNotFoundError(character_id)

    return community_crud.get_character_activity(db, character)


def _get_agent_tool_run(
    db: Session,
    *,
    session_key: str,
    action: str,
    requested_post_id: str | None = None,
    requested_character_id: str | None = None,
) -> models.AgentRun:
    run = agent_run_crud.get_active_run_for_tool_auth_key(db, session_key)
    if run is not None:
        return run
    if _is_daypart_memory_session_key(session_key):
        _raise_agent_tool_authorization_error(
            action=action,
            reason="daypart_session_key_not_authorized",
            session_key=session_key,
            run=None,
            requested_post_id=requested_post_id,
            requested_character_id=requested_character_id,
        )
    lookup_session_key = _agent_tool_lookup_session_key(session_key)
    run = agent_run_crud.get_active_run_for_session(db, lookup_session_key)
    if run is None:
        latest_run = (
            agent_run_crud.get_latest_run_for_tool_auth_key(db, session_key)
            or agent_run_crud.get_latest_run_for_session(db, lookup_session_key)
        )
        _raise_agent_tool_authorization_error(
            action=action,
            reason="no_active_run",
            session_key=session_key,
            run=latest_run,
            requested_post_id=requested_post_id,
            requested_character_id=requested_character_id,
        )
    return run


def _agent_tool_character_id(
    run: models.AgentRun,
    requested_character_id: str | None,
    *,
    action: str,
    session_key: str,
    post_id: str | None = None,
) -> str:
    character_id = requested_character_id or run.character_id
    if character_id != run.character_id:
        _raise_agent_tool_authorization_error(
            action=action,
            reason="character_mismatch",
            session_key=session_key,
            run=run,
            requested_post_id=post_id,
            requested_character_id=character_id,
        )
    return character_id


def _agent_tool_user(
    db: Session, run: models.AgentRun, *, action: str, session_key: str
) -> models.User:
    user = db.get(models.User, run.user_id)
    if user is None:
        _raise_agent_tool_authorization_error(
            action=action,
            reason="user_missing",
            session_key=session_key,
            run=run,
            requested_character_id=run.character_id,
        )
    return user


def _ensure_tick_action_allowed(
    db: Session, *, session_key: str, run: models.AgentRun, action: str
) -> None:
    try:
        agent_activity_policy.assert_action_allowed(db, run=run, action=action)
    except agent_activity_policy.ActivityPolicyDeniedError as exc:
        _raise_agent_tool_authorization_error(
            action=action,
            reason=str(exc),
            session_key=session_key,
            run=run,
            requested_post_id=run.post_id,
            requested_character_id=run.character_id,
        )


def _safe_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _resolve_author_character(
    db: Session, user: models.User, character_id: str | None
) -> models.Character | None:
    if character_id is None:
        return None
    character = community_crud.get_character(db, character_id)
    if character is None:
        raise CharacterNotFoundError(character_id)
    if character.deleted_at is not None:
        raise CharacterNotFoundError(character_id)
    if character.owner_id != user.id:
        raise CharacterOwnershipError(
            f"user {user.id} cannot act as character {character.id}"
        )
    if character.moderation_status == "suspended":
        raise CharacterSuspendedError("character_suspended")
    return character


def _reply_title(title: str) -> str:
    return f"Re: {title}"[:160]


def _quote_title(title: str) -> str:
    return f"Quote: {title}"[:160]


def _profile_ref(
    user: models.User | None, character: models.Character | None
) -> schemas.ProfileRef:
    if character is not None:
        if character.deleted_at is not None:
            return schemas.ProfileRef(
                profile_type="character",
                id=character.id,
                display_name=DELETED_CHARACTER_NAME,
                handle=None,
                avatar_url=None,
                banner_url=None,
            )
        return schemas.ProfileRef(
            profile_type="character",
            id=character.id,
            display_name=character.name,
            handle=character.handle,
            avatar_url=character.avatar_url,
            banner_url=character.banner_url,
        )
    if user is None:
        raise ProfileNotFoundError("profile")
    return schemas.ProfileRef(
        profile_type="user",
        id=user.id,
        display_name=user.display_name,
    )


def _profile_connections_page(
    db: Session,
    *,
    user_id: str | None = None,
    character_id: str | None = None,
    tab: str,
    limit: int,
    cursor: str | None,
    viewer_user: models.User | None,
) -> schemas.ProfileListPage:
    safe_limit = _safe_limit(limit)
    if tab == "character_followers":
        rows, next_cursor = community_crud.list_profile_followers(
            db,
            user_id=user_id,
            character_id=character_id,
            follower_type="character",
            limit=safe_limit,
            cursor=cursor,
        )
        items = [
            _profile_list_item(
                db,
                user_id=row.follower_user_id,
                character_id=row.follower_character_id,
                viewer_user=viewer_user,
            )
            for row in rows
        ]
    elif tab == "user_followers":
        rows, next_cursor = community_crud.list_profile_followers(
            db,
            user_id=user_id,
            character_id=character_id,
            follower_type="user",
            limit=safe_limit,
            cursor=cursor,
        )
        items = [
            _profile_list_item(
                db,
                user_id=row.follower_user_id,
                character_id=row.follower_character_id,
                viewer_user=viewer_user,
            )
            for row in rows
        ]
    else:
        rows, next_cursor = community_crud.list_profile_following(
            db,
            user_id=user_id,
            character_id=character_id,
            limit=safe_limit,
            cursor=cursor,
        )
        items = [
            _profile_list_item(
                db,
                user_id=row.target_user_id,
                character_id=row.target_character_id,
                viewer_user=viewer_user,
            )
            for row in rows
        ]
    return schemas.ProfileListPage(
        items=[item for item in items if item is not None],
        next_cursor=next_cursor,
    )


def _profile_list_item(
    db: Session,
    *,
    user_id: str | None,
    character_id: str | None,
    viewer_user: models.User | None,
) -> schemas.ProfileListItem | None:
    if character_id is not None:
        character = community_crud.get_character(db, character_id)
        if character is None or character.deleted_at is not None:
            return None
        return schemas.ProfileListItem(
            profile=_profile_ref(None, character),
            one_liner=character.one_liner,
            viewer_following=_viewer_follows_character(db, viewer_user, character),
        )
    if user_id is not None:
        user = community_crud.get_user(db, user_id)
        if user is None:
            return None
        return schemas.ProfileListItem(profile=_profile_ref(user, None))
    return None


def _viewer_follows_character(
    db: Session, viewer_user: models.User | None, character: models.Character
) -> bool:
    if viewer_user is None or character.deleted_at is not None:
        return False
    return community_crud.profile_follow_exists(
        db,
        follower_user=viewer_user,
        follower_character=None,
        target_user=None,
        target_character=character,
    )


def _character_search_result(
    character: models.Character,
) -> schemas.CharacterSearchResult:
    return schemas.CharacterSearchResult(
        id=character.id,
        name=character.name,
        handle=character.handle,
        avatar_url=character.avatar_url,
        banner_url=character.banner_url,
        one_liner=character.one_liner,
    )


def _notification_read(
    db: Session, notification: models.Notification
) -> schemas.NotificationRead:
    actor = _notification_actor_identity(db, notification)
    recipient = _notification_recipient_identity(db, notification)
    post_preview = _notification_post_preview(db, notification.post_id)
    source_post_preview = _notification_post_preview(db, notification.source_post_id)
    return schemas.NotificationRead.model_validate(
        {
            "id": notification.id,
            "notification_type": notification.notification_type,
            "post_id": notification.post_id,
            "source_post_id": notification.source_post_id,
            "actor_user_id": notification.actor_user_id,
            "actor_character_id": notification.actor_character_id,
            "recipient_user_id": notification.recipient_user_id,
            "recipient_character_id": notification.recipient_character_id,
            "data": notification.data,
            "actor_name": actor["name"],
            "actor_handle": actor["handle"],
            "actor_avatar_url": actor["avatar_url"],
            "recipient_name": recipient["name"],
            "recipient_handle": recipient["handle"],
            "recipient_avatar_url": recipient["avatar_url"],
            "post_title": post_preview["title"],
            "post_body": post_preview["body"],
            "source_post_title": source_post_preview["title"],
            "source_post_body": source_post_preview["body"],
            "read_at": notification.read_at,
            "created_at": notification.created_at,
        }
    )


def _compact_agent_notification_read(
    notification: schemas.NotificationRead,
) -> schemas.NotificationRead:
    return notification.model_copy(
        update={
            "post_title": _clip_agent_context_text(notification.post_title, 120),
            "post_body": _clip_agent_context_text(notification.post_body, 500),
            "source_post_title": _clip_agent_context_text(
                notification.source_post_title, 120
            ),
            "source_post_body": _clip_agent_context_text(
                notification.source_post_body, 500
            ),
            "data": _clip_agent_context_text(notification.data, 500),
        }
    )


def _notification_actor_identity(
    db: Session, notification: models.Notification
) -> dict[str, str | None]:
    if notification.actor_character_id:
        character = community_crud.get_character(db, notification.actor_character_id)
        if character is not None:
            if character.deleted_at is not None:
                return {
                    "name": DELETED_CHARACTER_NAME,
                    "handle": None,
                    "avatar_url": None,
                }
            return {
                "name": character.name,
                "handle": character.handle,
                "avatar_url": character.avatar_url,
            }
    if notification.actor_user_id:
        user = community_crud.get_user(db, notification.actor_user_id)
        if user is not None:
            return {"name": user.display_name, "handle": None, "avatar_url": None}
    return {"name": None, "handle": None, "avatar_url": None}


def _notification_recipient_identity(
    db: Session, notification: models.Notification
) -> dict[str, str | None]:
    if notification.recipient_character_id:
        character = community_crud.get_character(db, notification.recipient_character_id)
        if character is not None:
            if character.deleted_at is not None:
                return {
                    "name": DELETED_CHARACTER_NAME,
                    "handle": None,
                    "avatar_url": None,
                }
            return {
                "name": character.name,
                "handle": character.handle,
                "avatar_url": character.avatar_url,
            }
    if notification.recipient_user_id:
        user = community_crud.get_user(db, notification.recipient_user_id)
        if user is not None:
            return {"name": user.display_name, "handle": None, "avatar_url": None}
    return {"name": None, "handle": None, "avatar_url": None}


def _notification_post_preview(
    db: Session, post_id: str | None
) -> dict[str, str | None]:
    if post_id is None:
        return {"title": None, "body": None}
    post = community_crud.get_post_including_report_hidden(db, post_id)
    if post is None:
        return {"title": None, "body": None}
    if not _is_post_public_context_visible(db, post):
        return {"title": REPORT_HIDDEN_TITLE, "body": REPORT_HIDDEN_MESSAGE}
    return {"title": post.title, "body": post.body}


def _resolve_follower(
    db: Session, user: models.User, data: schemas.FollowCreate
) -> tuple[models.User | None, models.Character | None]:
    if data.follower_character_id is None:
        return user, None
    return None, _resolve_author_character(db, user, data.follower_character_id)


def _resolve_target_profile(
    db: Session, target_type: str, target_id: str
) -> tuple[models.User | None, models.Character | None]:
    if target_type != "character":
        raise ProfileNotFoundError(target_id)
    character = community_crud.get_character(db, target_id)
    if character is None or character.deleted_at is not None:
        raise ProfileNotFoundError(target_id)
    return None, character


def _ensure_not_self_follow(
    follower_user: models.User | None,
    follower_character: models.Character | None,
    target_user: models.User | None,
    target_character: models.Character | None,
) -> None:
    if follower_user is not None and target_user is not None:
        if follower_user.id == target_user.id:
            raise FollowSelfError("user cannot follow itself")
    if follower_character is not None and target_character is not None:
        if follower_character.id == target_character.id:
            raise FollowSelfError("character cannot follow itself")


def _notify_post_owner(
    db: Session,
    *,
    notification_type: str,
    post: models.Post,
    source_post_id: str | None,
    actor_user_id: str | None,
    actor_character_id: str | None,
) -> None:
    community_crud.create_notification(
        db,
        notification_type=notification_type,
        recipient_user_id=post.author_user_id if post.author_character_id is None else None,
        recipient_character_id=post.author_character_id,
        actor_user_id=actor_user_id,
        actor_character_id=actor_character_id,
        post_id=post.id,
        source_post_id=source_post_id,
    )


def _notify_mentioned_characters(
    db: Session,
    *,
    post: models.Post,
    actor_user_id: str | None,
    actor_character_id: str | None,
    skip_character_ids: Iterable[str | None] = (),
) -> None:
    skipped = {character_id for character_id in skip_character_ids if character_id}
    if actor_character_id:
        skipped.add(actor_character_id)
    for mention in _mentioned_characters_for_texts(db, post.title, post.body):
        if mention.character_id in skipped:
            continue
        community_crud.create_notification(
            db,
            notification_type="mention",
            recipient_character_id=mention.character_id,
            actor_user_id=actor_user_id,
            actor_character_id=actor_character_id,
            post_id=post.id,
            source_post_id=None,
        )


def _post_summary(db: Session, post: models.Post) -> schemas.PostSummary:
    comment_count = community_crud.count_post_comments(db, post.id)
    author = _post_author_identity(db, post)
    media = _post_media_reads(db, post)
    return schemas.PostSummary.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": post.title,
            "body": post.body,
            "info_kind": post.info_kind,
            "source_name": post.source_name,
            "source_url": post.source_url,
            "observed_at": post.observed_at,
            "location_label": post.location_label,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": _mentioned_characters_for_texts(
                db, post.title, post.body
            ),
            "reply_to_post_id": post.reply_to_post_id,
            "quote_post_id": post.quote_post_id,
            "repost_of_post_id": post.repost_of_post_id,
            "comment_count": comment_count,
            "like_count": community_crud.count_post_likes(db, post.id),
            "reply_count": community_crud.count_post_replies(db, post.id),
            "repost_count": community_crud.count_post_reposts(db, post.id),
            "quote_count": community_crud.count_post_quotes(db, post.id),
            "quoted_post": _post_reference(db, post.quote_post_id),
            "reposted_post": _post_reference(db, post.repost_of_post_id),
            "report_hidden": community_crud.is_report_hidden(post),
            "media": media,
        }
    )


def _post_detail(db: Session, post) -> schemas.PostDetail:
    author = _post_author_identity(db, post)
    media = _post_media_reads(db, post)
    return schemas.PostDetail.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": post.title,
            "body": post.body,
            "info_kind": post.info_kind,
            "source_name": post.source_name,
            "source_url": post.source_url,
            "observed_at": post.observed_at,
            "location_label": post.location_label,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": _mentioned_characters_for_texts(
                db, post.title, post.body
            ),
            "reply_to_post_id": post.reply_to_post_id,
            "quote_post_id": post.quote_post_id,
            "repost_of_post_id": post.repost_of_post_id,
            "comments": [],
            "like_count": community_crud.count_post_likes(db, post.id),
            "reply_count": community_crud.count_post_replies(db, post.id),
            "repost_count": community_crud.count_post_reposts(db, post.id),
            "quote_count": community_crud.count_post_quotes(db, post.id),
            "quoted_post": _post_reference(db, post.quote_post_id),
            "reposted_post": _post_reference(db, post.repost_of_post_id),
            "report_hidden": community_crud.is_report_hidden(post),
            "media": media,
        }
    )


def _hidden_post_detail(db: Session, post: models.Post) -> schemas.PostDetail:
    author = _post_author_identity(db, post)
    return schemas.PostDetail.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": REPORT_HIDDEN_TITLE,
            "body": REPORT_HIDDEN_MESSAGE,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": [],
            "reply_to_post_id": post.reply_to_post_id,
            "quote_post_id": None,
            "repost_of_post_id": None,
            "comments": [],
            "like_count": 0,
            "reply_count": 0,
            "repost_count": 0,
            "quote_count": 0,
            "quoted_post": None,
            "reposted_post": None,
            "report_hidden": True,
        }
    )


def is_post_public_context_visible(db: Session, post: models.Post) -> bool:
    return _is_post_public_context_visible(db, post)


def _is_post_public_context_visible(db: Session, post: models.Post) -> bool:
    if post.deleted_at is not None or community_crud.is_report_hidden(post):
        return False
    if (
        post.quote_post_id is not None
        and community_crud.get_post(db, post.quote_post_id) is None
    ):
        return False
    if (
        post.repost_of_post_id is not None
        and community_crud.get_post(db, post.repost_of_post_id) is None
    ):
        return False
    seen = {post.id}
    current = post
    while current.reply_to_post_id is not None:
        parent = community_crud.get_post(db, current.reply_to_post_id)
        if parent is None or parent.id in seen:
            return False
        seen.add(parent.id)
        current = parent
    return True


def _post_reference(db: Session, post_id: str | None) -> schemas.PostReference | None:
    if post_id is None:
        return None
    post = community_crud.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        return None
    author = _post_author_identity(db, post)
    return schemas.PostReference.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": post.title,
            "body": post.body,
            "info_kind": post.info_kind,
            "source_name": post.source_name,
            "source_url": post.source_url,
            "observed_at": post.observed_at,
            "location_label": post.location_label,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": _mentioned_characters_for_texts(
                db, post.title, post.body
            ),
            "media": _post_media_reads(db, post),
        }
    )


def _post_media_reads(db: Session, post: models.Post) -> list[schemas.PostMediaRead]:
    if community_crud.is_report_hidden(post):
        return []
    return [
        schemas.PostMediaRead.model_validate(media)
        for media in community_crud.list_post_media(db, post.id)
    ]


def _post_author_identity(db: Session, post: models.Post) -> dict[str, str | None]:
    if post.author_character_id:
        character = community_crud.get_character(db, post.author_character_id)
        if character is not None:
            if character.deleted_at is not None:
                return {
                    "name": DELETED_CHARACTER_NAME,
                    "handle": None,
                    "avatar_url": None,
                }
            return {
                "name": character.name,
                "handle": character.handle,
                "avatar_url": character.avatar_url,
            }
    return {"name": post.author_name, "handle": None, "avatar_url": None}


def _mentioned_characters_for_texts(
    db: Session, *texts: str | None
) -> list[schemas.MentionedCharacterRef]:
    handles: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in MENTION_HANDLE_RE.finditer(text):
            handle = match.group(1)
            if handle in seen:
                continue
            seen.add(handle)
            handles.append(handle)
    if not handles:
        return []

    characters = list(
        db.scalars(
            select(models.Character).where(
                models.Character.handle.in_(handles),
                models.Character.deleted_at.is_(None),
                models.Character.moderation_status == "active",
            )
        )
    )
    by_handle = {character.handle: character for character in characters}
    return [
        schemas.MentionedCharacterRef(
            handle=handle,
            character_id=character.id,
            name=character.name,
        )
        for handle in handles
        if (character := by_handle.get(handle)) is not None
    ]


def _can_delete_post(db: Session, user: models.User, post: models.Post) -> bool:
    if post.author_character_id is not None:
        character = community_crud.get_character(db, post.author_character_id)
        return character is not None and character.owner_id == user.id
    return post.author_user_id == user.id
