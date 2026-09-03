from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.chat.api.schemas import (
    MessageSettingsUpdate,
    WorldChatMessageCreate,
    WorldChatRetryCreate,
)
from app.domains.chat.application.both_retrieval import (
    BothRetrievalResult,
    WorkflowCoordinatorMetrics,
)
from app.domains.chat.application.canonical_retrieval import (
    CanonicalPlanningMetrics,
    CanonicalPlanningResult,
)
from app.domains.chat.application.character_response import (
    CharacterResponseGenerationService,
)
from app.domains.chat.application.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.application.generation_lifecycle import GenerationLifecycleService
from app.domains.chat.application.graph_retrieval import (
    GraphPlanningMetrics,
    GraphPlanningResult,
)
from app.domains.chat.application.response_workflow import (
    ResponseGenerationWorkflowService,
    ResponseWorkflowCommand,
)
from app.domains.chat.application.retrieval_routing import (
    ClarificationCandidate,
    ClarificationResolution,
    RetrievalRoutingMetrics,
    RetrievalRoutingResult,
)
from app.domains.chat.domain.call_tracker import (
    LlmNode,
    RouteAwareCallTracker,
    restore_call_tracker_snapshot,
)
from app.domains.chat.domain.evidence_bundle import (
    EVIDENCE_BUNDLE_VERSION,
    EvidenceItem,
    EvidenceKind,
    opaque_evidence_reference,
)
from app.domains.chat.domain.generation_lifecycle import (
    GenerationEventType,
    GenerationFence,
    ResponseRequestState,
    ResponseTerminalReason,
)
from app.domains.chat.domain.resolved_envelope import (
    ResolvedRetrievalEnvelope,
    RetrievalHardCaps,
)
from app.domains.chat.domain.response_request import (
    CreateResponseRequest,
    EvidenceCapability,
    RetrievalAxis,
    RetrievalOutcome,
    build_request_scope_hash,
)
from app.domains.chat.domain.retrieval_intent import (
    RetrievalDecision,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)
from app.domains.chat.domain.retrieval_router import (
    RetrievalRouterRepairExhaustedError,
    RouterFailureDiagnostic,
)
from app.domains.chat.domain.workflow_recipe import (
    WorkflowAxis,
    WorkflowRecipe,
    select_workflow_recipe,
)
from app.domains.chat.infrastructure.response_lifecycle_repository import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.domains.chat.ports.character_response_generator import (
    CharacterResponseGeneratorError,
    CharacterResponseGeneratorResult,
    CharacterResponseProfile,
)
from app.domains.chat.ports.successful_chat_memory import SuccessfulChatMemorySource
from app.domains.chat.ports.retrieval_policy import RetrievalPreflightCommand
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from app.domains.memory.public import (
    CANONICAL_PRIMITIVE_REGISTRY,
    MemoryScope,
    MemoryScopeService,
)
from app.domains.relationships.public import GRAPH_RECALL_PRIMITIVE_REGISTRY
from app.runtime.chat.world_generation import (
    accept_world_message,
    get_world_response_request,
    retry_world_response,
)
from app.runtime.chat.memory_producer import SqlAlchemySuccessfulChatMemoryProducer
from app.runtime.chat import sqlalchemy_service as world_chat


NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        display_name_normalized=user_id,
        profile_setup_completed=True,
    )


