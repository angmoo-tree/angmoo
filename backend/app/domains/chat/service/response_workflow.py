"""End-to-end P8-L-P response generation orchestration."""

from __future__ import annotations
from app.core.work_observation import scope as observation_scope, contextual

import asyncio
from anyio import CancelScope
import logging
from hashlib import sha256
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
from app.contracts.search_diagnostics import trace_payload
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
        situation_memory=None,
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
        self._situation_memory = situation_memory

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
            # Own the response before validating its stored input, so a damaged
            # admitted packet can be durably terminated under the same CAS.
            now = datetime.now(UTC)
            record = await self._database_unit(lambda: self._lifecycle.acquire_lease(
                request_id=record.request_id,
                lease_token=lease_token,
                now=now,
                lease_expires_at=min(
                    record.deadline_at,
                    now + timedelta(seconds=command.lease_seconds),
                ),
            ), lifecycle_only=True)
            from app.domains.chat.contracts.initial_input import INPUT_KEY, restore as restore_initial_input, assert_available
            assert_available(record.node_state)
            input_restored = INPUT_KEY in record.node_state
            if input_restored:
                command = restore_initial_input(command, record.node_state[INPUT_KEY])
            from app.contracts.name_binding import read_name_binding, NameBindingError
            from app.domains.characters.service.prompt_persona import request_persona, request_activity_thought
            name_binding = read_name_binding(record.node_state)
            from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext
            identity = ChatIdentityContext.read(record.node_state)
            if identity is not None:
                identity.assert_scope(command.preflight.owner_id, command.preflight.world_id, record.thread_id,
                    command.preflight.requester_world_character_id, command.preflight.responding_world_character_id)
                if name_binding is None:
                    raise NameBindingError("chat_identity_binding_missing")
                if identity.requester.name != ChatIdentityContext.from_binding(name_binding, record.thread_id).requester.name or identity.responder.name != ChatIdentityContext.from_binding(name_binding, record.thread_id).responder.name:
                    raise NameBindingError("chat_identity_binding_mismatch")
                command = replace(command, chat_identity=identity,
                    character_labels={**command.character_labels, **identity.names})
                bind_labels = getattr(self._social_context_provider, "bind_labels", None)
                if bind_labels:
                    bind_labels(identity.names)
                bind_today = getattr(self._today_snapshot_validator, "bind_labels", None)
                if bind_today:
                    bind_today(command.character_labels)
            if name_binding is not None:
                if (name_binding.owner_id, name_binding.world_id, name_binding.actor_world_character_id,
                    name_binding.user_world_character_id) != (command.preflight.owner_id, command.preflight.world_id,
                    command.preflight.responding_world_character_id, command.preflight.requester_world_character_id):
                    raise NameBindingError("name_binding_scope_invalid")
                if command.name_binding_validator:
                    await self._call_database(command.name_binding_validator)
                persona = request_persona(command.profile, name_binding)
                if not input_restored:
                    command = replace(command, profile=replace(command.profile,
                        name=persona["name"], worldview=persona["description"],
                        **{key: persona[key] for key in ("one_liner", "personality", "speech_style",
                            "character_background", "topic_preferences", "safety_rules")}))
                observe("name_binding", policy_version=name_binding.policy_version,
                    binding_digest=name_binding.digest, profile_version=name_binding.user_profile_version,
                    fields=persona["name_binding"]["fields"])
            if self._recall_mode is not ChatRecallMode.LEGACY:
                if self._social_context_provider is None:
                    raise RetrievalContractError("chat_social_context_provider_required")
                if input_restored and command.social_snapshot is None:
                    raise RetrievalContractError("chat_initial_social_input_unavailable")
                snapshot = command.social_snapshot or await self._call_database(lambda: self._social_context_provider.prepare(GraphRecallScope(
                    command.preflight.owner_id, command.preflight.world_id,
                    command.preflight.responding_world_character_id,
                ), counterpart_id=command.preflight.requester_world_character_id))
                command = replace(command, recall_mode=self._recall_mode, social_snapshot=snapshot)
                if identity is not None:
                    identity = identity.extend({item.relationship.target_world_character_id: item.display_name for item in snapshot.items})
                    command = replace(command, chat_identity=identity)
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
            fence = self._fence(record)
            accepted = self._event(record, GenerationEventType.ACCEPTED, sequence=0)
            await self._database_unit(lambda: self._lifecycle.accept_event(fence, accepted, now=datetime.now(UTC)), lifecycle_only=True)
            yield accepted

            progress = ResponseExecutionProgress(record, record.call_tracker)
            thought_finalizer = None
            if name_binding is not None:
                def thought_finalizer(value):
                    return request_activity_thought(value, name_binding,
                        recipient_id=command.preflight.requester_world_character_id)
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
                thought_finalizer=thought_finalizer,
                situation_memory=self._situation_memory,
                database_call=self._call_database,
                database_unit=self._database_unit,
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
            # Provider waits end the earlier read snapshot. Reject stale memory
            # dependencies before emitting response text, then recheck after the
            # streaming awaits immediately before the final persistence UoW.
            await progress.assert_memories_current(bundle)
            if name_binding is not None:
                from app.domains.characters.service.prompt_persona import render_names
                if command.name_binding_validator:
                    await self._call_database(command.name_binding_validator)
                rendered = render_names(response.text, name_binding, output=True,
                    recipient_id=command.preflight.requester_world_character_id, limit=16000)
                response = replace(response, text=rendered.text)
                observe("name_binding_output", policy_version=name_binding.policy_version,
                    binding_digest=name_binding.digest,
                    before_sha256=sha256(state["response"].text.encode()).hexdigest(),
                    final_sha256=sha256(response.text.encode()).hexdigest(),
                    applied=rendered.replacements > 0, **rendered.receipt())
            workflow_recipe = state["workflow_recipe"]
            record = await self._transition(
                record,
                ResponseRequestState.RESPONSE_STREAMING,
                node_state={
                    "character_response_metrics": _character_response_metrics(response),
                    **({"_relationship_delivery_capture": {
                        "digest": response.relationship_delivery["digest"],
                        "payload_digest": response.relationship_delivery["payload_digest"],
                        "prompt_digest": response.relationship_delivery["prompt_digest"],
                    }} if response.relationship_delivery is not None else {}),
                },
                call_tracker=response.call_tracker,
            )

            sequence = record.last_emitted_sequence
            if command.social_snapshot is not None:
                await self._call_database(lambda: self._social_context_provider.assert_usable(command.social_snapshot))
            for delta in character_response_deltas(response.text):
                sequence += 1
                event = self._event(
                    record,
                    GenerationEventType.DELTA,
                    sequence=sequence,
                    payload={"text": delta},
                )
                await self._database_unit(lambda: self._lifecycle.accept_event(
                    self._fence(record),
                    event,
                    now=datetime.now(UTC),
                ), lifecycle_only=True)
                record = _with_sequence(record, sequence)
                yield event
                await asyncio.sleep(0)

            # Today is reference content captured for this response. New SNS
            # events, midnight or edits do not change that delivered input.
            record = await self._transition(record, ResponseRequestState.COMMITTING)
            await progress.assert_memories_current(bundle)
            committing_record = record
            def persist_response():
                record = committing_record
                if command.name_binding_validator:
                    command.name_binding_validator()
                if command.social_snapshot is not None:
                    self._social_context_provider.assert_usable(command.social_snapshot)
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
                        relationship_delivery=response.relationship_delivery,
                    ),
                    now=datetime.now(UTC),
                )
                if self._situation_memory is not None:
                    self._situation_memory.admit(command, committed, response)
                return committed, completed
            with observation_scope(chat_stage="response_finalize"):
                committed, completed = await self._database_unit(persist_response)
            record = committed
            after_commit = getattr(self._unit_of_work, "response_committed", None)
            if after_commit is not None:
                await self._call_database(lambda: after_commit(committed.request_id))
            if command.request.node_state.get("_situation_policy") is None:
                with observation_scope(chat_stage="post_commit"):
                    await self._call_database(lambda: self._propose_memory_after_commit(command, committed))
            yield completed
        except asyncio.CancelledError as exc:
            def settle_cancellation():
                self._unit_of_work.rollback()
                current_record = self._after_rollback(record)
                self._cancel_if_active(
                    current_record, tracker=getattr(exc, "call_tracker", None) or (None if progress is None else progress.call_tracker),
                    graph_diagnostic=graph_failure_diagnostic(exc),
                )
                return current_record
            # A disconnected HTTP stream cancels every subsequent await in its
            # AnyIO scope. Finish this finite DB-only cleanup before propagating
            # cancellation. One handoff also survives repeated Task.cancel():
            # session_call drains the whole rollback/fence/terminal-save unit.
            with observation_scope(chat_stage="cancel_or_failure"), CancelScope(shield=True):
                record = await self._call_database(settle_cancellation)
            raise
        except Exception as exc:
            with observation_scope(chat_stage="cancel_or_failure"):
                await self._call_database(self._unit_of_work.rollback)
            observe("workflow_failed", status="failed")
            record = await self._call_database(lambda: self._after_rollback(record))
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

    async def _transition(
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
        updated = await self._database_unit(lambda: self._lifecycle.transition(
            self._fence(record),
            target=target,
            route=route,
            workflow_recipe=workflow_recipe,
            node_state=merged_node_state,
            call_tracker=call_tracker,
            now=datetime.now(UTC),
        ), lifecycle_only=True)
        return updated

    async def _call_database(self, operation):
        call = getattr(self._unit_of_work, "call", None)
        return await call(operation) if call is not None else operation()

    async def _database_unit(self, operation, *, lifecycle_only=False):
        return await self._call_database(lambda: self._run_database_unit(operation, lifecycle_only=lifecycle_only))

    def _run_database_unit(self, operation, *, lifecycle_only=False):
        # The opt-in is restricted to existing request-row CAS operations.
        # Message/relationship/memory finalization uses the default owner.
        run = getattr(self._unit_of_work, "run_lifecycle_unit", None) if lifecycle_only else None
        run = run or getattr(self._unit_of_work, "run_database_unit", None)
        if run is not None:
            return run(operation)
        result = operation()
        self._unit_of_work.checkpoint()
        return result

    @contextual(chat_stage="cancel_or_failure")
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
        target = ResponseRequestState.FAILED
        if datetime.now(UTC) >= record.deadline_at:
            target = ResponseRequestState.TIMED_OUT
            failure_class, retryable = "deadline_exceeded", True
            reason = ResponseTerminalReason.DEADLINE_EXCEEDED
        facts = _safe_failure_facts(exc)
        logger.warning("chat_workflow_failed request_id=%s state=%s error=%s sqlstate=%s sites=%s",
            record.request_id, record.state.value, facts["error_class"], facts["sqlstate"], facts["sites"])
        observe(
            "workflow_failed",
            status="failed",
            reason=failure_class,
            failure_code=facts["error_class"],
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
        failed_record = record
        def persist_failure():
            record = failed_record
            self._lifecycle.accept_event(
                self._fence(record),
                event,
                now=datetime.now(UTC),
            )
            record = _with_sequence(record, sequence)
            self._lifecycle.mark_terminal(
                self._fence(record),
                target=target,
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
            if self._situation_memory is not None:
                # Memory delivery has failed/cancelled outcomes; the Chat
                # lifecycle separately carries its more specific timed_out state.
                self._situation_memory.record_terminal(record,"failed",reason=failure_class)
        try:
            await self._database_unit(persist_failure, lifecycle_only=True)
        except Exception:
            await self._call_database(self._unit_of_work.rollback)
            raise exc
        yield event

    @contextual(chat_stage="cancel_or_failure")
    def _cancel_if_active(
        self, record: ResponseRequestRecord, *, tracker: dict | None = None, graph_diagnostic=None
    ) -> None:
        if record.state in TERMINAL_STATES:
            return
        cancelled_record = record
        def persist_cancel():
            record = cancelled_record
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
            if self._situation_memory is not None:
                self._situation_memory.record_terminal(record,"cancelled",reason="client_disconnected")
        try:
            self._run_database_unit(persist_cancel, lifecycle_only=True)
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
    from app.contracts.name_binding import NameBindingError
    from app.domains.chat.contracts.recall_currentness import RecallEvidenceChanged
    from app.domains.chat.exceptions import ChatSituationEvidenceError
    from app.domains.relationships.contracts.social_context import SocialContextValidationError
    from app.core.postgresql_concurrency import PostgresCommitOutcomeUnknown
    from app.core.sqlite_concurrency import is_sqlite_contention
    from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout
    if isinstance(exc, RetrievalContractError) and str(exc).startswith("chat_initial_"):
        # Repeating a request cannot recover an absent or corrupt admitted
        # input. Never offer an endless retry that silently seeks fresher data.
        return "initial_input_unavailable", False, ResponseTerminalReason.CONTRACT_INVALID
    if isinstance(exc, PostgresCommitOutcomeUnknown):
        return "storage_commit_uncertain", False, ResponseTerminalReason.COMMIT_CONFLICT
    if is_sqlite_contention(exc) or isinstance(exc, PoolTimeout):
        return "storage_unavailable", True, ResponseTerminalReason.COMMIT_CONFLICT
    if isinstance(exc, DBAPIError):
        return "storage_failure", False, ResponseTerminalReason.COMMIT_CONFLICT
    if isinstance(exc, ChatSituationEvidenceError):
        return "situation_evidence_contract_invalid", False, ResponseTerminalReason.CONTRACT_INVALID
    if isinstance(exc, SocialContextValidationError):
        if exc.reason == "visibility_lost":
            return "social_context_access_revoked", False, ResponseTerminalReason.POLICY_DENIED
        if exc.reason in {"canonical_database_busy", "canonical_read_deadline", "canonical_read_error", "canonical_database_error"}:
            return "storage_unavailable", True, ResponseTerminalReason.RETRIEVAL_FAILURE
        return "initial_input_invalid", False, ResponseTerminalReason.CONTRACT_INVALID
    if isinstance(exc, RecallEvidenceChanged):
        return "source_context_changed", True, ResponseTerminalReason.RETRIEVAL_FAILURE
    if isinstance(exc, NameBindingError):
        return str(exc), True, ResponseTerminalReason.CONTRACT_INVALID
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


def _safe_failure_facts(exc: BaseException) -> dict:
    """Structural evidence only; never stringify SQL, parameters or provider text."""
    import re
    current, seen, sites, state = exc, set(), [], None
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        raw = getattr(getattr(current, "orig", current), "sqlstate", None)
        if isinstance(raw, str) and re.fullmatch(r"[A-Z0-9]{5}", raw):
            state = state or raw
        trace = current.__traceback__
        while trace is not None:
            path = trace.tb_frame.f_code.co_filename.replace("\\", "/")
            if "/app/" in path:
                sites.append(f"{path.rsplit('/app/',1)[1]}:{trace.tb_lineno}:{trace.tb_frame.f_code.co_name}")
            trace = trace.tb_next
        current = current.__cause__ or current.__context__
    return {"error_class": type(exc).__name__, "sqlstate": state, "sites": sites[-8:]}


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
