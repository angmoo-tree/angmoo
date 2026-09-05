"""Neutralized context clipping shared by prompt and memory formatting."""

from typing import Any

from app.core.context_text import neutralize_context_text


def clip_context_text(value: Any, max_chars: int) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."
