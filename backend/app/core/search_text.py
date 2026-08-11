from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


_CONTROL_CATEGORIES = {"Cc", "Cf"}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_search_text(value: object, *, max_chars: int) -> str:
    """Return the deterministic, non-authoritative text used by feed search."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(
        " " if unicodedata.category(character) in _CONTROL_CATEGORIES else character
        for character in text
    )
    text = _WHITESPACE_RE.sub(" ", text).strip().casefold()
    return text[:max_chars]


def build_post_search_document(
    *, title: object, body: object, topic_signature: object
) -> str:
    parts: Iterable[tuple[object, int]] = (
        (title, 160),
        (body, 4_000),
        (topic_signature, 300),
    )
    normalized = [
        text
        for value, limit in parts
        if (text := normalize_search_text(value, max_chars=limit))
    ]
    return "\n".join(normalized)
