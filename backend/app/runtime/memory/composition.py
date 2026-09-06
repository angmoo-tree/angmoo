"""Construct Memory stores against the caller's one existing transaction."""
from functools import partial

from sqlalchemy.orm import Session

from app.domains.memory.contracts.scope_references import MemoryScopeReferences
from app.domains.memory.repository.items import SqlAlchemyMemoryRepository
from app.domains.memory.repository.batch import SqlAlchemyMemoryBatchRepository
from app.domains.memory.repository.consolidation import SqlAlchemyMemoryConsolidationRepository
from app.runtime.memory.scope_queries import read_scope_presence, read_scope_timezone


def scope_references(session: Session) -> MemoryScopeReferences:
    return MemoryScopeReferences(
        read_presence=partial(read_scope_presence, session),
        read_timezone=partial(read_scope_timezone, session),
    )


def memory_repository(session: Session) -> SqlAlchemyMemoryRepository:
    return SqlAlchemyMemoryRepository(session, references=scope_references(session))


def memory_batch_repository(session: Session) -> SqlAlchemyMemoryBatchRepository:
    return SqlAlchemyMemoryBatchRepository(session, references=scope_references(session))


def memory_consolidation_repository(session: Session) -> SqlAlchemyMemoryConsolidationRepository:
    return SqlAlchemyMemoryConsolidationRepository(session, references=scope_references(session))
