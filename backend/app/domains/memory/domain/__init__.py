"""Framework-free memory domain contracts."""

from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryDomainError,
    MemoryNotFoundError,
    MemoryScopeError,
    MemoryValidationError,
)
from app.domains.memory.domain.policies import validate_memory_item_shape
from app.domains.memory.domain.provenance import (
    MemoryCandidateStatus,
    MemoryHotBriefStatus,
    MemoryItemStatus,
    MemoryJobStatus,
    MemoryKindV1,
    MemoryProviderMode,
    MemorySourceTypeV1,
)
from app.domains.memory.domain.retention import (
    DEFAULT_MEMORY_RETENTION_DAYS,
    is_memory_expired,
    validate_retention_days,
)
from app.domains.memory.domain.scope import (
    MemoryScope,
    MemoryScopeSetting,
)

__all__ = [
    "DEFAULT_MEMORY_RETENTION_DAYS",
    "MemoryCandidateStatus",
    "MemoryConflictError",
    "MemoryDomainError",
    "MemoryHotBriefStatus",
    "MemoryItemStatus",
    "MemoryJobStatus",
    "MemoryKindV1",
    "MemoryNotFoundError",
    "MemoryProviderMode",
    "MemoryScope",
    "MemoryScopeError",
    "MemoryScopeSetting",
    "MemorySourceTypeV1",
    "MemoryValidationError",
    "is_memory_expired",
    "validate_memory_item_shape",
    "validate_retention_days",
]