def _character(character_id: str, owner_id: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=character_id,
        handle=character_id,
        one_liner="fixture",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="chat",
        safety_rules="safe",
        status="active",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


@pytest.fixture
def response_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    owner = _user("p-owner")
    responder_owner = _user("p-responder-owner")
    requester_character = _character("p-requester-character", owner.id)
    responding_character = _character("p-responding-character", responder_owner.id)
    world = models.World(
        id="p-world",
        slug="p-world",
        owner_user_id=owner.id,
        name="P World",
        tagline="",
        setting_description="",
        daily_life_description="",
        genre_tags=[],
        tone_tags=[],
        timezone="Asia/Seoul",
        language="ko",
        visibility="private",
        join_policy="private",
        status="published",
        contract_version="world-v1",
        contract_hash="b" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="p-world",
    )
    owner_membership = models.WorldMembership(
        id="p-owner-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=NOW,
    )
    responder_membership = models.WorldMembership(
        id="p-responder-membership",
        world_id=world.id,
        user_id=responder_owner.id,
        role="member",
        status="active",
        joined_at=NOW,
    )
    requester = models.WorldCharacter(
        id="p-requester",
        world_id=world.id,
        character_id=requester_character.id,
        membership_id=owner_membership.id,
        role_key="no_specific_role",
        status="active",
        control_mode="owner_controlled",
        owner_user_id=owner.id,
        autonomous_enabled=False,
        version=1,
    )
    responding = models.WorldCharacter(
        id="p-responding",
        world_id=world.id,
        character_id=responding_character.id,
        membership_id=responder_membership.id,
        role_key="no_specific_role",
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
        version=1,
    )
    session.add_all([owner, responder_owner])
    session.flush()
    session.add(
        models.InstallationIdentity(
            singleton_key="local-installation",
            installation_id="p8-l-p-installation",
            owner_user_id=owner.id,
            bootstrap_state="claimed",
            local_label="P8-L-P fixture",
            claimed_at=NOW,
        )
    )
    session.add_all([requester_character, responding_character, world])
    session.flush()
    session.add_all([owner_membership, responder_membership])
    session.flush()
    session.add_all([requester, responding])
    session.flush()
    session.add(
        models.UserMessagePreference(
            user_id=owner.id,
            default_model="gemini-3.1-flash-lite",
        )
    )
    session.flush()
    thread = models.MessageThread(
        id="p-thread",
        requester_id=owner.id,
        character_id=responding_character.id,
        world_id=world.id,
        requester_world_character_id=requester.id,
        responding_world_character_id=responding.id,
        world_scope_status="resolved",
        # Simulate a thread created before the user changed their global
        # default.  The default binding must resolve 3.1 at acceptance time.
        selected_model="gemini-2.5-flash-lite",
        model_binding_mode="default",
    )
    session.add(thread)
    session.flush()
    session.add(
        models.MessageMessage(
            thread_id=thread.id,
            role="user",
            content="오늘은 어땠어?",
            status="ok",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _intent(route: RetrievalRoute) -> RetrievalIntentEnvelope:
    if route is RetrievalRoute.CURRENT_CONTEXT:
        return RetrievalIntentEnvelope(
            decision=RetrievalDecision.CURRENT_CONTEXT,
            route=route,
            intent="smalltalk",
        )
    if route is RetrievalRoute.CLARIFICATION:
        return RetrievalIntentEnvelope(
            decision=RetrievalDecision.CLARIFICATION,
            route=route,
            intent="ambiguous_reference",
            clarification_slot="counterpart",
        )
    return RetrievalIntentEnvelope(
        decision=RetrievalDecision.RETRIEVAL,
        route=route,
        intent="mixed_evidence" if route is RetrievalRoute.BOTH else "historical_recall",
        coordination_hint=(
            WorkflowRecipe.INDEPENDENT_PARALLEL.value
            if route is RetrievalRoute.BOTH
            else None
        ),
    )


def _resolved(intent: RetrievalIntentEnvelope, request_id: str) -> ResolvedRetrievalEnvelope:
    return ResolvedRetrievalEnvelope.bind_intent(
        intent,
        request_id=request_id,
        owner_id="p-owner",
        world_id="p-world",
        requester_world_character_id="p-requester",
        responding_world_character_id="p-responding",
        entity_bindings=(),
        relationship_from_world_character_id=None,
        relationship_to_world_character_id=None,
        absolute_time_from=None,
        absolute_time_to=None,
        memory_enabled=True,
        canonical_operation_allowlist=tuple(
            operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY
        ),
        graph_operation_allowlist=tuple(
            operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY
        ),
        caps=RetrievalHardCaps(),
    )


class _Router:
    def __init__(self, route: RetrievalRoute) -> None:
        self.route_name = route
        self.calls = 0

    async def route(self, command, *, recent_context, now, deadline_at):
        del recent_context
        self.calls += 1
        intent = _intent(self.route_name)
        tracker = RouteAwareCallTracker(route=self.route_name, deadline_at=deadline_at)
        tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=now)
        tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=now)
        clarification = None
        if self.route_name is RetrievalRoute.CLARIFICATION:
            clarification = ClarificationResolution(
                slot="counterpart",
                candidates=(
                    ClarificationCandidate(
                        ref="candidate-1",
                        display_name="철수",
                        handle="cheolsu",
                    ),
                ),
            )
        return RetrievalRoutingResult(
            intent=intent,
            resolved=_resolved(intent, command.request_id),
            clarification=clarification,
            metrics=RetrievalRoutingMetrics(
                route=self.route_name,
                first_pass_valid=True,
                repair_used=False,
                rejected=False,
                clarification=clarification is not None,
                entity_resolution_outcome="not_required",
                direction_resolution_outcome="not_required",
                time_resolution_outcome="not_required",
                router_logical_calls=1,
                router_physical_attempts=1,
                provider="fixture",
                model="fixture-router",
            ),
            call_tracker=tracker.snapshot(),
        )


class _RejectedRouter:
    def __init__(self, validation_code: str) -> None:
        self.calls = 0
        self.diagnostic = RouterFailureDiagnostic(
            router_validation_code=validation_code,
            repair_used=True,
            repair_exhausted=True,
            physical_attempts=2,
        )

    async def route(self, command, *, recent_context, now, deadline_at):
        del command, recent_context, now, deadline_at
        self.calls += 1
        raise RetrievalRouterRepairExhaustedError(self.diagnostic)


class _Canonical:
    async def plan_and_execute(self, command, *, now, deadline_at):
        tracker = restore_call_tracker_snapshot(
            command.call_tracker,
            deadline_at=deadline_at,
        )
        tracker.record_logical_call(LlmNode.CANONICAL_PLANNER, now=now)
        tracker.record_physical_attempt(LlmNode.CANONICAL_PLANNER, now=now)
        return CanonicalPlanningResult(
            request_id=command.resolved.request_id,
            plan=None,
            execution=None,
            metrics=CanonicalPlanningMetrics(
                first_pass_valid=True,
                repair_used=False,
                short_circuited=True,
                short_circuit_reason="no_fixture_evidence",
                planner_logical_calls=1,
                planner_physical_attempts=1,
                executable_step_count=0,
                limit_clamped_step_count=0,
                result_record_count=0,
                provider="fixture",
                model="fixture-canonical",
            ),
            call_tracker=tracker.snapshot(),
        )


class _Graph:
    async def plan_and_execute(self, command, *, now, deadline_at):
        tracker = restore_call_tracker_snapshot(
            command.call_tracker,
            deadline_at=deadline_at,
        )
        tracker.record_logical_call(LlmNode.GRAPH_PLANNER, now=now)
        tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=now)
        return GraphPlanningResult(
            request_id=command.resolved.request_id,
            plan=None,
            execution=None,
            metrics=GraphPlanningMetrics(
                first_pass_valid=True,
                repair_used=False,
                short_circuited=True,
                short_circuit_reason="no_fixture_evidence",
                planner_logical_calls=1,
                planner_physical_attempts=1,
                executable_step_count=0,
                limit_clamped_step_count=0,
                hop_clamped_step_count=0,
                result_count=0,
                provider="fixture",
                model="fixture-graph",
            ),
            call_tracker=tracker.snapshot(),
        )


