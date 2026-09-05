"""Existing same-Session storage and canonical source-read collaborators."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from sqlalchemy.orm import Session

from app.domains.memory.contracts.source_evidence import MemorySourceEvidenceReaderPort

if TYPE_CHECKING:
    from app.domains.memory.models.batch import MemoryBatchSetting
    from app.domains.memory.repository.items import SqlAlchemyMemoryRepository
    from app.domains.memory.repository.batch import SqlAlchemyMemoryBatchRepository
    from app.domains.memory.repository.consolidation import SqlAlchemyMemoryConsolidationRepository


@dataclass(frozen=True)
class MemoryPreparationDependencies:
    memory_repository: Callable[[Session], SqlAlchemyMemoryRepository]
    batch_repository: Callable[[Session], SqlAlchemyMemoryBatchRepository]
    consolidation_repository: Callable[[Session], SqlAlchemyMemoryConsolidationRepository]
    source_reader: Callable[[Session], MemorySourceEvidenceReaderPort]
    read_due_configs: Callable[..., list[MemoryBatchSetting]]
