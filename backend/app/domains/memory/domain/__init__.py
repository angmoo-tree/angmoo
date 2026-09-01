"""Framework-free memory domain contracts."""

from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryDomainError,
    MemoryNotFoundError,
    MemoryScopeError,
    MemoryValidationError,
)
from app.domains.memory.domain.lifecycle import (
    MAX_MEMORY_SUMMARY_LENGTH,
    MEMORY_WRITE_CONTRACT_VERSION,
    MemoryCandidateRecord,
    MemoryItemRecord,
    MemoryWriteOutcome,
    MemoryWriteResult,
    as_utc,
    memory_candidate_idempotency_key,
    normalize_memory_source_id,
    normalize_memory_summary,
    validate_source_digest,
    validate_source_kind,
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
    "MAX_MEMORY_SUMMARY_LENGTH",
    "MEMORY_WRITE_CONTRACT_VERSION",
    "MemoryCandidateRecord",
    "MemoryCandidateStatus",
    "MemoryConflictError",
    "MemoryDomainError",
    "MemoryHotBriefStatus",
    "MemoryItemStatus",
    "MemoryItemRecord",
    "MemoryJobStatus",
    "MemoryKindV1",
    "MemoryNotFoundError",
    "MemoryProviderMode",
    "MemoryScope",
    "MemoryScopeError",
    "MemoryScopeSetting",
    "MemorySourceTypeV1",
    "MemoryValidationError",
    "MemoryWriteOutcome",
    "MemoryWriteResult",
    "as_utc",
    "is_memory_expired",
    "memory_candidate_idempotency_key",
    "normalize_memory_source_id",
    "normalize_memory_summary",
    "validate_source_digest",
    "validate_source_kind",
    "validate_memory_item_shape",
    "validate_retention_days",
]
