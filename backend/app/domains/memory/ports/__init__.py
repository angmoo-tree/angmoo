"""Ports required by canonical memory application services."""

from app.domains.memory.ports.maintenance_queue import (
    MemoryMaintenanceQueuePort,
    MemoryMaintenanceWorkItem,
)
from app.domains.memory.ports.repository import MemoryRepositoryPort
from app.domains.memory.ports.recall import (
    CanonicalRecallRepositoryPort,
    MemoryRecallIndexPort,
)
from app.domains.memory.ports.source_reader import (
    CanonicalMemoryEvidence,
    MemorySourceEvidenceReaderPort,
)
from app.domains.memory.ports.canonical_planner_provider import (
    MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS,
    CanonicalPlannerEntity,
    CanonicalPlannerOutputError,
    CanonicalPlannerProviderPort,
    CanonicalPlannerProviderResult,
    CanonicalPlannerRelationship,
    CanonicalPlannerRequest,
)
from app.domains.memory.ports.consolidation_provider import (
    MemoryConsolidationProviderError,
    MemoryConsolidationProviderPort,
    MemoryConsolidationProviderRequest,
    MemoryConsolidationProviderResult,
    MemoryConsolidationSource,
)
from app.domains.memory.ports.consolidation_repository import (
    MemoryConsolidationRepositoryPort,
)
from app.domains.memory.ports.maintenance_unit_of_work import (
    MemoryMaintenanceUnitOfWorkPort,
)

__all__ = [
    "CanonicalMemoryEvidence",
    "CanonicalPlannerEntity",
    "CanonicalPlannerOutputError",
    "CanonicalPlannerProviderPort",
    "CanonicalPlannerProviderResult",
    "CanonicalPlannerRelationship",
    "CanonicalPlannerRequest",
    "CanonicalRecallRepositoryPort",
    "MemoryConsolidationProviderError",
    "MemoryConsolidationProviderPort",
    "MemoryConsolidationProviderRequest",
    "MemoryConsolidationProviderResult",
    "MemoryConsolidationRepositoryPort",
    "MemoryConsolidationSource",
    "MemoryMaintenanceQueuePort",
    "MemoryMaintenanceUnitOfWorkPort",
    "MemoryMaintenanceWorkItem",
    "MemoryRepositoryPort",
    "MemoryRecallIndexPort",
    "MemorySourceEvidenceReaderPort",
    "MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS",
]
