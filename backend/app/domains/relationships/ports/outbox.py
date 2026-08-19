"""Claim/finalize boundary for replayable relationship projection work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from app.domains.relationships.projection.commands import ProjectionCommand


OutboxFinalizeStatus = Literal[
    "succeeded",
    "pending",
    "dead",
    "cancelled",
    "lease_lost",
]


@dataclass(frozen=True)
class ProjectionWorkItem:
    id: str
    projection_type: str


@runtime_checkable
class OutboxPort(Protocol):
    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
    ) -> tuple[ProjectionWorkItem, ...]: ...

    def load_command(self, *, outbox_id: str) -> ProjectionCommand: ...

    def finalize_success(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
    ) -> OutboxFinalizeStatus: ...

    def finalize_failure(
        self,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
        error_class: str,
        terminal: bool,
        cancelled: bool = False,
    ) -> OutboxFinalizeStatus: ...


__all__ = ["OutboxFinalizeStatus", "OutboxPort", "ProjectionWorkItem"]
