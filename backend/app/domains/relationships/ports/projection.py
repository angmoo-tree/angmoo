"""Write boundary implemented by Neo4j today and LadybugDB after ER3."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domains.relationships.projection.commands import ProjectionCommand


class RelationshipProjectionBackendError(RuntimeError):
    """Retryable projection backend failure without provider-specific details."""

    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class


@runtime_checkable
class RelationshipProjectionPort(Protocol):
    def apply(
        self,
        command: ProjectionCommand,
        *,
        timeout_seconds: float = 5.0,
    ) -> str: ...


__all__ = [
    "RelationshipProjectionBackendError",
    "RelationshipProjectionPort",
]
