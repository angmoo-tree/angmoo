"""Read results supplied by the caller's existing transaction.

Memory owns invalid-scope and timezone validation. These reads only retrieve
the three identity/World/subject IDs and the World timezone in their old order.
"""
from collections.abc import Callable
from dataclasses import dataclass

from app.domains.memory.contracts.scope import MemoryScope


@dataclass(frozen=True)
class MemoryScopeReferences:
    read_presence: Callable[[MemoryScope], tuple[str | None, str | None, str | None]]
    read_timezone: Callable[[MemoryScope], str | None]