class _Both:
    async def coordinate(self, command, *, now, deadline_at):
        tracker = restore_call_tracker_snapshot(
            command.call_tracker,
            deadline_at=deadline_at,
        )
        for node in (LlmNode.CANONICAL_PLANNER, LlmNode.GRAPH_PLANNER):
            tracker.record_logical_call(node, now=now)
            tracker.record_physical_attempt(node, now=now)
        selection = select_workflow_recipe(command.intent)
        return BothRetrievalResult(
            request_id=command.resolved.request_id,
            selection=selection,
            workflow=None,
            dependency=None,
            canonical=None,
            graph=None,
            references=(),
            metrics=WorkflowCoordinatorMetrics(
                requested_recipe=selection.requested,
                selected_recipe=selection.selected,
                router_hint_accepted=selection.hint_accepted,
                planners_parallel=True,
                planner_axes_called=(WorkflowAxis.CANONICAL, WorkflowAxis.GRAPH),
                dependency_reference=None,
                downstream_short_circuited=False,
                downstream_short_circuit_reason=None,
                input_candidate_count=0,
                joined_reference_count=0,
                dropped_unmatched_count=0,
                deduplicated_count=0,
                output_reference_count=0,
            ),
            call_tracker=tracker.snapshot(),
        )


class _Generator:
    def __init__(self, *, failure: CharacterResponseGeneratorError | None = None) -> None:
        self.failure = failure
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return CharacterResponseGeneratorResult(
            text=f"{request.evidence.route.value}에서 만든 안전한 답변",
            provider="fixture",
            model="fixture-model",
        )


