"""Construct worker collaborators without starting work or opening a Session."""
from app.runtime.memory.scope_queries import read_due_batch_configs
from app.domains.memory.contracts.batch_preparation import MemoryPreparationDependencies
from app.runtime.memory.composition import memory_repository, memory_batch_repository, memory_consolidation_repository
from app.runtime.memory.sqlalchemy_source_reader import SqlAlchemyMemorySourceEvidenceReader


def build_preparation_dependencies() -> MemoryPreparationDependencies:
    return MemoryPreparationDependencies(
        memory_repository=memory_repository,
        batch_repository=memory_batch_repository,
        consolidation_repository=memory_consolidation_repository,
        source_reader=SqlAlchemyMemorySourceEvidenceReader,
        read_due_configs=read_due_batch_configs,
    )
