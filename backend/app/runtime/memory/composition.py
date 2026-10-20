"""Construct Memory stores against the caller's one existing transaction."""
from functools import partial

from sqlalchemy.orm import Session

from app.domains.memory.contracts.scope_references import MemoryScopeReferences
from app.domains.memory.repository.items import SqlAlchemyMemoryRepository
from app.domains.memory.repository.batch import SqlAlchemyMemoryBatchRepository
from app.domains.memory.repository.consolidation import SqlAlchemyMemoryConsolidationRepository
from app.runtime.memory.scope_queries import read_scope_presence, read_scope_timezone, read_consolidation_binding


def scope_references(session: Session) -> MemoryScopeReferences:
    return MemoryScopeReferences(
        read_presence=partial(read_scope_presence, session),
        read_timezone=partial(read_scope_timezone, session),
        read_consolidation_binding=partial(read_consolidation_binding, session),
        read_consolidation_revision=partial(read_consolidation_binding, session),
    )


def memory_repository(session: Session) -> SqlAlchemyMemoryRepository:
    return SqlAlchemyMemoryRepository(session, references=scope_references(session))


def search_preparation_settings(session, owner_id, world_id, actor_id):
    """Read current saved settings only; never creates a setting or resolves keys."""
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
    scope = MemoryScope(owner_id, world_id, actor_id)
    repository = memory_repository(session)
    repository.validate_scope(scope)
    setting = repository.get_scope_setting(scope)
    if setting is None or not setting.enabled:
        return False, False
    return True, MemoryEmbeddingRepository(session, repository).read(scope).enabled


def memory_batch_repository(session: Session) -> SqlAlchemyMemoryBatchRepository:
    return SqlAlchemyMemoryBatchRepository(session, references=scope_references(session))


def memory_consolidation_repository(session: Session) -> SqlAlchemyMemoryConsolidationRepository:
    from app.runtime.memory.source_composition import source_evidence_reader
    return SqlAlchemyMemoryConsolidationRepository(session, references=scope_references(session), source_reader=source_evidence_reader(session))
