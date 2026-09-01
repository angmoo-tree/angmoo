from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.chat.application import BoundedFakeAnswerRequestExecutor
from app.domains.chat.domain import (
    CreateResponseRequest,
    GenerationContractError,
    GenerationEvent,
    GenerationEventType,
    GenerationFence,
    LlmNode,
    RESOLVED_RETRIEVAL_VERSION,
    ResolvedEntityBinding,
    ResolvedRetrievalEnvelope,
    ResponseCommitPayload,
    ResponseMetadata,
    ResponseRequestState,
    RetrievalContractError,
    RetrievalDecision,
    RetrievalEntityMention,
    RetrievalHardCaps,
    RetrievalIntentEnvelope,
    RetrievalOutcome,
    RetrievalRoute,
    RetrievalWorkflow,
    RouteAwareCallTracker,
    WorkflowRecipe,
    build_request_scope_hash,
)
from app.domains.chat.infrastructure import SqlAlchemyResponseLifecycleRepository
from app.domains.memory.public import (
    CANONICAL_PRIMITIVE_REGISTRY,
    CanonicalPlanStep,
    CanonicalRetrievalPlan,
)
from app.domains.relationships.public import (
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    GraphPlanStep,
    GraphRetrievalPlan,
)


def _intent(route: RetrievalRoute) -> RetrievalIntentEnvelope:
    decision = (
        RetrievalDecision.CURRENT_CONTEXT
        if route is RetrievalRoute.CURRENT_CONTEXT
        else RetrievalDecision.CLARIFICATION
        if route is RetrievalRoute.CLARIFICATION
        else RetrievalDecision.RETRIEVAL
    )
    return RetrievalIntentEnvelope(
        decision=decision,
        route=route,
        intent="relationship_cause" if route is not RetrievalRoute.CURRENT_CONTEXT else "smalltalk",
        entities=(RetrievalEntityMention("entity-1", "철수", "counterpart"),),
        clarification_slot="counterpart" if route is RetrievalRoute.CLARIFICATION else None,
    )


def _resolved(intent: RetrievalIntentEnvelope, request_id: str = "request-1") -> ResolvedRetrievalEnvelope:
    return ResolvedRetrievalEnvelope.bind_intent(
        intent,
        request_id=request_id,
        owner_id="owner",
        world_id="world",
        requester_world_character_id="requester",
        responding_world_character_id="responding",
        entity_bindings=(ResolvedEntityBinding("entity-1", "counterpart"),),
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


def _workflow(
    intent: RetrievalIntentEnvelope,
    resolved: ResolvedRetrievalEnvelope,
) -> RetrievalWorkflow:
    canonical = None
    graph = None
    recipe = None
    if intent.route in {RetrievalRoute.CANONICAL, RetrievalRoute.BOTH}:
        canonical = CanonicalRetrievalPlan(
            request_id=resolved.request_id,
            envelope_version=resolved.version,
            envelope_hash=resolved.envelope_hash,
            steps=(
                CanonicalPlanStep(
                    id="memory",
                    operation=next(iter(CANONICAL_PRIMITIVE_REGISTRY)).value,
                ),
            ),
        )
    if intent.route in {RetrievalRoute.GRAPH, RetrievalRoute.BOTH}:
        graph = GraphRetrievalPlan(
            request_id=resolved.request_id,
            envelope_version=resolved.version,
            envelope_hash=resolved.envelope_hash,
            steps=(
                GraphPlanStep(
                    id="relationship",
                    operation=next(iter(GRAPH_RECALL_PRIMITIVE_REGISTRY)).value,
                ),
            ),
        )
    if intent.route is RetrievalRoute.BOTH:
        recipe = WorkflowRecipe.INDEPENDENT_PARALLEL
    return RetrievalWorkflow(
        request_id=resolved.request_id,
        route=intent.route,
        envelope_version=RESOLVED_RETRIEVAL_VERSION,
        envelope_hash=resolved.envelope_hash,
        canonical_plan=canonical,
        graph_plan=graph,
        recipe=recipe,
    )


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (RetrievalRoute.CURRENT_CONTEXT, 2),
        (RetrievalRoute.CANONICAL, 3),
        (RetrievalRoute.GRAPH, 3),
        (RetrievalRoute.BOTH, 4),
        (RetrievalRoute.CLARIFICATION, 2),
    ],
)
def test_fake_nodes_enforce_route_budget_without_live_provider(
    route: RetrievalRoute,
    expected: int,
) -> None:
    now = datetime.now(UTC)
    intent = _intent(route)
    resolved = _resolved(intent)
    result = BoundedFakeAnswerRequestExecutor().execute(
        intent=intent,
        resolved=resolved,
        workflow=_workflow(intent, resolved),
        deadline_at=now + timedelta(seconds=30),
        now=now,
    )

    assert result.tracker["logical_total"] == expected
    assert result.tracker["physical_total"] == expected
    assert result.tracker["normal_full_path_cap"] == expected
    assert result.provider_calls == 0
    assert result.executed_nodes[-1] == "character_response_generator"


