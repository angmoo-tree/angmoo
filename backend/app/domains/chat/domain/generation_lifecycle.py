"""Framework-free generation lifecycle, fencing, and stream sequencing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


CHAT_GENERATION_STREAM_VERSION = "chat-generation-stream.v1"


class GenerationContractError(RuntimeError):
    """Stable fail-closed lifecycle error."""


class ResponseRequestState(StrEnum):
    ACCEPTED = "accepted"
    LEASE_ACQUIRED = "lease_acquired"
    PREFLIGHTED = "preflighted"
    ROUTING = "routing"
    RESOLVING = "resolving"
    CURRENT_CONTEXT_READY = "current_context_ready"
    CANONICAL_PLANNING = "canonical_planning"
    GRAPH_PLANNING = "graph_planning"
    BOTH_COORDINATING = "both_coordinating"
    CLARIFICATION_PREPARED = "clarification_prepared"
    OPTIONAL_RETRIEVING = "optional_retrieving"
    EVIDENCE_FROZEN = "evidence_frozen"
    RESPONSE_GENERATING = "response_generating"
    RESPONSE_STREAMING = "response_streaming"
    COMMITTING = "committing"
    COMMITTED = "committed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    ORPHANED = "orphaned"


TERMINAL_STATES = frozenset(
    {
        ResponseRequestState.COMMITTED,
        ResponseRequestState.REJECTED,
        ResponseRequestState.CANCELLED,
        ResponseRequestState.TIMED_OUT,
        ResponseRequestState.FAILED,
        ResponseRequestState.ORPHANED,
    }
)


class ResponseTerminalReason(StrEnum):
    COMMITTED = "committed"
    POLICY_DENIED = "policy_denied"
    ENTITY_AMBIGUOUS = "entity_ambiguous"
    USER_CANCELLED = "user_cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    PROVIDER_FAILURE = "provider_failure"
    RETRIEVAL_FAILURE = "retrieval_failure"
    CONTRACT_INVALID = "contract_invalid"
    LEASE_LOST = "lease_lost"
    ORPHAN_RECOVERED = "orphan_recovered"
    COMMIT_CONFLICT = "commit_conflict"


class GenerationEventType(StrEnum):
    ACCEPTED = "accepted"
    DELTA = "delta"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SequenceOutcome(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


_ROUTE_READY_STATES = frozenset(
    {
        ResponseRequestState.CURRENT_CONTEXT_READY,
        ResponseRequestState.CANONICAL_PLANNING,
        ResponseRequestState.GRAPH_PLANNING,
        ResponseRequestState.BOTH_COORDINATING,
        ResponseRequestState.CLARIFICATION_PREPARED,
    }
)


_TRANSITIONS: dict[ResponseRequestState, frozenset[ResponseRequestState]] = {
    ResponseRequestState.ACCEPTED: frozenset(
        {
            ResponseRequestState.LEASE_ACQUIRED,
            ResponseRequestState.REJECTED,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
        }
    ),
    ResponseRequestState.LEASE_ACQUIRED: frozenset(
        {
            ResponseRequestState.PREFLIGHTED,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
            ResponseRequestState.ORPHANED,
        }
    ),
    ResponseRequestState.PREFLIGHTED: frozenset(
        {
            ResponseRequestState.ROUTING,
            ResponseRequestState.REJECTED,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.ROUTING: frozenset(
        {
            ResponseRequestState.RESOLVING,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.RESOLVING: _ROUTE_READY_STATES
    | frozenset(
        {
            ResponseRequestState.REJECTED,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.CURRENT_CONTEXT_READY: frozenset(
        {ResponseRequestState.EVIDENCE_FROZEN}
    ),
    ResponseRequestState.CANONICAL_PLANNING: frozenset(
        {
            ResponseRequestState.OPTIONAL_RETRIEVING,
            ResponseRequestState.EVIDENCE_FROZEN,
        }
    ),
    ResponseRequestState.GRAPH_PLANNING: frozenset(
        {
            ResponseRequestState.OPTIONAL_RETRIEVING,
            ResponseRequestState.EVIDENCE_FROZEN,
        }
    ),
    ResponseRequestState.BOTH_COORDINATING: frozenset(
        {
            ResponseRequestState.OPTIONAL_RETRIEVING,
            ResponseRequestState.EVIDENCE_FROZEN,
        }
    ),
    ResponseRequestState.CLARIFICATION_PREPARED: frozenset(
        {ResponseRequestState.EVIDENCE_FROZEN}
    ),
    ResponseRequestState.OPTIONAL_RETRIEVING: frozenset(
        {
            ResponseRequestState.EVIDENCE_FROZEN,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.EVIDENCE_FROZEN: frozenset(
        {
            ResponseRequestState.RESPONSE_GENERATING,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.RESPONSE_GENERATING: frozenset(
        {
            ResponseRequestState.RESPONSE_STREAMING,
            ResponseRequestState.COMMITTING,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.RESPONSE_STREAMING: frozenset(
        {
            ResponseRequestState.COMMITTING,
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    ),
    ResponseRequestState.COMMITTING: frozenset(
        {ResponseRequestState.COMMITTED, ResponseRequestState.FAILED}
    ),
}


for _state in (
    ResponseRequestState.CURRENT_CONTEXT_READY,
    ResponseRequestState.CANONICAL_PLANNING,
    ResponseRequestState.GRAPH_PLANNING,
    ResponseRequestState.BOTH_COORDINATING,
    ResponseRequestState.CLARIFICATION_PREPARED,
):
    _TRANSITIONS[_state] = _TRANSITIONS[_state] | frozenset(
        {
            ResponseRequestState.CANCELLED,
            ResponseRequestState.TIMED_OUT,
            ResponseRequestState.FAILED,
        }
    )


@dataclass(frozen=True, slots=True)
class GenerationFence:
    request_id: str
    thread_id: str
    request_scope_hash: str
    generation_id: str
    attempt_number: int
    lease_generation: int
    expected_prior_state: ResponseRequestState

    def __post_init__(self) -> None:
        if any(
            not value
            for value in (
                self.request_id,
                self.thread_id,
                self.request_scope_hash,
                self.generation_id,
            )
        ):
            raise GenerationContractError("generation_fence_identity_missing")
        if len(self.request_scope_hash) != 64:
            raise GenerationContractError("generation_fence_scope_hash_invalid")
        if self.attempt_number < 1 or self.lease_generation < 0:
            raise GenerationContractError("generation_fence_counter_invalid")


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    request_id: str
    request_scope_hash: str
    generation_id: str
    attempt_number: int
    sequence: int
    event_type: GenerationEventType
    payload: dict[str, Any] = field(default_factory=dict)
    protocol_version: str = CHAT_GENERATION_STREAM_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != CHAT_GENERATION_STREAM_VERSION:
            raise GenerationContractError("generation_event_protocol_mismatch")
        if self.sequence < 0:
            raise GenerationContractError("generation_event_sequence_invalid")
        keys = set(self.payload)
        if self.event_type in {
            GenerationEventType.ACCEPTED,
            GenerationEventType.COMPLETED,
        }:
            if keys:
                raise GenerationContractError("generation_event_payload_forbidden")
        elif self.event_type is GenerationEventType.DELTA:
            if keys != {"text"}:
                raise GenerationContractError("generation_delta_payload_invalid")
            text = self.payload.get("text")
            if not isinstance(text, str) or not text or len(text) > 16_000:
                raise GenerationContractError("generation_delta_text_invalid")
        elif self.event_type is GenerationEventType.FAILED:
            if keys != {"failure_class", "retryable"}:
                raise GenerationContractError("generation_failed_payload_invalid")
            if (
                not isinstance(self.payload.get("failure_class"), str)
                or not self.payload["failure_class"]
                or len(self.payload["failure_class"]) > 64
                or not isinstance(self.payload.get("retryable"), bool)
            ):
                raise GenerationContractError("generation_failed_payload_invalid")
        elif self.event_type is GenerationEventType.CANCELLED:
            if keys != {"reason"}:
                raise GenerationContractError("generation_cancelled_payload_invalid")
            reason = self.payload.get("reason")
            if not isinstance(reason, str) or not reason or len(reason) > 64:
                raise GenerationContractError("generation_cancelled_payload_invalid")


def validate_transition(
    current: ResponseRequestState,
    target: ResponseRequestState,
) -> None:
    if current in TERMINAL_STATES:
        raise GenerationContractError("generation_terminal_state_immutable")
    if target not in _TRANSITIONS.get(current, frozenset()):
        raise GenerationContractError(
            f"generation_transition_invalid:{current.value}_to_{target.value}"
        )


def validate_event_sequence(
    fence: GenerationFence,
    event: GenerationEvent,
    *,
    last_emitted_sequence: int,
) -> SequenceOutcome:
    if (
        event.request_id != fence.request_id
        or event.request_scope_hash != fence.request_scope_hash
        or event.generation_id != fence.generation_id
        or event.attempt_number != fence.attempt_number
    ):
        raise GenerationContractError("generation_event_scope_mismatch")
    if event.sequence == last_emitted_sequence:
        return SequenceOutcome.DUPLICATE
    if event.sequence != last_emitted_sequence + 1:
        raise GenerationContractError("generation_event_sequence_gap_or_reversal")
    return SequenceOutcome.ACCEPTED


__all__ = [
    "CHAT_GENERATION_STREAM_VERSION",
    "GenerationContractError",
    "GenerationEvent",
    "GenerationEventType",
    "GenerationFence",
    "ResponseRequestState",
    "ResponseTerminalReason",
    "SequenceOutcome",
    "TERMINAL_STATES",
    "validate_event_sequence",
    "validate_transition",
]
