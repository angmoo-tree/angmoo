"""Pure P3/P4 activity-state transition contract."""

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
STATE_KEYS_V2 = frozenset({"mood", "mood_intensity", "action_note"})
ACTION_NOTE_MAX_LENGTH = 160
SOURCE_DELTA_LIMIT = 20
BEAT_DELTA_LIMIT = 30


class ActivityStateValidationError(ValueError):
    pass


def initial_state(*, schema_version: int = 1) -> dict[str, object]:
    return validate_state_snapshot({
        "mood": "neutral",
        "mood_intensity": 0,
        "energy": 50,
        "social_energy": 50,
        "action_note": "",
    } if schema_version == 1 else {"mood": "neutral", "mood_intensity": 0, "action_note": ""}, schema_version=schema_version)


def _bounded_integer(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActivityStateValidationError(f"{field}_invalid")
    if value < minimum or value > maximum:
        raise ActivityStateValidationError(f"{field}_out_of_range")
    return value


def validate_state_snapshot(snapshot: Mapping[str, object], *, schema_version: int = 1) -> dict[str, object]:
    if schema_version not in {1, 2}:
        raise ActivityStateValidationError("activity_state_version_unsupported")
    if frozenset(snapshot) != (STATE_KEYS if schema_version == 1 else STATE_KEYS_V2):
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
        "action_note": action_note,
    }
    if schema_version == 1:
        for name in ("energy", "social_energy"):
            normalized[name] = _bounded_integer(snapshot[name], field=name, minimum=0, maximum=100)
    if normalized["mood_intensity"] == 0:
        normalized["mood"] = "neutral"
    return normalized


def project_state_v2(snapshot: Mapping[str, object], *, source_version: int) -> dict[str, object]:
    validated = validate_state_snapshot(snapshot, schema_version=source_version)
    return validate_state_snapshot({key: validated[key] for key in STATE_KEYS_V2}, schema_version=2)


def _validate_delta(change: Mapping[str, Any], *, schema_version: int) -> dict[str, object]:
    allowed = {
        "mood",
        "mood_intensity_delta",
        "energy_delta",
        "social_energy_delta",
        "action_note",
    }
    if schema_version == 2:
        allowed.difference_update({"energy_delta", "social_energy_delta"})
    if not set(change).issubset(allowed):
        raise ActivityStateValidationError("activity_state_delta_fields_invalid")
    mood = change.get("mood")
    if mood is not None and (not isinstance(mood, str) or mood not in MOODS):
        raise ActivityStateValidationError("activity_state_mood_invalid")
    normalized: dict[str, object] = {"mood": mood}
    for field in ("mood_intensity_delta",) + (("energy_delta", "social_energy_delta") if schema_version == 1 else ()):
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
    schema_version: int = 1,
) -> dict[str, object]:
    state = validate_state_snapshot(current, schema_version=schema_version)
    normalized_changes = [_validate_delta(change, schema_version=schema_version) for change in changes]
    totals = {
        field: sum(int(change[field]) for change in normalized_changes)
        for field in ("mood_intensity_delta",) + (("energy_delta", "social_energy_delta") if schema_version == 1 else ())
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

    result = {
            "mood": latest_mood if intensity > 0 else "neutral",
            "mood_intensity": intensity,
            "action_note": latest_note,
        }
    if schema_version == 1:
        for name in ("energy", "social_energy"):
            result[name] = max(0, min(100, int(state[name]) + totals[name + "_delta"]))
    return validate_state_snapshot(result, schema_version=schema_version)
