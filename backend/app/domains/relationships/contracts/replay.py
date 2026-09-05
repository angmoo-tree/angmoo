"""Canonical replay-source port for rebuilding relationship projections."""

from __future__ import annotations

from typing import Protocol
from app.domains.relationships.contracts.projection import RelationshipProjectionPort

from app.domains.relationships.contracts.projection_commands import (ProjectionCommand)


class ProjectionReplaySource(Protocol):
    def world_ids(self) -> tuple[str, ...]: ...

    def commands_for_world(
        self,
        world_id: str,
    ) -> tuple[ProjectionCommand, ...]: ...


__all__ = ["ProjectionReplaySource"]


class ReplayStore(RelationshipProjectionPort, Protocol):
    def clear_world(self, world_id: str) -> None: ...

    def world_digest(self, world_id: str) -> dict[str, list[str]]: ...
