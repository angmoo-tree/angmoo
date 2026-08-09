from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


MOODS = frozenset(
    {
        "neutral",
        "curious",
        "joyful",
        "hopeful",
        "calm",
        "concerned",
        "frustrated",
        "sad",
        "embarrassed",
    }
)
STATE_KEYS = frozenset(
    {"mood", "mood_intensity", "energy", "social_energy", "action_note"}
)
ACTION_NOTE_MAX_LENGTH = 160
SOURCE_DELTA_LIMIT = 20
BEAT_DELTA_LIMIT = 30


class ActivityStateValidationError(ValueError):
    pass


def initial_state() -> dict[str, object]:
    return {
        "mood": "neutral",
        "mood_intensity": 0,
        "energy": 50,
        "social_energy": 50,
        "action_note": "",
    }


def _bounded_integer(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActivityStateValidationError(f"{field}_invalid")
    if value < minimum or value > maximum:
        raise ActivityStateValidationError(f"{field}_out_of_range")
    return value


def validate_state_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    if frozenset(snapshot) != STATE_KEYS:
        raise ActivityStateValidationError("activity_state_fields_invalid")
    mood = snapshot["mood"]
    if not isinstance(mood, str) or mood not in MOODS:
        raise ActivityStateValidationError("activity_state_mood_invalid")
    action_note = snapshot["action_note"]
    if not isinstance(action_note, str) or len(action_note) > ACTION_NOTE_MAX_LENGTH:
        raise ActivityStateValidationError("activity_state_action_note_invalid")
    normalized = {
        "mood": mood,
        "mood_intensity": _bounded_integer(
            snapshot["mood_intensity"],
            field="mood_intensity",
            minimum=0,
            maximum=100,
        ),
        "energy": _bounded_integer(
            snapshot["energy"], field="energy", minimum=0, maximum=100
        ),
        "social_energy": _bounded_integer(
            snapshot["social_energy"],
            field="social_energy",
            minimum=0,
            maximum=100,
        ),
        "action_note": action_note,
    }
    if normalized["mood_intensity"] == 0:
        normalized["mood"] = "neutral"
    return normalized


def _validate_delta(change: Mapping[str, Any]) -> dict[str, object]:
    allowed = {
        "mood",
        "mood_intensity_delta",
        "energy_delta",
        "social_energy_delta",
        "action_note",
    }
    if not set(change).issubset(allowed):
        raise ActivityStateValidationError("activity_state_delta_fields_invalid")
    mood = change.get("mood")
    if mood is not None and (not isinstance(mood, str) or mood not in MOODS):
        raise ActivityStateValidationError("activity_state_mood_invalid")
    normalized: dict[str, object] = {"mood": mood}
    for field in (
        "mood_intensity_delta",
        "energy_delta",
        "social_energy_delta",
    ):
        normalized[field] = _bounded_integer(
            change.get(field, 0),
            field=field,
            minimum=-SOURCE_DELTA_LIMIT,
            maximum=SOURCE_DELTA_LIMIT,
        )
    action_note = change.get("action_note")
    if action_note is not None and (
        not isinstance(action_note, str) or len(action_note) > ACTION_NOTE_MAX_LENGTH
    ):
        raise ActivityStateValidationError("activity_state_action_note_invalid")
    normalized["action_note"] = action_note
    return normalized


def apply_state_changes(
    current: Mapping[str, object],
    changes: Iterable[Mapping[str, Any]],
    *,
    scheduled_without_source: bool = False,
    daypart_ended: bool = False,
) -> dict[str, object]:
    state = validate_state_snapshot(current)
    normalized_changes = [_validate_delta(change) for change in changes]
    totals = {
        field: sum(int(change[field]) for change in normalized_changes)
        for field in (
            "mood_intensity_delta",
            "energy_delta",
            "social_energy_delta",
        )
    }
    if any(abs(total) > BEAT_DELTA_LIMIT for total in totals.values()):
        raise ActivityStateValidationError("activity_state_beat_delta_out_of_range")

    if scheduled_without_source and normalized_changes:
        raise ActivityStateValidationError("scheduled_beat_has_source_delta")

    latest_mood = next(
        (
            str(change["mood"])
            for change in reversed(normalized_changes)
            if change["mood"] is not None
        ),
        str(state["mood"]),
    )
    latest_note = next(
        (
            str(change["action_note"])
            for change in reversed(normalized_changes)
            if change["action_note"] is not None
        ),
        str(state["action_note"]),
    )
    intensity = int(state["mood_intensity"]) + totals["mood_intensity_delta"]
    if scheduled_without_source:
        intensity -= 10
    if daypart_ended:
        intensity -= 20
    intensity = max(0, min(100, intensity))

    return validate_state_snapshot(
        {
            "mood": latest_mood if intensity > 0 else "neutral",
            "mood_intensity": intensity,
            "energy": max(0, min(100, int(state["energy"]) + totals["energy_delta"])),
            "social_energy": max(
                0,
                min(
                    100,
                    int(state["social_energy"])
                    + totals["social_energy_delta"],
                ),
            ),
            "action_note": latest_note,
        }
    )
