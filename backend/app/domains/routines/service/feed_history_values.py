"""Provider-independent resident Feed history sanitization and bounded prompt values."""

import json
import re
from datetime import datetime
from typing import Any
from app.core.context_text import neutralize_context_text
from app.core.bounded_text import _clip_text, _safe_topic_text
from app.domains.routines.schemas import feed_history as schemas
from app.domains.routines.constants import (
    FEED_HISTORY_SANITIZED_CONSUMED_LIMIT,
    RECENT_FEED_INTEREST_HISTORY_LIMIT,
    RECENT_OWN_ROOT_TOPIC_HISTORY_LIMIT,
    FEED_HISTORY_STYLE_MARKER_RE,
)


def _safe_feed_history_post_id(value: object) -> str:
    return _clip_text(neutralize_context_text(str(value or "")).strip(), 64)


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
        lines.append("\n".join(item_lines))
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


from app.core.json_objects import _json_object

def activity_result_text_for_prompt(
    result: str | None, reason: str | None = None
) -> str:
    payload = _json_object(result)
    if payload:
        message = _safe_topic_text(payload.get("message"), 500)
        if message:
            return message
    return result or reason or "-"
