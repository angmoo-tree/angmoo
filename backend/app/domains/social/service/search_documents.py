from __future__ import annotations

from collections.abc import Iterable

from app.core.search_text import normalize_search_text


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