class _UnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.commits = 0
        self.rollbacks = 0

    def checkpoint(self) -> None:
        self.session.commit()
        self.commits += 1

    def rollback(self) -> None:
        self.session.rollback()
        self.rollbacks += 1


class _MemoryProducer:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.sources: list[SuccessfulChatMemorySource] = []

    def propose_after_commit(self, source: SuccessfulChatMemorySource) -> None:
        self.sources.append(source)
        if self.failure is not None:
            raise self.failure


def _request(session: Session, route: RetrievalRoute):
    user_message = session.scalar(
        select(models.MessageMessage).where(models.MessageMessage.role == "user")
    )
    assert user_message is not None
    suffix = route.value.lower()
    return GenerationLifecycleService(
        SqlAlchemyResponseLifecycleRepository(session)
    ).accept(
        CreateResponseRequest(
            request_id=f"request-{suffix}",
            thread_id="p-thread",
            user_message_id=user_message.id,
            response_slot_id=f"slot-{suffix}",
            request_scope_hash=build_request_scope_hash(
                owner_id="p-owner",
                world_id="p-world",
                thread_id="p-thread",
                user_message_id=user_message.id,
                requester_world_character_id="p-requester",
                responding_world_character_id="p-responding",
            ),
            idempotency_key=f"idempotency-{suffix}",
            generation_id=f"generation-{suffix}",
            attempt_number=1,
            selected_model="fixture-model",
            deadline_at=datetime.now(UTC) + timedelta(minutes=2),
        )
    )


def _workflow(
    session: Session,
    route: RetrievalRoute,
    generator: _Generator,
    *,
    memory_producer=None,
    router=None,
):
    lifecycle = GenerationLifecycleService(SqlAlchemyResponseLifecycleRepository(session))
    return ResponseGenerationWorkflowService(
        lifecycle=lifecycle,
        router=router or _Router(route),
        canonical=_Canonical(),
        graph=_Graph(),
        both=_Both(),
        evidence=EvidenceBundleAssembler(),
        character_response=CharacterResponseGenerationService(generator),
        unit_of_work=_UnitOfWork(session),
        memory_producer=memory_producer,
    )


def _command(record) -> ResponseWorkflowCommand:
    return ResponseWorkflowCommand(
        request=record,
        preflight=RetrievalPreflightCommand(
            request_id=record.request_id,
            owner_id="p-owner",
            world_id="p-world",
            thread_id="p-thread",
            requester_world_character_id="p-requester",
            responding_world_character_id="p-responding",
            user_message="오늘은 어땠어?",
        ),
        profile=CharacterResponseProfile(
            name="응답 앵무",
            handle="responder",
            one_liner="fixture",
            personality="calm",
            speech_style="friendly",
            worldview="fixture",
            topic_preferences="chat",
            safety_rules="safe",
        ),
        router_context=(),
        response_context=(),
        character_labels={},
    )


