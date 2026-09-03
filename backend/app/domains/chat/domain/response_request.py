"""Canonical response-attempt value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import hashlib
import json
from typing import Any

from app.domains.chat.domain.generation_lifecycle import (
    CHAT_GENERATION_STREAM_VERSION,
    ResponseRequestState,
    ResponseTerminalReason,
)
from app.domains.chat.domain.retrieval_intent import RetrievalRoute
from app.domains.chat.domain.workflow_recipe import WorkflowRecipe


def build_request_scope_hash(
    *,
    owner_id: str,
    world_id: str,
    thread_id: str,
    user_message_id: int,
    requester_world_character_id: str,
    responding_world_character_id: str,
) -> str:
    payload = {
        "owner_id": owner_id,
        "world_id": world_id,
        "thread_id": thread_id,
        "user_message_id": user_message_id,
        "requester_world_character_id": requester_world_character_id,
        "responding_world_character_id": responding_world_character_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class RetrievalOutcome(StrEnum):
    CURRENT_CONTEXT = "current_context"
    MEMORY_USED = "memory_used"
    RELATIONSHIP_USED = "relationship_used"
    BOTH_USED = "both_used"
    CLARIFICATION_REQUIRED = "clarification_required"
    NO_EVIDENCE = "no_evidence"
    MEMORY_OFF = "memory_off"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNVERIFIABLE = "unverifiable"


class RetrievalAxis(StrEnum):
    CANONICAL = "canonical"
    GRAPH = "graph"


class DegradedReason(StrEnum):
    CANONICAL_UNAVAILABLE = "canonical_unavailable"
    GRAPH_UNAVAILABLE = "graph_unavailable"
    RETRIEVAL_TIMEOUT = "retrieval_timeout"
    NO_ACCEPTED_EVIDENCE = "no_accepted_evidence"


class EvidenceCapability(StrEnum):
    NONE = "none"
    AVAILABLE = "available"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ResponseMetadata:
    request_id: str
    request_scope_hash: str
    generation_id: str
    attempt_number: int
    route: RetrievalRoute
    retrieval_outcome: RetrievalOutcome
    last_accepted_sequence: int
    workflow_recipe: WorkflowRecipe | None = None
    short_circuited: bool = False
    partial_axes: tuple[RetrievalAxis, ...] = ()
    public_evidence_count: int = 0
    evidence_bundle_version: str | None = None
    evidence_hash: str | None = None
    evidence_capability: EvidenceCapability = EvidenceCapability.NONE
    clarification_slot: str | None = None
    degraded_reason: DegradedReason | None = None
    retry_of_request_id: str | None = None
    node_diagnostic_refs: tuple[str, ...] = ()
    terminal_state: ResponseRequestState = ResponseRequestState.COMMITTED
    stream_protocol_version: str = CHAT_GENERATION_STREAM_VERSION

    def __post_init__(self) -> None:
        if any(
            not value
            for value in (
                self.request_id,
                self.request_scope_hash,
                self.generation_id,
            )
        ):
            raise ValueError("response_metadata_identity_missing")
        if len(self.request_scope_hash) != 64 or self.attempt_number < 1:
            raise ValueError("response_metadata_identity_invalid")
        if self.last_accepted_sequence < -1:
            raise ValueError("response_metadata_sequence_invalid")
        if self.terminal_state is not ResponseRequestState.COMMITTED:
            raise ValueError("response_metadata_terminal_state_invalid")
        if self.stream_protocol_version != CHAT_GENERATION_STREAM_VERSION:
            raise ValueError("response_metadata_protocol_invalid")
        if not 0 <= self.public_evidence_count <= 100:
            raise ValueError("response_metadata_evidence_count_invalid")
        if (self.evidence_bundle_version is None) != (self.evidence_hash is None):
            raise ValueError("response_metadata_evidence_identity_incomplete")
        if self.evidence_bundle_version is not None and (
            len(self.evidence_bundle_version) > 64
            or not self.evidence_bundle_version.strip()
            or self.evidence_hash is None
            or len(self.evidence_hash) != 64
        ):
            raise ValueError("response_metadata_evidence_identity_invalid")
        if (
            self.evidence_capability is not EvidenceCapability.NONE
            and self.evidence_bundle_version is None
        ):
            raise ValueError("response_metadata_evidence_capability_unbound")
        if (
            self.evidence_capability is EvidenceCapability.AVAILABLE
            and self.public_evidence_count == 0
        ):
            raise ValueError("response_metadata_evidence_capability_empty")
        if len(set(self.partial_axes)) != len(self.partial_axes):
            raise ValueError("response_metadata_partial_axis_duplicate")
        if len(self.node_diagnostic_refs) > 4 or any(
            not value or len(value) > 96 for value in self.node_diagnostic_refs
        ):
            raise ValueError("response_metadata_diagnostic_ref_invalid")
        if self.route is RetrievalRoute.BOTH and self.workflow_recipe is None:
            raise ValueError("response_metadata_both_recipe_required")
        if self.route is not RetrievalRoute.BOTH and self.workflow_recipe is not None:
            raise ValueError("response_metadata_recipe_forbidden")
        if (
            self.retrieval_outcome is RetrievalOutcome.CLARIFICATION_REQUIRED
        ) != (self.route is RetrievalRoute.CLARIFICATION):
            raise ValueError("response_metadata_clarification_route_mismatch")
        if self.degraded_reason is not None and self.retrieval_outcome not in {
            RetrievalOutcome.DEGRADED,
            RetrievalOutcome.NO_EVIDENCE,
        }:
            raise ValueError("response_metadata_degraded_reason_forbidden")

    def payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_scope_hash": self.request_scope_hash,
            "generation_id": self.generation_id,
            "attempt_number": self.attempt_number,
            "route": self.route.value.lower(),
            "retrieval_outcome": self.retrieval_outcome.value,
            "workflow_recipe": (
                None if self.workflow_recipe is None else self.workflow_recipe.value
            ),
            "short_circuited": self.short_circuited,
            "partial_axes": [axis.value for axis in self.partial_axes],
            "public_evidence_count": self.public_evidence_count,
            "evidence_bundle_version": self.evidence_bundle_version,
            "evidence_hash": self.evidence_hash,
            "evidence_capability": self.evidence_capability.value,
            "clarification_slot": self.clarification_slot,
            "degraded_reason": (
                None if self.degraded_reason is None else self.degraded_reason.value
            ),
            "retry_of_request_id": self.retry_of_request_id,
            "terminal_state": self.terminal_state.value,
            "stream_protocol_version": self.stream_protocol_version,
            "last_accepted_sequence": self.last_accepted_sequence,
            "node_diagnostic_refs": list(self.node_diagnostic_refs),
        }


@dataclass(frozen=True, slots=True)
class CreateResponseRequest:
    request_id: str
    thread_id: str
    user_message_id: int
    response_slot_id: str
    request_scope_hash: str
    idempotency_key: str
    generation_id: str
    attempt_number: int
    selected_model: str
    deadline_at: datetime
    retry_of_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResponseRequestRecord:
    request_id: str
    thread_id: str
    user_message_id: int
    response_slot_id: str
    request_scope_hash: str
    idempotency_key: str
    generation_id: str
    attempt_number: int
    selected_model: str
    deadline_at: datetime
    state: ResponseRequestState
    lease_generation: int = 0
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    retry_of_request_id: str | None = None
    route: RetrievalRoute | None = None
    workflow_recipe: WorkflowRecipe | None = None
    last_emitted_sequence: int = -1
    terminal_reason: ResponseTerminalReason | None = None
    retryable: bool = False
    committed_assistant_message_id: int | None = None
    node_state: dict[str, Any] = field(default_factory=dict)
    call_tracker: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    terminal_at: datetime | None = None
    cancel_requested_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResponseCommitPayload:
    content: str
    model: str
    metadata: ResponseMetadata
    evidence_inspector_snapshot: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("response_commit_content_empty")
        if not self.model.strip():
            raise ValueError("response_commit_model_empty")


__all__ = [
    "CreateResponseRequest",
    "DegradedReason",
    "EvidenceCapability",
    "ResponseCommitPayload",
    "ResponseMetadata",
    "ResponseRequestRecord",
    "RetrievalAxis",
    "RetrievalOutcome",
    "build_request_scope_hash",
]
