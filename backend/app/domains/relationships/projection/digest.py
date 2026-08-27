"""Deterministic, storage-neutral relationship projection parity digest."""

from __future__ import annotations

import json

from app.domains.relationships.projection.commands import (
    NoGraphMutationCommand,
    ProjectionCommand,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)


def _digest_entry(*values: object) -> str:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


def projection_digest(
    commands: list[ProjectionCommand] | tuple[ProjectionCommand, ...],
) -> dict[str, list[str]]:
    world_characters: set[str] = set()
    events: set[str] = set()
    relationships: dict[str, tuple[object, ...]] = {}
    evidence: set[tuple[object, ...]] = set()

    for command in commands:
        if isinstance(command, NoGraphMutationCommand):
            continue
        if isinstance(command, SourceExclusionProjectionCommand):
            events.discard(command.event_id)
            evidence = {row for row in evidence if row[3] != command.event_id}
            continue

        event = (
            command.event
            if isinstance(command, RelationshipStateProjectionCommand)
            else command
        )
        if not isinstance(event, SocialEventProjectionCommand):
            continue
        world_characters.add(event.actor_world_character_id)
        if event.target_world_character_id is not None:
            world_characters.add(event.target_world_character_id)
        events.add(event.event_id)

        if isinstance(command, RelationshipStateProjectionCommand):
            relationships[command.relationship_state_id] = (
                command.relationship_state_id,
                command.actor_world_character_id,
                command.target_world_character_id,
                command.relationship_version,
                command.familiarity,
                command.affinity,
                command.trust,
                command.tension,
                command.interaction_count,
            )
            evidence.add(
                (
                    command.relationship_state_id,
                    command.actor_world_character_id,
                    command.target_world_character_id,
                    event.event_id,
                    command.relationship_version,
                )
            )

    return {
        "world_characters": [
            _digest_entry(value) for value in sorted(world_characters)
        ],
        "events": [_digest_entry(value) for value in sorted(events)],
        "relationships": [
            _digest_entry(*value)
            for value in sorted(relationships.values(), key=lambda row: str(row[0]))
        ],
        "evidence": [
            _digest_entry(*value)
            for value in sorted(
                evidence,
                key=lambda row: tuple(str(item) for item in row),
            )
        ],
    }


__all__ = ["projection_digest"]