@pytest.mark.parametrize(
    ("route", "expected_calls"),
    [
        (RetrievalRoute.CURRENT_CONTEXT, 2),
        (RetrievalRoute.CANONICAL, 3),
        (RetrievalRoute.GRAPH, 3),
        (RetrievalRoute.BOTH, 4),
        (RetrievalRoute.CLARIFICATION, 2),
    ],
)
def test_all_routes_emit_only_crg_deltas_and_commit_once(
    response_session: Session,
    route: RetrievalRoute,
    expected_calls: int,
) -> None:
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator()
    memory_producer = _MemoryProducer()
    workflow = _workflow(
        response_session,
        route,
        generator,
        memory_producer=memory_producer,
    )

    events = asyncio.run(_collect(workflow.run(_command(record))))

    assert [event.event_type for event in events] == [
        GenerationEventType.ACCEPTED,
        GenerationEventType.DELTA,
        GenerationEventType.COMPLETED,
    ]
    assert events[0].payload == {}
    assert events[1].payload == {"text": f"{route.value}에서 만든 안전한 답변"}
    assert events[2].payload == {}
    assert len(generator.requests) == 1
    committed = SqlAlchemyResponseLifecycleRepository(response_session).get_request(
        record.request_id
    )
    assert committed.state is ResponseRequestState.COMMITTED
    assert committed.call_tracker["logical_total"] == expected_calls
    assert committed.call_tracker["logical_counts"]["character_response_generator"] == 1
    assert committed.response_metadata["evidence_bundle_version"] == EVIDENCE_BUNDLE_VERSION
    assert len(committed.response_metadata["evidence_hash"]) == 64
    assert committed.response_metadata["evidence_capability"] == "none"
    assert response_session.scalar(
        select(func.count(models.MessageMessage.id)).where(
            models.MessageMessage.thread_id == "p-thread",
            models.MessageMessage.role == "assistant",
        )
    ) == 1
    assert len(memory_producer.sources) == 1
    assert memory_producer.sources[0].assistant_message_id == (
        committed.committed_assistant_message_id
    )
    assert memory_producer.sources[0].subject_world_character_id == "p-responding"

    replay_events = asyncio.run(_collect(workflow.run(_command(committed))))
    assert [event.event_type for event in replay_events] == [
        GenerationEventType.COMPLETED
    ]
    assert len(generator.requests) == 1
    assert len(memory_producer.sources) == 1


def test_failure_is_durable_retryable_and_partial_assistant_is_not_committed(
    response_session: Session,
) -> None:
    route = RetrievalRoute.CURRENT_CONTEXT
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator(
        failure=CharacterResponseGeneratorError(
            "provider_timeout",
            retryable=True,
            provider_diagnostic={
                "node": "character_response_generator",
                "provider": "google",
                "model": "gemini-2.5-flash-lite",
                "failure_class": "timeout",
                "provider_status": "DEADLINE_EXCEEDED",
                "provider_code": 504,
                "provider_error_hint": "provider_timeout",
                "retryable": True,
            },
        )
    )
    memory_producer = _MemoryProducer()
    workflow = _workflow(
        response_session,
        route,
        generator,
        memory_producer=memory_producer,
    )

    events = asyncio.run(_collect(workflow.run(_command(record))))

    assert [event.event_type for event in events] == [
        GenerationEventType.ACCEPTED,
        GenerationEventType.FAILED,
    ]
    assert events[-1].payload == {
        "failure_class": "provider_timeout",
        "retryable": True,
    }
    failed = SqlAlchemyResponseLifecycleRepository(response_session).get_request(
        record.request_id
    )
    assert failed.state is ResponseRequestState.FAILED
    assert failed.retryable is True
    assert failed.node_state["failure_class"] == "provider_timeout"
    assert failed.node_state["provider_diagnostic"] == {
        "node": "character_response_generator",
        "provider": "google",
        "model": "gemini-2.5-flash-lite",
        "failure_class": "provider_timeout",
        "provider_status": "DEADLINE_EXCEEDED",
        "provider_code": 504,
        "provider_error_hint": "provider_timeout",
        "retryable": True,
    }
    assert failed.call_tracker["logical_counts"]["character_response_generator"] == 1
    assert failed.call_tracker["physical_counts"]["character_response_generator"] == 1
    assert response_session.scalar(
        select(func.count(models.MessageMessage.id)).where(
            models.MessageMessage.thread_id == "p-thread",
            models.MessageMessage.role == "assistant",
        )
    ) == 0
    assert memory_producer.sources == []

    replay = asyncio.run(_collect(workflow.run(_command(failed))))
    assert replay[-1].payload == {
        "failure_class": "provider_timeout",
        "retryable": True,
    }
    assert len(generator.requests) == 1


