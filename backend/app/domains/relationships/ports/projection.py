"""Write boundary implemented by Neo4j today and LadybugDB after ER3."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domains.relationships.projection.commands import ProjectionCommand


@runtime_checkable
class RelationshipProjectionPort(Protocol):
    def apply(
        self,
        command: ProjectionCommand,
        *,
        timeout_seconds: float = 5.0,
    ) -> str: ...


__all__ = ["RelationshipProjectionPort"]
