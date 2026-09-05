"""Original activity log type normalization."""
from app.domains.routines.constants import PUBLIC_ACTION_TYPES


def _normalize_action_types(action_types: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(action_types, str):
        return (action_types,)
    return action_types



def _public_action_log_types() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            action_type
            for action_types in PUBLIC_ACTION_TYPES.values()
            for action_type in action_types
        )
    )

