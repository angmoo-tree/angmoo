"""End-to-end P8-L-P response generation orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
from uuid import uuid4

from app.domains.chat.application.both_retrieval import (
    BothRetrievalCommand,
    BothRetrievalWorkflowCoordinator,
)
from app.domains.chat.application.canonical_retrieval import (
    CanonicalRetrievalCommand,
    CanonicalRetrievalPlanningService,
)
from app.domains.chat.application.character_response import (
    CharacterResponseGenerationService,
    character_response_deltas,
)
from app.domains.chat.application.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.application.generation_lifecycle import GenerationLifecycleService
from app.domains.chat.application.graph_retrieval import (
    GraphRetrievalCommand,
    GraphRetrievalPlanningService,
)
from app.domains.chat.application.retrieval_routing import RetrievalRoutingService
from app.domains.chat.domain.generation_lifecycle import (
    GenerationContractError,
    GenerationEvent,
    GenerationEventType,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
    TERMINAL_STATES,
)
from app.domains.chat.domain.response_request import (
    ResponseCommitPayload,
    ResponseMetadata,
    ResponseRequestRecord,
)
from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalRoute,
)
from app.domains.chat.ports.character_response_generator import (
    CharacterResponseContextMessage,
    CharacterResponseGeneratorError,
    CharacterResponseGeneratorRequest,
    CharacterResponseProfile,
)
from app.domains.chat.ports.response_workflow import ResponseWorkflowUnitOfWorkPort
from app.domains.chat.ports.successful_chat_memory import (
    SuccessfulChatMemoryProducerPort,
    SuccessfulChatMemorySource,
)
from app.domains.chat.ports.retrieval_policy import RetrievalPreflightCommand
from app.domains.chat.ports.retrieval_router_provider import RetrievalRouterContextMessage


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResponseWorkflowCommand:
    request: ResponseRequestRecord
    preflight: RetrievalPreflightCommand
    profile: CharacterResponseProfile
    router_context: tuple[RetrievalRouterContextMessage, ...]
    response_context: tuple[CharacterResponseContextMessage, ...]
    character_labels: Mapping[str, str]
    graph_projection_enabled: bool = True
    lease_seconds: int = 180

    def __post_init__(self) -> None:
        if self.request.request_id != self.preflight.request_id:
            raise RetrievalContractError("response_workflow_request_mismatch")
        if self.request.thread_id != self.preflight.thread_id:
            raise RetrievalContractError("response_workflow_thread_mismatch")
        if not 30 <= self.lease_seconds <= 300:
            raise RetrievalContractError("response_workflow_lease_invalid")


class ResponseGenerationWorkflowService:
    """Run one durable generation and emit only the CRG public protocol."""

    def __init__(
        self,
        *,
        lifecycle: GenerationLifecycleService,
        router: RetrievalRoutingService,
        canonical: CanonicalRetrievalPlanningService,
        graph: GraphRetrievalPlanningService,
        both: BothRetrievalWorkflowCoordinator,
        evidence: EvidenceBundleAssembler,
        character_response: CharacterResponseGenerationService,
        unit_of_work: ResponseWorkflowUnitOfWorkPort,
        memory_producer: SuccessfulChatMemoryProducerPort | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._router = router
        self._canonical = canonical
        self._graph = graph
        self._both = both
        self._evidence = evidence
        self._character_response = character_response
        self._unit_of_work = unit_of_work
        self._memory_producer = memory_producer

    async def run(
        self,
        command: ResponseWorkflowCommand,
    ) -> AsyncIterator[GenerationEvent]:
        record = command.request
        if record.state in TERMINAL_STATES:
            async for event in self._terminal_rehydrate(record):
                yield event
            return
        if record.state is not ResponseRequestState.ACCEPTED:
            raise GenerationContractError("response_workflow_not_replayable")

        lease_token = f"lease-{uuid4().hex}"
        try:
            now = datetime.now(UTC)
            record = self._lifecycle.acquire_lease(
                request_id=record.request_id,
                lease_token=lease_token,
                now=now,
                lease_expires_at=min(
                    record.deadline_at,
                    now + timedelta(seconds=command.lease_seconds),
                ),
            )
            self._unit_of_work.checkpoint()
            fence = self._fence(record)
            accepted = self._event(record, GenerationEventType.ACCEPTED, sequence=0)
            self._lifecycle.accept_event(fence, accepted, now=datetime.now(UTC))
            self._unit_of_work.checkpoint()
            yield accepted

            record = self._transition(record, ResponseRequestState.PREFLIGHTED)
            record = self._transition(record, ResponseRequestState.ROUTING)
            routing = await self._router.route(
                command.preflight,
                recent_context=command.router_context,
                now=datetime.now(UTC),
                deadline_at=record.deadline_at,
            )
            record = self._transition(
                record,
                ResponseRequestState.RESOLVING,
                route=routing.intent.route,
                node_state={
                    "intent_hash": routing.intent.envelope_hash,
                    "resolved_hash": routing.resolved.envelope_hash,
                    "router_metrics": _safe_metrics(routing.metrics),
                },
                call_tracker=routing.call_tracker,
            )

            route = routing.intent.route
            workflow_recipe = None
            if route is RetrievalRoute.CURRENT_CONTEXT:
                record = self._transition(
                    record,
                    ResponseRequestState.CURRENT_CONTEXT_READY,
                )
                bundle = self._evidence.current_context(
                    request_id=record.request_id,
                    request_scope_hash=record.request_scope_hash,
                )
                tracker = routing.call_tracker
            elif route is RetrievalRoute.CLARIFICATION:
                record = self._transition(
                    record,
                    ResponseRequestState.CLARIFICATION_PREPARED,
                )
                clarification = routing.clarification
                if clarification is None:
                    raise RetrievalContractError("response_clarification_missing")
                bundle = self._evidence.clarification(
                    request_id=record.request_id,
                    request_scope_hash=record.request_scope_hash,
                    slot=clarification.slot,
                )
                tracker = routing.call_tracker
            elif route is RetrievalRoute.CANONICAL:
                record = self._transition(
                    record,
                    ResponseRequestState.CANONICAL_PLANNING,
                )
                result = await self._canonical.plan_and_execute(
                    CanonicalRetrievalCommand(
                        user_message=command.preflight.user_message,
                        thread_id=record.thread_id,
                        intent=routing.intent,
                        resolved=routing.resolved,
                        call_tracker=routing.call_tracker,
                    ),
                    now=datetime.now(UTC),
                    deadline_at=record.deadline_at,
                )
                record = self._transition(
                    record,
                    ResponseRequestState.OPTIONAL_RETRIEVING,
                    node_state={"canonical_metrics": _safe_metrics(result.metrics)},
                    call_tracker=result.call_tracker,
                )
                bundle = self._evidence.canonical(
                    request_scope_hash=record.request_scope_hash,
                    result=result,
                )
                tracker = result.call_tracker
            elif route is RetrievalRoute.GRAPH:
                record = self._transition(
                    record,
                    ResponseRequestState.GRAPH_PLANNING,
                )
                result = await self._graph.plan_and_execute(
                    GraphRetrievalCommand(
                        user_message=command.preflight.user_message,
                        intent=routing.intent,
                        resolved=routing.resolved,
                        call_tracker=routing.call_tracker,
                        graph_projection_enabled=command.graph_projection_enabled,
                    ),
                    now=datetime.now(UTC),
                    deadline_at=record.deadline_at,
                )
                record = self._transition(
                    record,
                    ResponseRequestState.OPTIONAL_RETRIEVING,
                    node_state={"graph_metrics": _safe_metrics(result.metrics)},
                    call_tracker=result.call_tracker,
                )
                bundle = self._evidence.graph(
                    request_scope_hash=record.request_scope_hash,
                    result=result,
                    character_labels=command.character_labels,
                )
                tracker = result.call_tracker
            else:
                record = self._transition(
                    record,
                    ResponseRequestState.BOTH_COORDINATING,
                )
                result = await self._both.coordinate(
                    BothRetrievalCommand(
                        user_message=command.preflight.user_message,
                        thread_id=record.thread_id,
                        intent=routing.intent,
                        resolved=routing.resolved,
                        call_tracker=routing.call_tracker,
                        graph_projection_enabled=command.graph_projection_enabled,
                    ),
                    now=datetime.now(UTC),
                    deadline_at=record.deadline_at,
                )
                workflow_recipe = result.selection.selected
                record = self._transition(
                    record,
                    ResponseRequestState.OPTIONAL_RETRIEVING,
                    workflow_recipe=workflow_recipe,
                    node_state={"both_metrics": _safe_metrics(result.metrics)},
                    call_tracker=result.call_tracker,
                )
                bundle = self._evidence.both(
                    request_scope_hash=record.request_scope_hash,
                    result=result,
                    character_labels=command.character_labels,
                )
                tracker = result.call_tracker

            record = self._transition(
                record,
                ResponseRequestState.EVIDENCE_FROZEN,
                workflow_recipe=workflow_recipe,
                node_state={
                    "evidence_version": bundle.version,
                    "evidence_hash": bundle.evidence_hash,
                    "retrieval_outcome": bundle.retrieval_outcome.value,
                    "public_evidence_count": bundle.public_evidence_count,
                },
                call_tracker=tracker,
            )
            tracker = self._character_response.reserve_call(
                call_tracker=tracker,
                now=datetime.now(UTC),
                deadline_at=record.deadline_at,
            )
            record = self._transition(
                record,
                ResponseRequestState.RESPONSE_GENERATING,
                call_tracker=tracker,
            )
            candidates = ()
            if routing.clarification is not None:
                candidates = tuple(
                    f"{candidate.display_name} (@{candidate.handle})"
                    for candidate in routing.clarification.candidates
                )
            response = await self._character_response.generate(
                CharacterResponseGeneratorRequest(
                    user_message=command.preflight.user_message,
                    profile=command.profile,
                    recent_context=command.response_context,
                    evidence=bundle,
                    clarification_candidates=candidates,
                ),
                call_tracker=tracker,
                now=datetime.now(UTC),
                deadline_at=record.deadline_at,
            )
            record = self._transition(
                record,
                ResponseRequestState.RESPONSE_STREAMING,
                call_tracker=response.call_tracker,
            )

            sequence = record.last_emitted_sequence
            for delta in character_response_deltas(response.text):
                sequence += 1
                event = self._event(
                    record,
                    GenerationEventType.DELTA,
                    sequence=sequence,
                    payload={"text": delta},
                )
                self._lifecycle.accept_event(
                    self._fence(record),
                    event,
                    now=datetime.now(UTC),
                )
                self._unit_of_work.checkpoint()
                record = _with_sequence(record, sequence)
                yield event
                await asyncio.sleep(0)

            record = self._transition(record, ResponseRequestState.COMMITTING)
            sequence = record.last_emitted_sequence + 1
            completed = self._event(
                record,
                GenerationEventType.COMPLETED,
                sequence=sequence,
            )
            self._lifecycle.accept_event(
                self._fence(record),
                completed,
                now=datetime.now(UTC),
            )
            record = _with_sequence(record, sequence)
            metadata = ResponseMetadata(
                request_id=record.request_id,
                request_scope_hash=record.request_scope_hash,
                generation_id=record.generation_id,
                attempt_number=record.attempt_number,
                route=route,
                retrieval_outcome=bundle.retrieval_outcome,
                last_accepted_sequence=sequence,
                workflow_recipe=workflow_recipe,
                short_circuited=bundle.retrieval_outcome.value in {
                    "memory_off",
                    "no_evidence",
                },
                partial_axes=bundle.partial_axes,
                public_evidence_count=bundle.public_evidence_count,
                evidence_bundle_version=bundle.version,
                evidence_hash=bundle.evidence_hash,
                evidence_capability=bundle.evidence_capability,
                clarification_slot=bundle.clarification_slot,
                degraded_reason=bundle.degraded_reason,
                retry_of_request_id=record.retry_of_request_id,
            )
            committed = self._lifecycle.finalize(
                self._fence(record),
                ResponseCommitPayload(
                    content=response.text,
                    model=response.model,
                    metadata=metadata,
                ),
                now=datetime.now(UTC),
            )
            self._unit_of_work.checkpoint()
            self._propose_memory_after_commit(command, committed)
            yield completed
        except asyncio.CancelledError:
            self._unit_of_work.rollback()
            self._cancel_if_active(record)
            raise
        except Exception as exc:
            self._unit_of_work.rollback()
            async for event in self._fail(record, exc):
                yield event

    def _propose_memory_after_commit(
        self,
        command: ResponseWorkflowCommand,
        committed: ResponseRequestRecord,
    ) -> None:
        """Keep Memory failure isolated from an already-successful Chat commit."""

        if self._memory_producer is None:
            return
        assistant_message_id = committed.committed_assistant_message_id
        if assistant_message_id is None:
            logger.error(
                "p8_l_p_memory_candidate_missing_assistant request_id=%s",
                committed.request_id,
            )
            return
        try:
            self._memory_producer.propose_after_commit(
                SuccessfulChatMemorySource(
                    request_id=committed.request_id,
                    owner_id=command.preflight.owner_id,
                    world_id=command.preflight.world_id,
                    subject_world_character_id=(
                        command.preflight.responding_world_character_id
                    ),
                    assistant_message_id=assistant_message_id,
                )
            )
        except Exception:
            logger.exception(
                "p8_l_p_memory_candidate_after_commit_failed request_id=%s",
                committed.request_id,
            )

    def _transition(
        self,
        record: ResponseRequestRecord,
        target: ResponseRequestState,
        *,
        route: RetrievalRoute | None = None,
        workflow_recipe=None,
        node_state: dict | None = None,
        call_tracker: dict | None = None,
    ) -> ResponseRequestRecord:
        updated = self._lifecycle.transition(
            self._fence(record),
            target=target,
            route=route,
            workflow_recipe=workflow_recipe,
            node_state=node_state,
            call_tracker=call_tracker,
            now=datetime.now(UTC),
        )
        self._unit_of_work.checkpoint()
        return updated

    async def _fail(
        self,
        record: ResponseRequestRecord,
        exc: Exception,
    ) -> AsyncIterator[GenerationEvent]:
        if record.state in TERMINAL_STATES:
            return
        failure_class, retryable, reason = _classify_failure(exc)
        sequence = record.last_emitted_sequence + 1
        event = self._event(
            record,
            GenerationEventType.FAILED,
            sequence=sequence,
            payload={"failure_class": failure_class, "retryable": retryable},
        )
        try:
            self._lifecycle.accept_event(
                self._fence(record),
                event,
                now=datetime.now(UTC),
            )
            record = _with_sequence(record, sequence)
            self._lifecycle.mark_terminal(
                self._fence(record),
                target=ResponseRequestState.FAILED,
                reason=reason,
                retryable=retryable,
                failure_class=failure_class,
                call_tracker=getattr(exc, "call_tracker", None),
                now=datetime.now(UTC),
            )
            self._unit_of_work.checkpoint()
        except Exception:
            self._unit_of_work.rollback()
            raise exc
        yield event

    def _cancel_if_active(self, record: ResponseRequestRecord) -> None:
        if record.state in TERMINAL_STATES:
            return
        try:
            sequence = record.last_emitted_sequence + 1
            event = self._event(
                record,
                GenerationEventType.CANCELLED,
                sequence=sequence,
                payload={"reason": "client_disconnected"},
            )
            self._lifecycle.accept_event(
                self._fence(record),
                event,
                now=datetime.now(UTC),
            )
            record = _with_sequence(record, sequence)
            self._lifecycle.mark_terminal(
                self._fence(record),
                target=ResponseRequestState.CANCELLED,
                reason=ResponseTerminalReason.USER_CANCELLED,
                retryable=True,
                now=datetime.now(UTC),
            )
            self._unit_of_work.checkpoint()
        except Exception:
            self._unit_of_work.rollback()

    async def _terminal_rehydrate(
        self,
        record: ResponseRequestRecord,
    ) -> AsyncIterator[GenerationEvent]:
        sequence = max(record.last_emitted_sequence, 0)
        if record.state is ResponseRequestState.COMMITTED:
            yield self._event(
                record,
                GenerationEventType.COMPLETED,
                sequence=sequence,
            )
            return
        yield self._event(
            record,
            GenerationEventType.FAILED,
            sequence=sequence,
            payload={
                "failure_class": (
                    record.node_state.get("failure_class")
                    or (
                        "generation_failed"
                        if record.terminal_reason is None
                        else record.terminal_reason.value
                    )
                ),
                "retryable": record.retryable,
            },
        )

    @staticmethod
    def _fence(record: ResponseRequestRecord) -> GenerationFence:
        return GenerationFence(
            request_id=record.request_id,
            thread_id=record.thread_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            lease_generation=record.lease_generation,
            expected_prior_state=record.state,
        )

    @staticmethod
    def _event(
        record: ResponseRequestRecord,
        event_type: GenerationEventType,
        *,
        sequence: int,
        payload: dict[str, Any] | None = None,
    ) -> GenerationEvent:
        return GenerationEvent(
            request_id=record.request_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            sequence=sequence,
            event_type=event_type,
            payload=payload or {},
        )


def _classify_failure(
    exc: Exception,
) -> tuple[str, bool, ResponseTerminalReason]:
    if isinstance(exc, CharacterResponseGeneratorError):
        return (
            exc.failure_class,
            exc.retryable,
            ResponseTerminalReason.PROVIDER_FAILURE,
        )
    text = str(exc).lower()
    retryable = any(
        marker in text
        for marker in ("timeout", "deadline", "unavailable", "orphan", "lease")
    )
    if isinstance(exc, RetrievalContractError):
        reason = ResponseTerminalReason.RETRIEVAL_FAILURE
        failure_class = "retrieval_timeout" if retryable else "retrieval_rejected"
    elif isinstance(exc, GenerationContractError):
        reason = ResponseTerminalReason.CONTRACT_INVALID
        failure_class = "generation_conflict"
    else:
        reason = ResponseTerminalReason.PROVIDER_FAILURE
        failure_class = "generation_failed"
        retryable = True
    return failure_class, retryable, reason


def _safe_metrics(value: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in getattr(value, "__dataclass_fields__", {}):
        item = getattr(value, key)
        if isinstance(item, (str, int, float, bool)) or item is None:
            output[key] = item.value if hasattr(item, "value") else item
        elif isinstance(item, tuple):
            output[key] = [entry.value if hasattr(entry, "value") else entry for entry in item]
    return output


def _with_sequence(
    record: ResponseRequestRecord,
    sequence: int,
) -> ResponseRequestRecord:
    from dataclasses import replace

    return replace(record, last_emitted_sequence=sequence)


__all__ = ["ResponseGenerationWorkflowService", "ResponseWorkflowCommand"]
