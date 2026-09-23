"""End-to-end P8-L-P response generation orchestration."""

from __future__ import annotations

import asyncio
import logging
from app.domains.chat.service.social_context_inspector import social_context_inspector as _social_context_inspector
from app.domains.chat.contracts.graph_failure import graph_failure_diagnostic
from app.domains.chat.graph_retry_policy import graph_failure_allows_user_retry
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from dataclasses import replace
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.relationships.contracts.graph_recall import GraphRecallScope
from app.domains.relationships.contracts.social_context import SocialContextProvider, SocialContextChangedError

from app.contracts.retrieval_observation import Observation, current, observe
from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseGeneratorError,
)
from app.domains.chat.contracts.generation_lifecycle import (
    TERMINAL_STATES,
    GenerationContractError,
    GenerationEvent,
    GenerationEventType,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
)
from app.domains.chat.contracts.response_execution import (
    ResponseExecutionError,
    ResponseGraphExecutor,
    ResponseWorkflowCommand,
    initial_response_state,
)
from app.domains.chat.contracts.response_lifecycle import (
    ResponseLifecycleRepositoryPort,
)
from app.domains.chat.contracts.response_request import (
    ResponseCommitPayload,
    ResponseMetadata,
    ResponseRequestRecord,
)
from app.domains.chat.contracts.response_workflow import ResponseWorkflowUnitOfWorkPort
from app.domains.chat.contracts.retrieval_intent import (
    RetrievalContractError,
    RetrievalRoute,
)
from app.domains.chat.contracts.retrieval_router import RouterFailureDiagnostic
from app.domains.chat.contracts.successful_chat_memory import (
    SuccessfulChatMemoryProducerPort,
    SuccessfulChatMemorySource,
)
from app.domains.chat.contracts.today_sns_activity import (
    TodaySnsSnapshotChangedError,
    TodaySnsSnapshotValidatorPort,
)
from app.domains.chat.service.both_retrieval import BothRetrievalWorkflowCoordinator
from app.domains.chat.service.canonical_retrieval import (
    CanonicalRetrievalPlanningService,
)
from app.domains.chat.service.character_response import (
    CharacterResponseGenerationService,
    character_response_deltas,
)
from app.domains.chat.service.diagnostic_capture import capture
from app.contracts.search_diagnostics import trace_payload, lineage
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.service.graph_retrieval import GraphRetrievalPlanningService
from app.domains.chat.service.response_steps import (
    ResponseExecutionProgress,
    ResponseWorkflowSteps,
)
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService

logger = logging.getLogger(__name__)


