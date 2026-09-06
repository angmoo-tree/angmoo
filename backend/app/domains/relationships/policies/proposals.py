"""Explicit daypart wording consistency for activity proposals."""

_DAYPART_MARKERS = {
    "dawn": ("새벽", "dawn"),
    "morning": ("아침", "오전", "morning"),
    "afternoon": ("낮", "오후", "afternoon"),
    "evening": ("저녁", "밤", "evening", "tonight"),
}


def _text_daypart_consistent(text: str, target_daypart: str) -> bool:
    normalized = text.casefold()
    explicit = {
        daypart
        for daypart, markers in _DAYPART_MARKERS.items()
        if any(marker in normalized for marker in markers)
    }
    return not explicit or explicit == {target_daypart}