def test_router_repair_exhaustion_is_safe_durable_and_explicitly_retryable(
    response_session: Session,
) -> None:
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    rejected_router = _RejectedRouter("current_context_not_minimal")
    generator = _Generator()
    workflow = _workflow(
        response_session,
        RetrievalRoute.CURRENT_CONTEXT,
        generator,
        router=rejected_router,
    )

    events = asyncio.run(_collect(workflow.run(_command(record))))

    assert [event.event_type for event in events] == [
        GenerationEventType.ACCEPTED,
        GenerationEventType.FAILED,
    ]
    assert events[-1].payload == {
        "failure_class": "router_schema_rejected",
        "retryable": True,
    }
    assert rejected_router.calls == 1
    assert generator.requests == []
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    failed = repository.get_request(record.request_id)
    assert failed.retryable is True
    assert failed.route is None
    assert failed.node_state == {
        "failure_class": "router_schema_rejected",
        "router_diagnostic": {
            "version": "router-diagnostic.v1",
            "node": "retrieval_router",
            "router_validation_code": "current_context_not_minimal",
            "repair_used": True,
            "repair_exhausted": True,
            "physical_attempts": 2,
        },
    }
    serialized = str(failed.node_state)
    for forbidden in (
        "오늘은 어땠어?",
        "prompt",
        "raw_output",
        "api_key",
        "credential",
        "provider_body",
    ):
        assert forbidden not in serialized
    assert response_session.scalar(
        select(func.count(models.MessageMessage.id)).where(
            models.MessageMessage.thread_id == "p-thread",
            models.MessageMessage.role == "assistant",
        )
    ) == 0

    owner = response_session.get(models.User, "p-owner")
    assert owner is not None
    retried = retry_world_response(
        response_session,
        owner,
        "p-world",
        "p-thread",
        WorldChatRetryCreate(
            failed_request_id=failed.request_id,
            idempotency_key="router-hotfix-explicit-retry",
        ),
    )
    assert retried.user_message.id == failed.user_message_id
    assert retried.response_request.response_slot_id == failed.response_slot_id
    assert retried.response_request.request_id != failed.request_id
    assert retried.response_request.generation_id != failed.generation_id
    assert retried.response_request.attempt_number == failed.attempt_number + 1

    retried_record = repository.get_request(retried.response_request.request_id)
    successful_router = _Router(RetrievalRoute.CURRENT_CONTEXT)
    successful_generator = _Generator()
    retry_events = asyncio.run(
        _collect(
            _workflow(
                response_session,
                RetrievalRoute.CURRENT_CONTEXT,
                successful_generator,
                router=successful_router,
            ).run(_command(retried_record))
        )
    )
    assert retry_events[-1].event_type is GenerationEventType.COMPLETED
    assert successful_router.calls == 1
    assert len(successful_generator.requests) == 1
    assert response_session.scalar(
        select(func.count(models.MessageMessage.id)).where(
            models.MessageMessage.thread_id == "p-thread",
            models.MessageMessage.role == "user",
        )
    ) == 1
    assert response_session.scalar(
        select(func.count(models.MessageMessage.id)).where(
            models.MessageMessage.thread_id == "p-thread",
            models.MessageMessage.role == "assistant",
        )
    ) == 1
    assert repository.get_request(failed.request_id).node_state == failed.node_state


def test_router_security_rejection_stays_nonretryable(
    response_session: Session,
) -> None:
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    response_session.commit()
    events = asyncio.run(
        _collect(
            _workflow(
                response_session,
                RetrievalRoute.CURRENT_CONTEXT,
                _Generator(),
                router=_RejectedRouter("raw_query_forbidden"),
            ).run(_command(record))
        )
    )
    assert events[-1].payload == {
        "failure_class": "router_schema_rejected",
        "retryable": False,
    }
    failed = SqlAlchemyResponseLifecycleRepository(response_session).get_request(
        record.request_id
    )
    assert failed.retryable is False
    assert failed.node_state["router_diagnostic"][
        "router_validation_code"
    ] == "raw_query_forbidden"


