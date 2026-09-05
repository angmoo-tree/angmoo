"""Ports required by canonical memory application services."""

from app.domains.memory.contracts.maintenance_queue import (
    MemoryMaintenanceQueuePort,
    MemoryMaintenanceWorkItem,
)
from app.domains.memory.contracts.item_store import MemoryRepositoryPort
from app.domains.memory.contracts.recall_store import (
    CanonicalRecallRepositoryPort,
    MemoryRecallIndexPort,
)
from app.domains.memory.contracts.source_evidence import (
    CanonicalMemoryEvidence,
    MemorySourceEvidenceReaderPort,
)
from app.domains.memory.contracts.planner_provider import (
    MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS,
    CanonicalPlannerEntity,
    CanonicalPlannerOutputError,
    CanonicalPlannerProviderPort,
    CanonicalPlannerProviderResult,
    CanonicalPlannerRelationship,
    CanonicalPlannerRequest,
)
from app.domains.memory.contracts.consolidation_provider import (
    MemoryConsolidationProviderError,
    MemoryConsolidationProviderPort,
    MemoryConsolidationProviderRequest,
    MemoryConsolidationProviderResult,
    MemoryConsolidationSource,
)
from app.domains.memory.contracts.consolidation_store import (
    MemoryConsolidationRepositoryPort,
)
from app.domains.memory.contracts.maintenance_transaction import (
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
