"""Existing Memory collaborators constructed by the application's runtime."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TYPE_CHECKING
from sqlalchemy.orm import Session

from app.domains.memory.contracts.scope import MemoryScope

if TYPE_CHECKING:
    from app.domains.memory.repository.batch import SqlAlchemyMemoryBatchRepository
    from app.domains.memory.service.inspector import MemoryReadService
    from app.domains.memory.service.items import MemoryWriteLifecycleService
    from app.domains.memory.service.scope import MemoryScopeService


class MemoryOwner(Protocol):
    id: str


@dataclass(frozen=True)
class MemoryWorkflows:
    """Lazy factories and foreign reads using each request's existing Session.

    Provider validation resolves readiness only and never generates on Save.
    Transaction decisions belong to the actual owner-management service.
    """
    read_service: Callable[[Session], MemoryReadService]
    scope_service: Callable[[Session], MemoryScopeService]
    write_service: Callable[[Session], MemoryWriteLifecycleService]
    batch_repository: Callable[[Session], SqlAlchemyMemoryBatchRepository]
    character_names: Callable[[Session, MemoryScope], dict[str, str]]
    validate_provider: Callable[[Session, str, str], None]
