from __future__ import annotations

import re
import unicodedata


_CONTROL_CATEGORIES = {"Cc", "Cf"}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_search_text(value: object, *, max_chars: int) -> str:
    """Return the deterministic, non-authoritative text used by feed search."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(
        " " if unicodedata.category(character) in _CONTROL_CATEGORIES and character != "\u200c" else character
        for character in text
    )
    text = _WHITESPACE_RE.sub(" ", text).strip().casefold()
    return text[:max_chars]


def word_character(character: str) -> bool:
    return character == "_" or character == "\u200c" or unicodedata.category(character)[0] in "LMN"


def word_spans(text: str, *, structured: bool = False):
    """Preserve combining marks and Persian ZWNJ; punctuation is not a word.

    Identifier connectors belong to a span only between word characters, so a
    sentence-final dot never expands a number/version or blocks a normal word.
    """
    index = 0
    while index < len(text):
        if not word_character(text[index]):
            index += 1
            continue
        start = index
        index += 1
        while index < len(text):
            if word_character(text[index]):
                index += 1
            elif (structured and text[index] in "-:./+" and index + 1 < len(text)
                  and word_character(text[index + 1])):
                index += 2
            else:
                break
        yield start, index, text[start:index]


def literal_boundary(text: str, start: int, end: int) -> bool:
    """Prevent a partial identifier while accepting terminal punctuation."""
    if start and word_character(text[start - 1]):
        return False
    if end < len(text) and word_character(text[end]):
        return False
    if start > 1 and text[start - 1] in "-:./+" and word_character(text[start - 2]):
        return False
    if end + 1 < len(text) and text[end] in "-:./+" and word_character(text[end + 1]):
        return False
    return True




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
