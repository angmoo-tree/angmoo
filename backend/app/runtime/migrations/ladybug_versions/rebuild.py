"""Rebuild the v1 LadybugDB projection only from SQLite canonical outbox."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app import models
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.services.graph_projection_commands import build_projection_command
from app.services.graph_projection_replay import projection_digest


class LadybugRebuildError(RuntimeError):
    """Stable projection rebuild failure."""


def rebuild_projection_v1(
    *,
    database_root: Path,
    session_factory: Callable[[], Any],
) -> dict[str, dict[str, list[str]]]:
    expected_by_world: dict[str, dict[str, list[str]]] = {}
    with LadybugRelationshipProjection(database_root=database_root) as projection:
        with session_factory() as db:
            world_ids = tuple(
                str(value)
                for value in db.scalars(
                    select(models.World.id).order_by(models.World.id)
                )
            )
        for world_id in world_ids:
            with session_factory() as db:
                outbox_ids = tuple(
                    str(value)
                    for value in db.scalars(
                        select(models.GraphProjectionOutbox.id)
                        .where(models.GraphProjectionOutbox.world_id == world_id)
                        .order_by(
                            models.GraphProjectionOutbox.created_at,
                            models.GraphProjectionOutbox.id,
                        )
                    )
                )
            commands = []
            for outbox_id in outbox_ids:
                with session_factory() as db:
                    command = build_projection_command(
                        db,
                        outbox_id=outbox_id,
                        replay_relationship_snapshot=True,
                    )
                commands.append(command)
                projection.apply(command)
            expected = projection_digest(commands)
            actual = projection.world_digest(world_id)
            if actual != expected:
                raise LadybugRebuildError("ladybug_rebuild_parity_mismatch")
            expected_by_world[world_id] = expected
        projection.verify_connectivity()
    return expected_by_world


__all__ = ["LadybugRebuildError", "rebuild_projection_v1"]
