"""Public activity results exclude internal proof and recovery envelopes."""

PRIVATE_ACTIVITY_RESULT_KEYS = frozenset({"_relationship_effect_progress", "_interruption", "_routine_recovery"})


def public_execution_result(value):
    return {key: item for key, item in (value or {}).items() if key not in PRIVATE_ACTIVITY_RESULT_KEYS}
