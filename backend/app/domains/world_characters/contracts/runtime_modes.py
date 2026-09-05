"""Canonical autonomous WorldCharacter runtime-mode contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


AUTONOMOUS_ACTIVITY_RUNTIME_MODE = "routine_resident_v1"
AUTONOMOUS_FEED_RUNTIME_MODE = "keyword_search_v1"
LEGACY_FEED_RUNTIME_MODE = "legacy_latest_v1"
LOCAL_ENTRY_IDEMPOTENCY_PROFILE_KEY = "entry_idempotency_key"


@dataclass(frozen=True, slots=True)
class AutonomousRuntimeModePair:
    activity_runtime_mode: str = AUTONOMOUS_ACTIVITY_RUNTIME_MODE
    feed_runtime_mode: str = AUTONOMOUS_FEED_RUNTIME_MODE


AUTONOMOUS_RUNTIME_MODE_PAIR = AutonomousRuntimeModePair()


def is_expected_autonomous_runtime_pair(
    *, activity_runtime_mode: str, feed_runtime_mode: str
) -> bool:
    return (
        activity_runtime_mode == AUTONOMOUS_ACTIVITY_RUNTIME_MODE
        and feed_runtime_mode == AUTONOMOUS_FEED_RUNTIME_MODE
    )


def is_affected_local_entry_runtime_pair(
    *,
    control_mode: str,
    owner_user_id: str | None,
    activity_runtime_mode: str,
    feed_runtime_mode: str,
    local_profile: Mapping[str, object] | None,
) -> bool:
    """Identify the exact PR G legacy-default signature before DB checks."""

    entry_key = (
        local_profile.get(LOCAL_ENTRY_IDEMPOTENCY_PROFILE_KEY)
        if isinstance(local_profile, Mapping)
        else None
    )
    return bool(
        control_mode == "autonomous"
        and owner_user_id is None
        and activity_runtime_mode == AUTONOMOUS_ACTIVITY_RUNTIME_MODE
        and feed_runtime_mode == LEGACY_FEED_RUNTIME_MODE
        and isinstance(entry_key, str)
        and entry_key.strip()
    )


__all__ = [
    "AUTONOMOUS_ACTIVITY_RUNTIME_MODE",
    "AUTONOMOUS_FEED_RUNTIME_MODE",
    "AUTONOMOUS_RUNTIME_MODE_PAIR",
    "AutonomousRuntimeModePair",
    "LEGACY_FEED_RUNTIME_MODE",
    "LOCAL_ENTRY_IDEMPOTENCY_PROFILE_KEY",
    "is_affected_local_entry_runtime_pair",
    "is_expected_autonomous_runtime_pair",
]
