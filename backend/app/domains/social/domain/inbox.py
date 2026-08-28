"""Canonical owner-reply inbox candidate contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ManualInboxInteractionCandidate:
    source_event_id: str
    world_id: str
    consumer_world_character_id: str
    actor_world_character_id: str
    excerpt: str
    occurred_at: datetime
    directness: int
    episode_relevance: int
    relationship_band: str


__all__ = ["ManualInboxInteractionCandidate"]
