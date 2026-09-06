from __future__ import annotations

import re
import unicodedata


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




def _like_search_terms(query: str) -> list[str]:
    raw = query.strip()
    if not raw:
        return []
    terms = [raw]
    if raw.startswith("@") and len(raw) > 1:
        terms.append(raw[1:])
    return list(dict.fromkeys(terms))


def _like_pattern(term: str) -> str:
    escaped = (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"
