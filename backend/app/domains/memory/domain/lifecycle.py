"""Framework-free candidate, item, and lifecycle contracts for Memory v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import hashlib
import re

from app.domains.memory.domain.errors import MemoryValidationError
from app.domains.memory.domain.provenance import (
    MemoryCandidateStatus,
    MemoryItemStatus,
    MemoryKindV1,
    MemorySourceTypeV1,
)
from app.domains.memory.domain.scope import MemoryScope


MEMORY_WRITE_CONTRACT_VERSION = "memory-write.v1"
MAX_MEMORY_SUMMARY_LENGTH = 2_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class MemoryWriteOutcome(str, Enum):
    CREATED = "created"
    REUSED = "reused"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class MemoryCandidateRecord:
    id: str
    scope_setting_id: str
    source_type: MemorySourceTypeV1
    source_id: str
    source_digest: str
    memory_kind_hint: MemoryKindV1
    status: MemoryCandidateStatus
    reason_code: str | None
    idempotency_key: str
    version: int
    created_at: datetime
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class MemoryItemRecord:
    id: str
    scope: MemoryScope
    counterpart_world_character_id: str | None
    thread_id: str | None
    memory_kind: MemoryKindV1
    summary: str
    status: MemoryItemStatus
    confidence: float
    salience: float
    valid_from: datetime
    valid_until: datetime | None
    pinned_at: datetime | None
    superseded_by_id: str | None
    deleted_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    outcome: MemoryWriteOutcome
    code: str
    candidate: MemoryCandidateRecord | None = None
    item: MemoryItemRecord | None = None
    writes: tuple[str, ...] = ()
    provider_call_count: int = 0


_ALLOWED_SOURCE_KINDS: dict[MemorySourceTypeV1, frozenset[MemoryKindV1]] = {
    MemorySourceTypeV1.CHAT_MESSAGE: frozenset(
        {
            MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            MemoryKindV1.THREAD_SUMMARY,
        }
    ),
    MemorySourceTypeV1.OWNER_MEMORY_REQUEST: frozenset(
        {
            MemoryKindV1.OWNER_PREFERENCE,
            MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            MemoryKindV1.THREAD_SUMMARY,
        }
    ),
    MemorySourceTypeV1.POST: frozenset({MemoryKindV1.AUTOBIOGRAPHICAL_EVENT}),
    MemorySourceTypeV1.REPLY: frozenset({MemoryKindV1.AUTOBIOGRAPHICAL_EVENT}),
    MemorySourceTypeV1.REACTION: frozenset(
        {
            MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            MemoryKindV1.DIRECTIONAL_RELATIONSHIP,
        }
    ),
    MemorySourceTypeV1.SOCIAL_EVENT: frozenset(
        {
            MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
            MemoryKindV1.DIRECTIONAL_RELATIONSHIP,
        }
    ),
    MemorySourceTypeV1.ACTIVITY_EVENT: frozenset(
        {MemoryKindV1.AUTOBIOGRAPHICAL_EVENT}
    ),
    MemorySourceTypeV1.RELATIONSHIP_EVENT: frozenset(
        {MemoryKindV1.DIRECTIONAL_RELATIONSHIP}
    ),
    MemorySourceTypeV1.JOINT_COMMITMENT: frozenset(
        {MemoryKindV1.ACCEPTED_JOINT_COMMITMENT}
    ),
}


def validate_source_kind(
    *, source_type: MemorySourceTypeV1, memory_kind: MemoryKindV1
) -> None:
    if memory_kind not in _ALLOWED_SOURCE_KINDS[source_type]:
        raise MemoryValidationError("memory_source_kind_not_allowed")


def normalize_memory_summary(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > MAX_MEMORY_SUMMARY_LENGTH:
        raise MemoryValidationError("memory_summary_invalid")
    return normalized


def validate_source_digest(value: str) -> str:
    normalized = value.strip().lower()
    if _SHA256_RE.fullmatch(normalized) is None:
        raise MemoryValidationError("memory_source_digest_invalid")
    return normalized


def memory_candidate_idempotency_key(
    *,
    scope: MemoryScope,
    source_type: MemorySourceTypeV1,
    source_id: str,
    memory_kind: MemoryKindV1,
    contract_version: str = MEMORY_WRITE_CONTRACT_VERSION,
) -> str:
    normalized_source_id = normalize_memory_source_id(source_id)
    material = "\x1f".join(
        (
            contract_version,
            source_type.value,
            normalized_source_id,
            scope.owner_id,
            scope.world_id,
            scope.subject_world_character_id,
            memory_kind.value,
        )
    )
    return f"mw1:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def normalize_memory_source_id(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise MemoryValidationError("memory_source_id_invalid")
    return normalized


def normalize_memory_idempotency_key(value: str) -> str:
    """Validate a retry-safe opaque owner mutation key.

    The key is deliberately restricted to a small ASCII alphabet so it can be
    hashed into an internal correction item identity without ever becoming
    user-visible content or provenance.
    """

    normalized = value.strip()
    if _IDEMPOTENCY_KEY_RE.fullmatch(normalized) is None:
        raise MemoryValidationError("memory_idempotency_key_invalid")
    return normalized


def memory_correction_item_id(
    *,
    scope: MemoryScope,
    old_item_id: str,
    idempotency_key: str,
) -> str:
    """Derive the stable internal identity used for correction replay."""

    item_id = normalize_memory_source_id(old_item_id)
    key = normalize_memory_idempotency_key(idempotency_key)
    material = "\x1f".join(
        (
            MEMORY_WRITE_CONTRACT_VERSION,
            "owner-correction",
            scope.owner_id,
            scope.world_id,
            scope.subject_world_character_id,
            item_id,
            key,
        )
    )
    return f"mcor-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:48]}"


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "MAX_MEMORY_SUMMARY_LENGTH",
    "MEMORY_WRITE_CONTRACT_VERSION",
    "MemoryCandidateRecord",
    "MemoryItemRecord",
    "MemoryWriteOutcome",
    "MemoryWriteResult",
    "as_utc",
    "memory_candidate_idempotency_key",
    "memory_correction_item_id",
    "normalize_memory_idempotency_key",
    "normalize_memory_source_id",
    "normalize_memory_summary",
    "validate_source_digest",
    "validate_source_kind",
]
