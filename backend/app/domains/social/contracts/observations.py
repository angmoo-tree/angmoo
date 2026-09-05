"""Canonical social-observation contracts.

Observation is a deterministic statement that one WorldCharacter was actually
shown one canonical source event.  It deliberately carries no inferred
affinity, trust, tension, or other subjective emotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


ObservationLane = Literal["routine", "inbox", "feed"]


class SocialObservationError(Exception):
    reason_code = "social_observation_error"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


@dataclass(frozen=True)
class SocialObservationCommand:
    world_id: str
    observer_world_character_id: str
    source_social_event_id: str | None
    source_post_id: str | None
    lane: ObservationLane
    observed_at: datetime


@dataclass(frozen=True)
class SocialObservationResult:
    source_social_event_id: str
    receipt_id: str
    relationship_state_id: str
    replayed: bool
    lane: ObservationLane
    schema_version: Literal["social-observation-v1"] = "social-observation-v1"


__all__ = [
    "ObservationLane",
    "SocialObservationCommand",
    "SocialObservationError",
    "SocialObservationResult",
]
