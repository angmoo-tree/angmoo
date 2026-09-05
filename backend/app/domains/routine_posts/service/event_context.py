"""Filter, rank and bound source events before they enter a routine prompt."""
from __future__ import annotations
from datetime import datetime
from typing import Any
import json
from app.domains.routine_posts.constants import MAX_SOURCE_EVENTS, MAX_EVENT_EXCERPT_CHARS, MAX_TOTAL_EVENT_EXCERPT_CHARS, MAX_EVENT_CONTEXT_JSON_BYTES
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.domains.routine_posts.utils.text import _clip
from app.domains.routines.service.scheduling import aware_utc as _aware_utc


def _relationship_rank(value: str) -> int:
    return {
        "trusted": 4,
        "close": 3,
        "familiar": 2,
        "new": 1,
        "unknown": 0,
    }.get(value, 0)



def _bounded_events(
    raw_events: list[RoutineInteractionInput],
    *,
    world_id: str,
    consumer_world_character_id: str,
    after: datetime,
    before: datetime,
    blocked_event_ids: set[str] | None = None,
) -> tuple[tuple[RoutineInteractionInput, ...], dict[str, int], int, int]:
    reasons: dict[str, int] = {}

    def reject(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    normalized: list[RoutineInteractionInput] = []
    seen: set[str] = set()
    for item in raw_events:
        occurred_at = _aware_utc(item.occurred_at)
        if item.source_event_id in (blocked_event_ids or set()):
            reject("already_consumed")
            continue
        if item.source_event_id in seen:
            reject("already_consumed")
            continue
        if (
            item.world_id != world_id
            or item.consumer_world_character_id != consumer_world_character_id
        ):
            reject("world_scope_filtered")
            continue
        if occurred_at <= after or occurred_at > before:
            reject("policy_filtered")
            continue
        excerpt = _clip(item.excerpt, MAX_EVENT_EXCERPT_CHARS)
        if not excerpt:
            reject("policy_filtered")
            continue
        seen.add(item.source_event_id)
        normalized.append(
            RoutineInteractionInput(
                source_event_id=item.source_event_id,
                world_id=item.world_id,
                consumer_world_character_id=item.consumer_world_character_id,
                actor_world_character_id=item.actor_world_character_id,
                excerpt=excerpt,
                occurred_at=occurred_at,
                directness=max(0, min(int(item.directness), 100)),
                episode_relevance=max(0, min(int(item.episode_relevance), 100)),
                relationship_band=item.relationship_band,
            )
        )
    normalized.sort(
        key=lambda item: (
            -item.directness,
            -item.episode_relevance,
            -_relationship_rank(item.relationship_band),
            -item.occurred_at.timestamp(),
            item.source_event_id,
        )
    )

    selected: list[RoutineInteractionInput] = []
    total_chars = 0
    for item in normalized:
        if len(selected) >= MAX_SOURCE_EVENTS:
            reject("prompt_item_limit")
            continue
        if total_chars + len(item.excerpt) > MAX_TOTAL_EVENT_EXCERPT_CHARS:
            reject("excerpt_char_limit")
            continue
        candidate = [*selected, item]
        payload = [
            {
                "source_event_id": event.source_event_id,
                "actor_world_character_id": event.actor_world_character_id,
                "excerpt": event.excerpt,
                "occurred_at": event.occurred_at.isoformat(),
                "relationship_band": event.relationship_band,
            }
            for event in candidate
        ]
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_EVENT_CONTEXT_JSON_BYTES:
            reject("context_char_limit")
            continue
        selected.append(item)
        total_chars += len(item.excerpt)
    return tuple(selected), reasons, total_chars, len(normalized)


class EmptyRoutineInteractionSource:
    def candidates(
        self,
        db: Any,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[RoutineInteractionInput]:
        del db, world_id, consumer_world_character_id, episode_id, after, before
        return []
