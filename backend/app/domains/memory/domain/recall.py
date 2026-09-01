"""Framework-free contracts for bounded canonical Memory recall."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from app.domains.memory.domain.provenance import MemorySourceTypeV1
from app.domains.memory.domain.scope import MemoryScope


MEMORY_RECALL_CONTRACT_VERSION = "memory-recall.v1"
MEMORY_RECALL_GENERATION = "v1"
MEMORY_RECALL_SCHEMA_VERSION = 1
MAX_CANONICAL_RECALL_RESULTS = 50


class CanonicalRecallOperation(StrEnum):
    SEARCH_THREAD_MESSAGES = "search_thread_messages"
    SEARCH_POSTS = "search_posts"
    SEARCH_MEMORY_ITEMS = "search_memory_items"
    LIST_SOCIAL_EVENTS = "list_social_events"
    CANONICAL_EVENT_DETAILS = "canonical_event_details"
    GET_POST_THREAD = "get_post_thread"
    LIST_ACTIVITY_EPISODES = "list_activity_episodes"
    LIST_RELATIONSHIP_CHANGES = "list_relationship_changes"
    GET_CHARACTER_SUMMARIES = "get_character_summaries"


class RecallDocumentKind(StrEnum):
    THREAD_MESSAGE = "thread_message"
    OWNER_MEMORY_REQUEST = "owner_memory_request"
    POST = "post"
    REPLY = "reply"
    REACTION = "reaction"
    MEMORY_ITEM = "memory_item"
    SOCIAL_EVENT = "social_event"
    ACTIVITY_EVENT = "activity_event"
    RELATIONSHIP_EVENT = "relationship_event"
    JOINT_COMMITMENT = "joint_commitment"
    CHARACTER_SUMMARY = "character_summary"


class CanonicalRecallStatus(StrEnum):
    READY = "ready"
    DISABLED = "disabled"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class MemoryRecallDocument:
    document_id: str
    memory_item_id: str
    owner_id: str
    world_id: str
    subject_world_character_id: str
    kind: RecallDocumentKind
    canonical_source_id: str
    text: str
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None
    source_type: MemorySourceTypeV1 | None = None
    source_event_id: str | None = None
    occurred_at: datetime | None = None
    searchable: bool = True
    tombstoned_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryRecallSearchQuery:
    scope: MemoryScope
    text: str
    kinds: tuple[RecallDocumentKind, ...]
    limit: int
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecallCandidate:
    document_id: str
    memory_item_id: str
    kind: RecallDocumentKind
    canonical_source_id: str
    score: float
    snippet: str
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None
    source_type: MemorySourceTypeV1 | None = None
    source_event_id: str | None = None
    occurred_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalRecallRecord:
    reference: str
    kind: RecallDocumentKind
    canonical_source_id: str
    text: str
    occurred_at: datetime
    memory_item_id: str | None = None
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None
    source_type: MemorySourceTypeV1 | None = None
    source_event_id: str | None = None
    evidence_references: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalRecallQuery:
    operation: CanonicalRecallOperation
    scope: MemoryScope
    text: str | None = None
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None
    source_references: tuple[str, ...] = ()
    world_character_references: tuple[str, ...] = ()
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class CanonicalRecallResult:
    operation: CanonicalRecallOperation
    status: CanonicalRecallStatus
    records: tuple[CanonicalRecallRecord, ...]
    candidate_count: int = 0
    excluded_count: int = 0
    truncated: bool = False
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryRecallDoctor:
    database_path: str
    generation: str
    schema_version: int
    fts5_available: bool
    integrity_check: str
    document_count: int
    searchable_document_count: int
    indexed_document_count: int
    tombstone_count: int
    digest: str
    digest_matches: bool
    rollback_available: bool
    healthy: bool
    tokenizer_strategy: str


SOURCE_KIND_BY_TYPE = {
    MemorySourceTypeV1.CHAT_MESSAGE: RecallDocumentKind.THREAD_MESSAGE,
    MemorySourceTypeV1.OWNER_MEMORY_REQUEST: RecallDocumentKind.OWNER_MEMORY_REQUEST,
    MemorySourceTypeV1.POST: RecallDocumentKind.POST,
    MemorySourceTypeV1.REPLY: RecallDocumentKind.REPLY,
    MemorySourceTypeV1.REACTION: RecallDocumentKind.REACTION,
    MemorySourceTypeV1.SOCIAL_EVENT: RecallDocumentKind.SOCIAL_EVENT,
    MemorySourceTypeV1.ACTIVITY_EVENT: RecallDocumentKind.ACTIVITY_EVENT,
    MemorySourceTypeV1.RELATIONSHIP_EVENT: RecallDocumentKind.RELATIONSHIP_EVENT,
    MemorySourceTypeV1.JOINT_COMMITMENT: RecallDocumentKind.JOINT_COMMITMENT,
}


__all__ = [
    "CanonicalRecallOperation",
    "CanonicalRecallQuery",
    "CanonicalRecallRecord",
    "CanonicalRecallResult",
    "CanonicalRecallStatus",
    "MAX_CANONICAL_RECALL_RESULTS",
    "MEMORY_RECALL_CONTRACT_VERSION",
    "MEMORY_RECALL_GENERATION",
    "MEMORY_RECALL_SCHEMA_VERSION",
    "MemoryRecallCandidate",
    "MemoryRecallDoctor",
    "MemoryRecallDocument",
    "MemoryRecallSearchQuery",
    "RecallDocumentKind",
    "SOURCE_KIND_BY_TYPE",
]
