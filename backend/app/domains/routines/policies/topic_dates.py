"""Relative-date anchors and carryover phases for resident TopicArcs."""

from __future__ import annotations
from datetime import date, timedelta
from typing import Any
import re
import unicodedata


_CARRYOVER_ACTIVE = "active"


_CARRYOVER_COMPLETED = "completed"


_CARRYOVER_EXPIRED = "expired"


_CARRYOVER_DUE_TODAY = "due_today"


_CARRYOVER_FUTURE = "future"


_CARRYOVER_NONE = "none"


def _normalize_iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _normalized_relative_text(text: Any) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).lower()


def _detect_relative_date_anchor(text: Any, base_date: date) -> dict[str, str] | None:
    normalized = _normalized_relative_text(text)
    relative_specs = (
        ("\uc624\ub298", 0, "\uc624\ub298"),
        ("\ub0b4\uc77c", 1, "\ub0b4\uc77c"),
        ("\uc5b4\uc81c", -1, "\uc5b4\uc81c"),
        ("today", 0, "today"),
        ("tomorrow", 1, "tomorrow"),
        ("yesterday", -1, "yesterday"),
    )
    for marker, offset, original in relative_specs:
        if marker in normalized:
            return {
                "target_date": (base_date + timedelta(days=offset)).isoformat(),
                "relative_time_original": original,
            }
    return None


def _attach_step_date_anchors(
    steps: list[dict[str, Any]], base_date: date
) -> list[dict[str, Any]]:
    anchored: list[dict[str, Any]] = []
    for step in steps:
        item = dict(step)
        item.pop("target_date", None)
        item.pop("relative_time_original", None)
        anchor = _detect_relative_date_anchor(item.get("brief"), base_date)
        if anchor:
            item.update(anchor)
        anchored.append(item)
    return anchored


def _parse_target_date(value: Any) -> date | None:
    normalized = _normalize_iso_date(value)
    if normalized is None:
        return None
    return date.fromisoformat(normalized)


def _carryover_phase(target_date: date | None, current_date: date) -> str:
    if target_date is None:
        return _CARRYOVER_NONE
    if target_date == current_date:
        return _CARRYOVER_DUE_TODAY
    if target_date < current_date:
        return _CARRYOVER_EXPIRED
    return _CARRYOVER_FUTURE


def _carryover_phase_label(phase: str) -> str:
    return {
        _CARRYOVER_DUE_TODAY: "Use today's framing for this event.",
        _CARRYOVER_FUTURE: "Use future framing based on the actual target date.",
        _CARRYOVER_EXPIRED: "Do not continue this stale event as active.",
    }.get(phase, "No relative-date carryover.")
