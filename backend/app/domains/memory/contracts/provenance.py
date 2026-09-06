"""Version-one canonical memory vocabulary.

The stored values are intentionally closed.  Adding a kind or source requires
an explicit contract/migration decision instead of accepting arbitrary LLM
output as a database enum.
"""

from enum import Enum


class _ClosedValue(str, Enum):
    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(item.value for item in cls)


class MemoryKindV1(_ClosedValue):
    OWNER_PREFERENCE = "OWNER_PREFERENCE"
    AUTOBIOGRAPHICAL_EVENT = "AUTOBIOGRAPHICAL_EVENT"
    DIRECTIONAL_RELATIONSHIP = "DIRECTIONAL_RELATIONSHIP"
    THREAD_SUMMARY = "THREAD_SUMMARY"
    ACCEPTED_JOINT_COMMITMENT = "ACCEPTED_JOINT_COMMITMENT"


class MemorySourceTypeV1(_ClosedValue):
    CHAT_MESSAGE = "CHAT_MESSAGE"
    OWNER_MEMORY_REQUEST = "OWNER_MEMORY_REQUEST"
    POST = "POST"
    REPLY = "REPLY"
    REACTION = "REACTION"
    SOCIAL_EVENT = "SOCIAL_EVENT"
    ACTIVITY_EVENT = "ACTIVITY_EVENT"
    RELATIONSHIP_EVENT = "RELATIONSHIP_EVENT"
    JOINT_COMMITMENT = "JOINT_COMMITMENT"


class MemoryProviderMode(_ClosedValue):
    NONE = "none"
    OPTIONAL_CONFIGURED = "optional-configured"


class MemoryCandidateStatus(_ClosedValue):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MemoryItemStatus(_ClosedValue):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class MemoryHotBriefStatus(_ClosedValue):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"


class MemoryJobStatus(_ClosedValue):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


__all__ = [
    "MemoryCandidateStatus",
    "MemoryHotBriefStatus",
    "MemoryItemStatus",
    "MemoryJobStatus",
    "MemoryKindV1",
    "MemoryProviderMode",
    "MemorySourceTypeV1",
]
