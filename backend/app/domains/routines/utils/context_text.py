"""Whitespace compaction preserving the original resident prompt text contract."""


def _clip_text(value: str | None, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."

