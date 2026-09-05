"""Recognize already-covered handoff context without making storage reads."""

from __future__ import annotations
from typing import Any
import re
import unicodedata


_TOPIC_ARC_EVENT_TYPE = "writing_topic_arc"


def _normalize_coverage_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _coverage_word_tokens(text: str) -> set[str]:
    normalized = _normalize_coverage_text(text)
    return {
        token for token in normalized.split() if len(token) >= 2 and not token.isdigit()
    }


def _coverage_char_ngrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", _normalize_coverage_text(text))
    if len(compact) < 2:
        return set()
    grams: set[str] = set()
    for size in (2, 3, 4):
        if len(compact) < size:
            continue
        grams.update(
            compact[index : index + size] for index in range(len(compact) - size + 1)
        )
    return grams


def _handoff_covered_by_today_post(handoff_text: Any, post_text: Any) -> bool:
    handoff = _normalize_coverage_text(handoff_text)
    post = _normalize_coverage_text(post_text)
    if not handoff or not post:
        return False
    handoff_tokens = _coverage_word_tokens(handoff)
    post_tokens = _coverage_word_tokens(post)
    shared_tokens = handoff_tokens & post_tokens
    if len(shared_tokens) >= 3:
        return True
    if (
        handoff_tokens
        and len(handoff_tokens) <= 4
        and len(shared_tokens) >= max(2, len(handoff_tokens) - 1)
    ):
        return True
    handoff_grams = _coverage_char_ngrams(handoff)
    post_grams = _coverage_char_ngrams(post)
    if not handoff_grams or not post_grams:
        return False
    shared_grams = len(handoff_grams & post_grams)
    return shared_grams >= 8 and shared_grams / max(1, len(handoff_grams)) >= 0.35


def _handoff_coverage(
    handoff_text: str, coverage_posts: list[dict[str, Any]]
) -> dict[str, Any]:
    for post in coverage_posts:
        if _handoff_covered_by_today_post(handoff_text, post.get("coverage_text")):
            return {
                "already_covered_today": True,
                "covered_by_recent_post_id": post.get("post_id"),
                "coverage_reason": "today_root_post_overlap",
            }
    return {
        "already_covered_today": False,
        "covered_by_recent_post_id": None,
        "coverage_reason": None,
    }


def _handoff_continuity_kind(event_type: str) -> str:
    return {
        _TOPIC_ARC_EVENT_TYPE: "writing_memory",
        "langgraph_tick": "activity_memory",
        "observation_feed": "feed_memory",
        "observation_inbox": "inbox_memory",
        "relationship_review": "relationship_memory",
    }.get(event_type, "activity_memory")