class ResponseGenerationWorkflowService:
    """Run one durable generation and emit only the CRG public protocol."""

    def __init__(
        self,
        *,
        graph_executor: ResponseGraphExecutor,
        lifecycle: ResponseLifecycleRepositoryPort,
        router: RetrievalRoutingService,
        canonical: CanonicalRetrievalPlanningService,
        graph: GraphRetrievalPlanningService,
        both: BothRetrievalWorkflowCoordinator,
        evidence: EvidenceBundleAssembler,
        character_response: CharacterResponseGenerationService,
        unit_of_work: ResponseWorkflowUnitOfWorkPort,
        memory_producer: SuccessfulChatMemoryProducerPort | None = None,
        today_snapshot_validator: TodaySnsSnapshotValidatorPort | None = None,
        recall_mode: ChatRecallMode = ChatRecallMode.LEGACY,
        social_context_provider: SocialContextProvider | None = None,
    ) -> None:
        self._graph_executor = graph_executor
        self._lifecycle = lifecycle
        self._router = router
        self._canonical = canonical
        self._graph = graph
        self._both = both
        self._evidence = evidence
        self._character_response = character_response
        self._unit_of_work = unit_of_work
        self._memory_producer = memory_producer
        self._today_snapshot_validator = today_snapshot_validator
        self._recall_mode = recall_mode
        self._social_context_provider = social_context_provider

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

        diagnostic_scope = (
            command.preflight.owner_id,
            command.preflight.world_id,
            record.thread_id,
        )
        observation = Observation(
            request_id=record.request_id,
            detailed=capture.active(diagnostic_scope, record.request_id),
        )
        observation_token = current.set(observation)
        observe("search_trace_summary", instrumentation_version="search-diagnostic-trace.v1",
                captured_at_request=observation.detailed)
        observe(
            "request",
            model=record.selected_model,
            thinking_level=record.selected_thinking_level,
        )
        progress = None
        lease_token = f"lease-{uuid4().hex}"
        try:
            if self._recall_mode is not ChatRecallMode.LEGACY:
                if self._social_context_provider is None:
                    raise RetrievalContractError("chat_social_context_provider_required")
                snapshot = self._social_context_provider.prepare(GraphRecallScope(
                    command.preflight.owner_id, command.preflight.world_id,
                    command.preflight.responding_world_character_id,
                ), counterpart_id=command.preflight.requester_world_character_id)
                command = replace(command, recall_mode=self._recall_mode, social_snapshot=snapshot)
                observe("social_context_prepared", snapshot_id="s-"+snapshot.snapshot_id,
                        content_hash="h-"+snapshot.content_hash, status=snapshot.status,
                        candidates=snapshot.candidate_count, excluded=snapshot.excluded_count,
                        items=len(snapshot.items), queries=snapshot.query_count)
            if (
                command.today_sns_snapshot is not None
                and self._today_snapshot_validator is None
            ):
                raise RetrievalContractError(
                    "response_workflow_today_validator_required"
                )
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

            progress = ResponseExecutionProgress(record, record.call_tracker)
            steps = ResponseWorkflowSteps(
                command=command,
                progress=progress,
                save_transition=self._transition,
                router=self._router,
                canonical=self._canonical,
                graph=self._graph,
                both=self._both,
                evidence=self._evidence,
                character_response=self._character_response,
                today_snapshot_validator=self._today_snapshot_validator,
                social_context_provider=self._social_context_provider,
            )
            try:
                state = await self._graph_executor.run(
                    initial_response_state(record), steps
                )
                steps.assert_finished(state)
            finally:
                record = progress.record
            routing = state["routing"]
            route = routing.intent.route
            bundle = state["bundle"]
            response = state["response"]
            workflow_recipe = state["workflow_recipe"]
            record = self._transition(
                record,
                ResponseRequestState.RESPONSE_STREAMING,
                node_state={
                    "character_response_metrics": _character_response_metrics(response)
                },
                call_tracker=response.call_tracker,
            )

            sequence = record.last_emitted_sequence
            if command.social_snapshot is not None:
                self._social_context_provider.assert_current(command.social_snapshot)
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

            if (
                command.today_sns_snapshot is not None
                and self._today_snapshot_validator is not None
            ):
                self._today_snapshot_validator.assert_current(
                    command.today_sns_snapshot
                )
            record = self._transition(record, ResponseRequestState.COMMITTING)
            if command.social_snapshot is not None:
                self._social_context_provider.assert_current(command.social_snapshot)
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
                short_circuited=bundle.retrieval_outcome.value
                in {
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
                    activity_thought=response.activity_thought,
                    relationship_metrics=response.relationship_metrics,
                    model=response.model,
                    metadata=metadata,
                    evidence_inspector_snapshot=bundle.inspector_snapshot(),
                    social_context_inspector_snapshot=_social_context_inspector(command.social_snapshot),
                ),
                now=datetime.now(UTC),
            )
            self._unit_of_work.checkpoint()
            self._propose_memory_after_commit(command, committed)
            yield completed
        except asyncio.CancelledError as exc:
            self._unit_of_work.rollback()
            record = self._after_rollback(record)
            self._cancel_if_active(
                record, tracker=getattr(exc, "call_tracker", None) or (None if progress is None else progress.call_tracker),
                graph_diagnostic=graph_failure_diagnostic(exc),
            )
            raise
        except Exception as exc:
            self._unit_of_work.rollback()
            observe("workflow_failed", status="failed")
            record = self._after_rollback(record)
            async for event in self._fail(
                record, exc, tracker=None if progress is None else progress.call_tracker
            ):
                yield event
        finally:
            try:
                capture.store(diagnostic_scope, record.request_id, observation.details, trace_payload())
            except Exception:
                pass  # Diagnostics cannot change a committed response.
            finally:
                current.reset(observation_token)

    def _after_rollback(self, record: ResponseRequestRecord) -> ResponseRequestRecord:
        """Refresh our own durable sequence; never adopt another lease."""
        latest = self._lifecycle.get_request(record.request_id)
        if (
            latest.generation_id == record.generation_id
            and latest.attempt_number == record.attempt_number
            and latest.lease_token == record.lease_token
            and latest.lease_generation == record.lease_generation
            and latest.request_scope_hash == record.request_scope_hash
        ):
            return latest
        return record

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
        merged_node_state = dict(record.node_state)
        if node_state is not None:
            merged_node_state.update(node_state)
        updated = self._lifecycle.transition(
            self._fence(record),
            target=target,
            route=route,
            workflow_recipe=workflow_recipe,
            node_state=merged_node_state,
            call_tracker=call_tracker,
            now=datetime.now(UTC),
        )
        self._unit_of_work.checkpoint()
        return updated

    async def _fail(
        self,
        record: ResponseRequestRecord,
        exc: Exception,
        *,
        tracker: dict | None = None,
    ) -> AsyncIterator[GenerationEvent]:
        if record.state in TERMINAL_STATES:
            return
        failure_class, retryable, reason = _classify_failure(exc)
        observe(
            "workflow_failed",
            status="failed",
            reason=failure_class,
            validation_code=str(exc)
            if isinstance(exc, ResponseExecutionError)
            else None,
        )
        failure_diagnostic = _provider_failure_diagnostic(exc)
        router_diagnostic = _router_failure_diagnostic(exc)
        if router_diagnostic is not None:
            observe(
                "router_validation",
                status="rejected",
                reason=router_diagnostic.router_validation_code,
                repair_used=router_diagnostic.repair_used,
            )
        if failure_diagnostic is not None:
            failure_diagnostic["failure_class"] = failure_class
            failure_diagnostic["retryable"] = retryable
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
                failure_diagnostic=failure_diagnostic,
                router_diagnostic=router_diagnostic,
                graph_diagnostic=graph_failure_diagnostic(exc, include_sibling=True),
                call_tracker=getattr(exc, "call_tracker", None)
                or tracker
                or record.call_tracker,
                now=datetime.now(UTC),
            )
            self._unit_of_work.checkpoint()
        except Exception:
            self._unit_of_work.rollback()
            raise exc
        yield event

    def _cancel_if_active(
        self, record: ResponseRequestRecord, *, tracker: dict | None = None, graph_diagnostic=None
    ) -> None:
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
                call_tracker=tracker or record.call_tracker,
                graph_diagnostic=graph_diagnostic,
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
    if isinstance(exc, (TodaySnsSnapshotChangedError, SocialContextChangedError)):
        return "source_context_changed", True, ResponseTerminalReason.RETRIEVAL_FAILURE
    if isinstance(exc, CharacterResponseGeneratorError):
        return (
            exc.failure_class,
            exc.retryable,
            ResponseTerminalReason.PROVIDER_FAILURE,
        )
    router_diagnostic = _router_failure_diagnostic(exc)
    if router_diagnostic is not None:
        return (
            "router_schema_rejected",
            router_diagnostic.retryable,
            ResponseTerminalReason.RETRIEVAL_FAILURE,
        )
    if isinstance(exc, RetrievalContractError) and str(exc) == "graph_planner_request_wide_repair_exhausted":
        return (
            "retrieval_rejected",
            graph_failure_allows_user_retry(graph_failure_diagnostic(exc)),
            ResponseTerminalReason.RETRIEVAL_FAILURE,
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


def _provider_failure_diagnostic(exc: BaseException) -> dict[str, Any] | None:
    """Copy a bounded safe diagnostic through wrapped adapter exceptions."""

    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        diagnostic = getattr(current, "provider_diagnostic", None)
        if isinstance(diagnostic, dict):
            return dict(diagnostic)
        current = current.__cause__ or current.__context__
    return None


def _router_failure_diagnostic(
    exc: BaseException,
) -> RouterFailureDiagnostic | None:
    """Copy only the typed domain diagnostic through wrapped exceptions."""

    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        diagnostic = getattr(current, "router_diagnostic", None)
        if isinstance(diagnostic, RouterFailureDiagnostic):
            return diagnostic
        current = current.__cause__ or current.__context__
    return None


def _character_response_metrics(value: Any) -> dict[str, Any]:
    """Persist bounded numeric and enum diagnostics, never generated text."""

    return {
        "provider": value.provider,
        "model": value.model,
        "prompt_token_count": value.prompt_token_count,
        "output_token_count": value.output_token_count,
        "thought_token_count": value.thought_token_count,
        "total_token_count": value.total_token_count,
        "latency_ms": value.latency_ms,
        "thinking_level": value.thinking_level,
        "max_output_tokens": value.max_output_tokens,
        "finish_reason": value.finish_reason,
    }


def _with_sequence(
    record: ResponseRequestRecord,
    sequence: int,
) -> ResponseRequestRecord:
    from dataclasses import replace

    return replace(record, last_emitted_sequence=sequence)


__all__ = ["ResponseGenerationWorkflowService", "ResponseWorkflowCommand"]
