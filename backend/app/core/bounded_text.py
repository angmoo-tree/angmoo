"""Bounded neutral text shared by Social results and resident planning context."""

from app.core.context_text import neutralize_context_text


def _clip_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _safe_topic_text(value: object, limit: int = 300) -> str:
    return _clip_text(neutralize_context_text(str(value or "")), limit)
