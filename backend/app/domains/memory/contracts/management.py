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


class ConsolidationFollowup(Protocol):
    """Runtime-owned collaborator; methods share the caller's transaction."""
    def admit(self, scope: MemoryScope, row) -> None: ...
    def active(self, setting_id: str): ...
    def extend(self, row, value: dict) -> dict: ...
    def capability(self, scope: MemoryScope) -> dict: ...
    def retry(self, scope: MemoryScope, row) -> None: ...


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
    validate_embedding_credential: Callable[[Session, str, str], None] | None = None
    embedding_credential_options: Callable[[Session, str, str | None], list[dict[str, str]]] | None = None
    consolidation_followup: Callable[[Session], ConsolidationFollowup] | None = None
    embedding_runtime_status: Callable[[], str] | None = None