def test_after_commit_memory_candidate_is_opt_in_idempotent_and_failure_isolated(
    response_session: Session,
) -> None:
    scope = MemoryScope(
        owner_id="p-owner",
        world_id="p-world",
        subject_world_character_id="p-responding",
    )
    repository = SqlAlchemyMemoryRepository(response_session)
    scope_service = MemoryScopeService(repository)
    initial = scope_service.get_or_create(scope)
    scope_service.update(
        scope,
        expected_version=initial.version,
        enabled=True,
        retention_days=180,
    )
    response_session.commit()

    route = RetrievalRoute.CURRENT_CONTEXT
    record = _request(response_session, route)
    response_session.commit()
    workflow = _workflow(
        response_session,
        route,
        _Generator(),
        memory_producer=SqlAlchemySuccessfulChatMemoryProducer(response_session),
    )

    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    committed = SqlAlchemyResponseLifecycleRepository(response_session).get_request(
        record.request_id
    )
    candidate = response_session.scalar(select(models.MemoryCandidate))
    assert candidate is not None
    assert candidate.source_type == "CHAT_MESSAGE"
    assert candidate.source_id == str(committed.committed_assistant_message_id)
    assert candidate.memory_kind_hint == "AUTOBIOGRAPHICAL_EVENT"

    producer = SqlAlchemySuccessfulChatMemoryProducer(response_session)
    producer.propose_after_commit(
        SuccessfulChatMemorySource(
            request_id=committed.request_id,
            owner_id="p-owner",
            world_id="p-world",
            subject_world_character_id="p-responding",
            assistant_message_id=committed.committed_assistant_message_id or 0,
        )
    )
    assert response_session.scalar(select(func.count(models.MemoryCandidate.id))) == 1

    failing = _MemoryProducer(failure=RuntimeError("fixture-memory-down"))
    second = _request(response_session, RetrievalRoute.GRAPH)
    response_session.commit()
    second_events = asyncio.run(
        _collect(
            _workflow(
                response_session,
                RetrievalRoute.GRAPH,
                _Generator(),
                memory_producer=failing,
            ).run(_command(second))
        )
    )
    assert second_events[-1].event_type is GenerationEventType.COMPLETED
    assert SqlAlchemyResponseLifecycleRepository(response_session).get_request(
        second.request_id
    ).state is ResponseRequestState.COMMITTED
    assert len(failing.sources) == 1
    assert response_session.scalar(select(func.count(models.MemoryCandidate.id))) == 1


async def _collect(iterator):
    return [event async for event in iterator]


def test_evidence_snapshot_is_deterministic_bounded_and_provider_safe() -> None:
    assembler = EvidenceBundleAssembler()
    newest = EvidenceItem(
        opaque_reference=opaque_evidence_reference("canonical", "secret-source-2"),
        kind=EvidenceKind.CANONICAL_SOURCE,
        text="검증된 최근 사건",
        occurred_at=NOW,
        axes=(RetrievalAxis.CANONICAL,),
    )
    older = EvidenceItem(
        opaque_reference=opaque_evidence_reference("canonical", "secret-source-1"),
        kind=EvidenceKind.CANONICAL_SOURCE,
        text="검증된 과거 사건",
        occurred_at=NOW - timedelta(days=1),
        axes=(RetrievalAxis.CANONICAL,),
    )
    duplicate = replace(older, opaque_reference="evidence-ffffffffffffffffffffffff")

    first = assembler._dedupe_sort_truncate((older, duplicate, newest))
    second = assembler._dedupe_sort_truncate((newest, duplicate, older))

    assert first == second
    assert [item.text for item in first] == ["검증된 최근 사건", "검증된 과거 사건"]
    bundle = assembler._bundle(
        request_id="request-evidence",
        request_scope_hash="a" * 64,
        route=RetrievalRoute.CANONICAL,
        outcome=RetrievalOutcome.MEMORY_USED,
        candidates=(older, duplicate, newest),
    )
    payload = bundle.provider_payload()
    assert bundle.evidence_capability is EvidenceCapability.AVAILABLE
    assert bundle == assembler._bundle(
        request_id="request-evidence",
        request_scope_hash="a" * 64,
        route=RetrievalRoute.CANONICAL,
        outcome=RetrievalOutcome.MEMORY_USED,
        candidates=(newest, older, duplicate),
    )
    assert "secret-source" not in str(payload)
    assert all(set(item) == {"ref", "kind", "text", "occurred_at"} for item in payload["items"])


