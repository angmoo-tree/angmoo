"""Provider-neutral interaction candidate contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RoutineInteractionInput:
    source_event_id: str
    world_id: str
    consumer_world_character_id: str
    actor_world_character_id: str
    excerpt: str
    occurred_at: datetime
    directness: int = 0
    episode_relevance: int = 0
    relationship_band: str = "unknown"


__all__ = ["RoutineInteractionInput"]
