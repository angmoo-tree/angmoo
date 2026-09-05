"""Context records and same-transaction readers used by routine post policy.

Related records are read views of the caller's attached objects, not copied ORM
models or a second persistence owner. Any permits those records and test views
without importing another domain's models into this contract.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol
from app.domains.routines.contracts.lifecycle import DueTick
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput


class RoutineInteractionSource(Protocol):
    def candidates(
        self,
        db: Any,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[RoutineInteractionInput]: ...



@dataclass(frozen=True)
class RoutinePostContext:
    world: Any
    membership: Any
    world_character: Any
    character: Any
    profile: Any
    plan: Any
    item: Any
    episode: Any
    due_tick: DueTick
    previous_beat: Any | None
    previous_post: Any | None
    state_before: dict[str, object]
    source_events: tuple[RoutineInteractionInput, ...]
    eligible_event_count: int
    overflow_reason_counts: dict[str, int]
    prompt_comment_chars: int

    @property
    def considered_source_event_ids(self) -> list[str]:
        return [event.source_event_id for event in self.source_events]



class RoutineContextReferences(Protocol):
    def get_membership(self, membership_id: str) -> Any: ...
    def get_world(self, world_id: str) -> Any: ...
    def current_item(self, *, world_character_id: str, current: datetime) -> Any: ...
    def get_plan(self, plan_id: str) -> Any: ...
    def episode_for_item(self, plan_item_id: str) -> Any: ...
    def get_repertoire(self, repertoire_id: str) -> Any: ...
    def get_profile(self, profile_id: str) -> Any: ...
    def get_beat(self, beat_id: str) -> Any: ...
    def get_post(self, post_id: str) -> Any: ...
    def latest_beat(self, episode_id: str) -> Any: ...
    def get_activity_setting(self, character_id: str) -> Any: ...
    def event_consumptions(self, *, world_character_id: str, event_ids: list[str]) -> Iterable[Any]: ...
    def default_interaction_source(self) -> RoutineInteractionSource: ...
