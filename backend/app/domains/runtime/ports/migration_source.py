"""Read-only migration inventory boundary used by transition tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class MigrationRevision:
    revision: str
    down_revision: str | None
    path: str
    sha256: str


@runtime_checkable
class MigrationSourcePort(Protocol):
    def revisions(self) -> tuple[MigrationRevision, ...]: ...


__all__ = ["MigrationRevision", "MigrationSourcePort"]
