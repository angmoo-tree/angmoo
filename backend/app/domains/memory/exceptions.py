"""Stable, privacy-safe failures owned by the memory domain."""


class MemoryDomainError(Exception):
    """Base failure exposed through the memory public facade."""


class MemoryValidationError(MemoryDomainError):
    """A caller supplied a malformed memory contract."""


class MemoryScopeError(MemoryDomainError):
    """The owner, World, and remembering subject do not form one scope."""


class MemoryNotFoundError(MemoryDomainError):
    """A canonical memory scope or row does not exist."""


class MemoryConflictError(MemoryDomainError):
    """A monotonic version or idempotency contract was violated."""


__all__ = [
    "MemoryConflictError",
    "MemoryDomainError",
    "MemoryNotFoundError",
    "MemoryScopeError",
    "MemoryValidationError",
]
