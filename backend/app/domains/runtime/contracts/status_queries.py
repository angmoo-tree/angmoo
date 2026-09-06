"""Named canonical queries; all callbacks share the original request Session."""

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RuntimeStatusQueries:
    migration_revision: Callable[[str], Any]
    owner_state: Callable[[], Any]
    registered_world_count: Callable[[str], Any]
    active_world_count: Callable[[str], Any]
    active_world_character_count: Callable[[str], Any]
    scheduler_state: Callable[[], Any]
    projection_counts: Callable[[], Any]
    recent_runs: Callable[[str, datetime], Any]
    rollback: Callable[[], None]
