"""Compatibility facade for routines-owned activity-state policy."""

from app.domains.routines.policies.activity_state import (
    ACTION_NOTE_MAX_LENGTH,
    BEAT_DELTA_LIMIT,
    MOODS,
    SOURCE_DELTA_LIMIT,
    STATE_KEYS,
    ActivityStateValidationError,
    apply_state_changes,
    initial_state,
    validate_state_snapshot,
)

__all__ = [
    "ACTION_NOTE_MAX_LENGTH",
    "BEAT_DELTA_LIMIT",
    "MOODS",
    "SOURCE_DELTA_LIMIT",
    "STATE_KEYS",
    "ActivityStateValidationError",
    "apply_state_changes",
    "initial_state",
    "validate_state_snapshot",
]