def test_send_replay_and_retry_reuse_one_user_message_and_response_slot(
    response_session: Session,
) -> None:
    owner = response_session.get(models.User, "p-owner")
    assert owner is not None
    payload = WorldChatMessageCreate(
        content="철수랑 왜 싸웠지?",
        idempotency_key="message-idempotency-p8-l-p",
    )
    accepted = accept_world_message(
        response_session,
        owner,
        "p-world",
        "p-thread",
        payload,
    )
    replayed = accept_world_message(
        response_session,
        owner,
        "p-world",
        "p-thread",
        payload,
    )
    assert replayed.outcome == "replayed"
    assert replayed.user_message.id == accepted.user_message.id
    accepted_snapshot = response_session.get(
        models.ChatResponseRequest,
        accepted.response_request.request_id,
    )
    assert accepted_snapshot is not None
    assert accepted_snapshot.selected_model == "gemini-3.1-flash-lite"
    persisted_thread = response_session.get(models.MessageThread, "p-thread")
    assert persisted_thread is not None
    assert persisted_thread.selected_model == "gemini-3.1-flash-lite"

    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    record = repository.get_request(accepted.response_request.request_id)
    now = datetime.now(UTC)
    record = repository.acquire_lease(
        request_id=record.request_id,
        lease_token="lease-retry",
        now=now,
        lease_expires_at=now + timedelta(seconds=30),
    )
    failed = repository.mark_terminal(
        GenerationFence(
            request_id=record.request_id,
            thread_id=record.thread_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            lease_generation=record.lease_generation,
            expected_prior_state=record.state,
        ),
        target=ResponseRequestState.FAILED,
        reason=ResponseTerminalReason.PROVIDER_FAILURE,
        retryable=True,
        failure_class="provider_timeout",
        now=now,
    )
    response_session.commit()
    world_chat.update_user_settings(
        response_session,
        owner,
        MessageSettingsUpdate(default_model="gemini-2.5-flash"),
    )
    retried = retry_world_response(
        response_session,
        owner,
        "p-world",
        "p-thread",
        WorldChatRetryCreate(
            failed_request_id=failed.request_id,
            idempotency_key="retry-idempotency-p8-l-p",
        ),
    )

    assert retried.user_message.id == accepted.user_message.id
    assert retried.response_request.response_slot_id == accepted.response_request.response_slot_id
    assert retried.response_request.attempt_number == 2
    assert retried.response_request.generation_id != accepted.response_request.generation_id
    retry_snapshot = response_session.get(
        models.ChatResponseRequest,
        retried.response_request.request_id,
    )
    assert retry_snapshot is not None
    assert retry_snapshot.selected_model == "gemini-2.5-flash"
    assert response_session.scalar(
        select(func.count(models.MessageMessage.id)).where(
            models.MessageMessage.thread_id == "p-thread",
            models.MessageMessage.role == "user",
        )
    ) == 2


def test_status_read_recovers_an_expired_non_terminal_request(
    response_session: Session,
) -> None:
    owner = response_session.get(models.User, "p-owner")
    assert owner is not None
    record = _request(response_session, RetrievalRoute.CURRENT_CONTEXT)
    row = response_session.get(models.ChatResponseRequest, record.request_id)
    assert row is not None
    row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    response_session.commit()

    read = get_world_response_request(
        response_session,
        owner,
        "p-world",
        "p-thread",
        record.request_id,
    )

    assert read.state == "timed_out"
    assert read.retryable is True
    assert read.failure_class == "deadline_exceeded"
