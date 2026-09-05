"""Canonical post-result text and bounded topic/preview values."""
import json
from typing import Any
from app.core.context_text import neutralize_context_text
from app.domains.social.constants import FEED_SCAN_BODY_PREVIEW_CHARS


def _clip_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _safe_topic_text(value: object, limit: int = 300) -> str:
    return _clip_text(neutralize_context_text(str(value or "")), limit)


def _body_preview(value: str | None) -> str:
    return _safe_topic_text(value, FEED_SCAN_BODY_PREVIEW_CHARS)


def _fallback_topic_signature(*, title: str | None, body: str | None) -> str:
    title_text = _safe_topic_text(title, 120)
    body_text = _body_preview(body)
    if title_text and body_text:
        return _clip_text(f"{title_text} / {body_text}", 300)
    return _clip_text(title_text or body_text, 300)


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
