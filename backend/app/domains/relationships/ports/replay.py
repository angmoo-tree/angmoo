"""Canonical replay-source port for rebuilding relationship projections."""

from __future__ import annotations

from typing import Protocol

from app.domains.relationships.projection.commands import ProjectionCommand


class ProjectionReplaySource(Protocol):
    def world_ids(self) -> tuple[str, ...]: ...

    def commands_for_world(
        self,
        world_id: str,
    ) -> tuple[ProjectionCommand, ...]: ...


__all__ = ["ProjectionReplaySource"]
