"""Owner reads needed to apply one deterministic Social observation."""
from __future__ import annotations
from typing import Protocol
from app.domains.relationships.contracts.events import EventPost


class ObservationPost(EventPost, Protocol):
    @property
    def id(self) -> str: ...
    @property
    def author_world_character_id(self) -> str | None: ...


class ObservationWorldCharacter(Protocol):
    @property
    def id(self) -> str: ...


class ObservationReferences(Protocol):
    """Returns caller-Session objects at the original query positions."""
    def world_character(self, *, world_id: str, world_character_id: str, lock: bool = False) -> ObservationWorldCharacter: ...
    def get_post(self, post_id: str) -> ObservationPost | None: ...
    def pair_blocked(self, *, world_id: str, actor_id: str, target_id: str) -> bool: ...
