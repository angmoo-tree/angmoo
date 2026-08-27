"""Version-scoped semantic contracts for embedded SQLite migrations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection


class SqliteMigrationDeltaError(RuntimeError):
    """Stable, redacted failure for an unexpected migration data delta."""


@dataclass(frozen=True)
class SqliteMigrationContract:
    """Expected data changes owned by one consecutive migration step."""

    source_version: int
    target_version: int
    name: str
    mutable_identity_tables: frozenset[str]
    capture: Callable[[Connection], Any]
    verify: Callable[[Connection, Any], None]


__all__ = [
    "SqliteMigrationContract",
    "SqliteMigrationDeltaError",
]