def test_request_wide_repair_and_duplicate_crg_are_fail_closed() -> None:
    now = datetime.now(UTC)
    tracker = RouteAwareCallTracker(
        route=RetrievalRoute.BOTH,
        deadline_at=now + timedelta(seconds=30),
    )
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=now)
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=now, repair=True)
    tracker.record_logical_call(LlmNode.CHARACTER_RESPONSE_GENERATOR, now=now)
    with pytest.raises(RetrievalContractError, match="repair_exceeded"):
        tracker.record_logical_call(LlmNode.GRAPH_PLANNER, now=now, repair=True)
    with pytest.raises(RetrievalContractError, match="duplicate_crg"):
        tracker.record_logical_call(LlmNode.CHARACTER_RESPONSE_GENERATOR, now=now)


def test_envelope_hash_cross_catalog_and_raw_query_are_rejected() -> None:
    intent = _intent(RetrievalRoute.CANONICAL)
    resolved = _resolved(intent)
    graph_operation = next(iter(GRAPH_RECALL_PRIMITIVE_REGISTRY)).value
    wrong_plan = CanonicalRetrievalPlan(
        request_id=resolved.request_id,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        steps=(CanonicalPlanStep(id="wrong", operation=graph_operation),),
    )
    workflow = RetrievalWorkflow(
        request_id=resolved.request_id,
        route=RetrievalRoute.CANONICAL,
        envelope_version=resolved.version,
        envelope_hash=resolved.envelope_hash,
        canonical_plan=wrong_plan,
    )
    now = datetime.now(UTC)
    with pytest.raises(RetrievalContractError, match="canonical_plan_operation_forbidden"):
        BoundedFakeAnswerRequestExecutor().execute(
            intent=intent,
            resolved=resolved,
            workflow=workflow,
            deadline_at=now + timedelta(seconds=30),
            now=now,
        )
    with pytest.raises(ValueError, match="raw_sql_forbidden"):
        CanonicalPlanStep(id="raw", operation="SELECT * FROM memory_items;")
    with pytest.raises(ValueError, match="raw_cypher_forbidden"):
        GraphPlanStep(id="raw", operation="MATCH (n) RETURN n")
    with pytest.raises(ValueError, match="parameter_value_invalid"):
        CanonicalPlanStep(
            id="raw_parameter",
            operation=next(iter(CANONICAL_PRIMITIVE_REGISTRY)).value,
            parameters=(("query", "SELECT * FROM memory_items;"),),
        )


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
        one_liner="",
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
    now = datetime.now(UTC)
    owner = _user("response-owner")
    responder_owner = _user("response-responder-owner")
    requester_character = _character("response-requester-character", owner.id)
    responding_character = _character(
        "response-responding-character",
        responder_owner.id,
    )
    world = models.World(
        id="response-world",
        slug="response-world",
        owner_user_id=owner.id,
        name="Response World",
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
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="response-world",
    )
    owner_membership = models.WorldMembership(
        id="response-owner-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=now,
    )
    responder_membership = models.WorldMembership(
        id="response-responder-membership",
        world_id=world.id,
        user_id=responder_owner.id,
        role="member",
        status="active",
        joined_at=now,
    )
    requester = models.WorldCharacter(
        id="response-requester",
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
        id="response-responding",
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
    session.add_all([requester_character, responding_character, world])
    session.flush()
    session.add_all([owner_membership, responder_membership])
    session.flush()
    session.add_all([requester, responding])
    session.flush()
    thread = models.MessageThread(
        id="response-thread",
        requester_id=owner.id,
        character_id=responding_character.id,
        world_id=world.id,
        requester_world_character_id=requester.id,
        responding_world_character_id=responding.id,
        world_scope_status="resolved",
        selected_model="fixture-model",
    )
    session.add(thread)
    session.flush()
    user_message = models.MessageMessage(
        thread_id=thread.id,
        role="user",
        content="철수랑 왜 싸웠지?",
        status="ok",
    )
    session.add(user_message)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _command(now: datetime, suffix: str = "1") -> CreateResponseRequest:
    return CreateResponseRequest(
        request_id=f"request-{suffix}",
        thread_id="response-thread",
        user_message_id=1,
        response_slot_id=f"slot-{suffix}",
        request_scope_hash=build_request_scope_hash(
            owner_id="response-owner",
            world_id="response-world",
            thread_id="response-thread",
            user_message_id=1,
            requester_world_character_id="response-requester",
            responding_world_character_id="response-responding",
        ),
        idempotency_key=f"request-idempotency-{suffix}",
        generation_id=f"generation-{suffix}",
        attempt_number=1,
        selected_model="fixture-model",
        deadline_at=now + timedelta(minutes=2),
    )


def _fence(record) -> GenerationFence:
    return GenerationFence(
        request_id=record.request_id,
        thread_id=record.thread_id,
        request_scope_hash=record.request_scope_hash,
        generation_id=record.generation_id,
        attempt_number=record.attempt_number,
        lease_generation=record.lease_generation,
        expected_prior_state=record.state,
    )


def _transition(repository, record, target, now, **values):
    return repository.transition(
        _fence(record),
        target=target,
        now=now,
        **values,
    )


def _ready_to_commit(repository, now, suffix="1"):
    record = repository.create_request(_command(now, suffix))
    record = repository.acquire_lease(
        request_id=record.request_id,
        lease_token=f"lease-{suffix}",
        now=now,
        lease_expires_at=now + timedelta(minutes=1),
    )
    record = _transition(repository, record, ResponseRequestState.PREFLIGHTED, now)
    record = _transition(repository, record, ResponseRequestState.ROUTING, now)
    record = _transition(repository, record, ResponseRequestState.RESOLVING, now)
    record = _transition(
        repository,
        record,
        ResponseRequestState.CURRENT_CONTEXT_READY,
        now,
        route=RetrievalRoute.CURRENT_CONTEXT,
    )
    record = _transition(repository, record, ResponseRequestState.EVIDENCE_FROZEN, now)
    record = _transition(
        repository,
        record,
        ResponseRequestState.RESPONSE_GENERATING,
        now,
        call_tracker={
            "logical_counts": {"character_response_generator": 1},
            "physical_counts": {"character_response_generator": 1},
        },
    )
    record = _transition(repository, record, ResponseRequestState.COMMITTING, now)
    return record


def _commit_payload(record) -> ResponseCommitPayload:
    return ResponseCommitPayload(
        content="검증된 근거를 바탕으로 만든 완전한 답변",
        model="fixture-model",
        metadata=ResponseMetadata(
            request_id=record.request_id,
            request_scope_hash=record.request_scope_hash,
            generation_id=record.generation_id,
            attempt_number=record.attempt_number,
            route=RetrievalRoute.CURRENT_CONTEXT,
            retrieval_outcome=RetrievalOutcome.CURRENT_CONTEXT,
            last_accepted_sequence=record.last_emitted_sequence,
        ),
    )


def test_renewed_lease_rejects_old_fence_and_sequence_gap(response_session: Session) -> None:
    now = datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    record = repository.create_request(_command(now))
    replay = repository.create_request(_command(now))
    assert replay.request_id == record.request_id
    record = repository.acquire_lease(
        request_id=record.request_id,
        lease_token="lease-1",
        now=now,
        lease_expires_at=now + timedelta(seconds=30),
    )
    stale = _fence(record)
    renewed = repository.renew_lease(
        stale,
        lease_token="lease-1",
        now=now + timedelta(seconds=1),
        lease_expires_at=now + timedelta(seconds=60),
    )
    with pytest.raises(GenerationContractError, match="fence_conflict"):
        repository.transition(
            stale,
            target=ResponseRequestState.PREFLIGHTED,
            now=now + timedelta(seconds=2),
        )
    renewed = _transition(
        repository,
        renewed,
        ResponseRequestState.PREFLIGHTED,
        now + timedelta(seconds=2),
    )
    event = GenerationEvent(
        request_id=renewed.request_id,
        request_scope_hash=renewed.request_scope_hash,
        generation_id=renewed.generation_id,
        attempt_number=renewed.attempt_number,
        sequence=0,
        event_type=GenerationEventType.ACCEPTED,
    )
    assert repository.accept_event(_fence(renewed), event, now=now + timedelta(seconds=3)).value == "accepted"
    assert repository.accept_event(_fence(renewed), event, now=now + timedelta(seconds=3)).value == "duplicate"
    gap = GenerationEvent(
        request_id=renewed.request_id,
        request_scope_hash=renewed.request_scope_hash,
        generation_id=renewed.generation_id,
        attempt_number=renewed.attempt_number,
        sequence=2,
        event_type=GenerationEventType.DELTA,
        payload={"text": "raw partial must stay transient"},
    )
    with pytest.raises(GenerationContractError, match="gap_or_reversal"):
        repository.accept_event(_fence(renewed), gap, now=now + timedelta(seconds=4))
    assert repository.get_request(renewed.request_id).last_emitted_sequence == 0


def test_fenced_finalize_is_atomic_idempotent_and_stores_no_partial_delta(
    response_session: Session,
) -> None:
    now = datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    record = _ready_to_commit(repository, now)
    bad_fence = GenerationFence(
        request_id=record.request_id,
        thread_id=record.thread_id,
        request_scope_hash=record.request_scope_hash,
        generation_id=record.generation_id,
        attempt_number=record.attempt_number,
        lease_generation=record.lease_generation + 1,
        expected_prior_state=ResponseRequestState.COMMITTING,
    )
    payload = _commit_payload(record)
    before = response_session.scalar(select(func.count(models.MessageMessage.id)))
    with pytest.raises(GenerationContractError, match="finalize_fence_conflict"):
        repository.finalize_response(bad_fence, payload, now=now + timedelta(seconds=1))
    assert response_session.scalar(select(func.count(models.MessageMessage.id))) == before

    committed = repository.finalize_response(
        _fence(record),
        payload,
        now=now + timedelta(seconds=2),
    )
    response_session.commit()
    assert committed.state is ResponseRequestState.COMMITTED
    assert committed.committed_assistant_message_id is not None
    assert committed.response_metadata["route"] == "current_context"
    assert response_session.scalar(select(func.count(models.MessageMessage.id))) == before + 1

    replay = repository.finalize_response(
        _fence(record),
        payload,
        now=now + timedelta(seconds=3),
    )
    assert replay.committed_assistant_message_id == committed.committed_assistant_message_id
    assert response_session.scalar(select(func.count(models.MessageMessage.id))) == before + 1
    columns = set(models.ChatResponseRequest.__table__.columns.keys())
    assert not {"delta", "partial_text", "typing", "socket", "transport_session"} & columns
    assert response_session.scalar(select(func.count(models.MemoryCandidate.id))) == 0


def test_cancel_orphan_recovery_and_retry_lineage_are_fail_closed(
    response_session: Session,
) -> None:
    now = datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(response_session)

    cancelled = repository.create_request(_command(now, "cancel"))
    cancelled = repository.acquire_lease(
        request_id=cancelled.request_id,
        lease_token="lease-cancel",
        now=now,
        lease_expires_at=now + timedelta(seconds=30),
    )
    cancel_fence = _fence(cancelled)
    cancelled = repository.request_cancel(
        request_id=cancelled.request_id,
        request_scope_hash=cancelled.request_scope_hash,
        now=now + timedelta(seconds=1),
    )
    assert cancelled.cancel_requested_at is not None
    assert cancelled.state is ResponseRequestState.CANCELLED
    with pytest.raises(GenerationContractError, match="transition_fence_conflict"):
        repository.transition(
            cancel_fence,
            target=ResponseRequestState.PREFLIGHTED,
            now=now + timedelta(seconds=2),
        )

    orphan = repository.create_request(_command(now, "orphan"))
    orphan = repository.acquire_lease(
        request_id=orphan.request_id,
        lease_token="lease-orphan",
        now=now,
        lease_expires_at=now + timedelta(seconds=1),
    )
    recovered = repository.recover_expired_requests(
        now=now + timedelta(seconds=2)
    )
    recovered_by_id = {record.request_id: record for record in recovered}
    assert recovered_by_id[orphan.request_id].state is ResponseRequestState.ORPHANED
    assert recovered_by_id[orphan.request_id].retryable is True

    retry = replace(
        _command(now, "orphan"),
        request_id="request-orphan-retry",
        idempotency_key="request-idempotency-orphan-retry",
        generation_id="generation-orphan-retry",
        attempt_number=2,
        retry_of_request_id=orphan.request_id,
    )
    retry_record = repository.create_request(retry)
    assert retry_record.attempt_number == 2
    assert retry_record.retry_of_request_id == orphan.request_id
    with pytest.raises(GenerationContractError, match="retry_lineage_mismatch"):
        repository.create_request(
            replace(
                retry,
                request_id="request-bad-retry",
                idempotency_key="request-idempotency-bad-retry",
                generation_id="generation-bad-retry",
                response_slot_id="different-slot",
            )
        )


def test_stream_payload_and_typed_commit_metadata_reject_internal_drift(
    response_session: Session,
) -> None:
    now = datetime.now(UTC)
    with pytest.raises(GenerationContractError, match="delta_payload_invalid"):
        GenerationEvent(
            request_id="request",
            request_scope_hash="a" * 64,
            generation_id="generation",
            attempt_number=1,
            sequence=0,
            event_type=GenerationEventType.DELTA,
            payload={"text": "visible", "router_output": "forbidden"},
        )

    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    record = _ready_to_commit(repository, now, "metadata")
    bad_payload = replace(
        _commit_payload(record),
        metadata=replace(
            _commit_payload(record).metadata,
            generation_id="stale-generation",
        ),
    )
    before = response_session.scalar(select(func.count(models.MessageMessage.id)))
    with pytest.raises(GenerationContractError, match="metadata_mismatch"):
        repository.finalize_response(
            _fence(record),
            bad_payload,
            now=now + timedelta(seconds=1),
        )
    assert response_session.scalar(select(func.count(models.MessageMessage.id))) == before


def test_deadline_prevents_late_transition_and_physical_retry_is_visible(
    response_session: Session,
) -> None:
    now = datetime.now(UTC)
    tracker = RouteAwareCallTracker(
        route=RetrievalRoute.CURRENT_CONTEXT,
        deadline_at=now + timedelta(seconds=1),
    )
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=now)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=now)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=now)
    assert tracker.logical_total == 1
    assert tracker.physical_total == 2
    with pytest.raises(RetrievalContractError, match="physical_attempt_budget"):
        tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=now)
    with pytest.raises(RetrievalContractError, match="deadline_exceeded"):
        tracker.record_logical_call(
            LlmNode.CHARACTER_RESPONSE_GENERATOR,
            now=now + timedelta(seconds=1),
        )

    repository = SqlAlchemyResponseLifecycleRepository(response_session)
    command = _command(now, "deadline")
    command = replace(command, deadline_at=now + timedelta(seconds=1))
    record = repository.create_request(command)
    record = repository.acquire_lease(
        request_id=record.request_id,
        lease_token="lease-deadline",
        now=now,
        lease_expires_at=now + timedelta(seconds=30),
    )
    with pytest.raises(GenerationContractError, match="transition_fence_conflict"):
        repository.transition(
            _fence(record),
            target=ResponseRequestState.PREFLIGHTED,
            now=now + timedelta(seconds=2),
        )
