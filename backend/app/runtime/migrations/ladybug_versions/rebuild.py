"""Rebuild the v1 LadybugDB projection only from SQLite canonical outbox."""

from __future__ import annotations

from pathlib import Path

from app.domains.relationships.ports.replay import ProjectionReplaySource
from app.domains.relationships.projection.digest import projection_digest
from app.integrations.ladybug_projection import LadybugRelationshipProjection


class LadybugRebuildError(RuntimeError):
    """Stable projection rebuild failure."""


def rebuild_projection_v1(
    *,
    database_root: Path,
    replay_source: ProjectionReplaySource,
) -> dict[str, dict[str, list[str]]]:
    expected_by_world: dict[str, dict[str, list[str]]] = {}
    with LadybugRelationshipProjection(database_root=database_root) as projection:
        for world_id in replay_source.world_ids():
            commands = replay_source.commands_for_world(world_id)
            for command in commands:
                projection.apply(command)
            expected = projection_digest(commands)
            actual = projection.world_digest(world_id)
            if actual != expected:
                raise LadybugRebuildError("ladybug_rebuild_parity_mismatch")
            expected_by_world[world_id] = expected
        projection.verify_connectivity()
    return expected_by_world


__all__ = ["LadybugRebuildError", "rebuild_projection_v1"]
