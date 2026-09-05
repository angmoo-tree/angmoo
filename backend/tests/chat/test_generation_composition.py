"""Actual streaming admission and provider composition preserve execution order."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import func, select

from app.domains.chat import models
from app.domains.chat.contracts import GenerationEventType, ResponseRequestState
from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.runtime.chat import generation_workflows
from app.runtime.chat.message_composition import generation_service
from test_p8_l_j_response_generation_lifecycle import _command, response_session


def test_runtime_builder_keeps_provider_order_material_and_session(monkeypatch):
    db = object()
    material = object()
    config = object()
    lifecycle = object()
    labels = {"character": "Name"}
    observed = []

    def provider(name):
        def create(value):
            assert value is material
            observed.append(name)
            return SimpleNamespace(name=name)

        return create

    for symbol, name in (
        ("DirectLlmCanonicalRetrievalPlannerProvider", "canonical"),
        ("DirectLlmGraphRetrievalPlannerProvider", "graph"),
        ("DirectLlmRetrievalRouterProvider", "router"),
        ("DirectLlmCharacterResponseGenerator", "response"),
    ):
        monkeypatch.setattr(generation_workflows, symbol, provider(name))

    def graph_gateway(session, *, config, graph_provider):
        assert session is db
        assert config is runtime_config
        assert graph_provider == "ladybug"
        observed.append("graph_gateway")
        return object()

    runtime_config = config
    monkeypatch.setattr(
        generation_workflows, "SqlAlchemyRelationshipGraphReadGateway", graph_gateway
    )

    def character_labels(session, world_id):
        assert session is db
        assert world_id == "world"
        observed.append("labels")
        return labels

    def memory_producer(session):
        assert session is db
        observed.append("memory")
        return SimpleNamespace(session=session)

    def today_validator(session, current_labels):
        assert session is db
        assert current_labels is labels
        observed.append("today")
        return SimpleNamespace(session=session)

    monkeypatch.setattr(generation_workflows, "_character_labels", character_labels)
    monkeypatch.setattr(
        generation_workflows, "SqlAlchemySuccessfulChatMemoryProducer", memory_producer
    )
    monkeypatch.setattr(
        generation_workflows, "SqlAlchemyTodaySnsSnapshotValidator", today_validator
    )
    execution = generation_workflows.build(
        db,
        material,
        memory_recall_service=object(),
        runtime_settings=config,
        lifecycle=lifecycle,
        world_id="world",
    )
    assert observed == [
        "canonical",
        "graph_gateway",
        "graph",
        "labels",
        "router",
        "response",
        "memory",
        "today",
    ]
    assert execution.character_labels is labels
    assert execution.workflow._lifecycle is lifecycle
    assert execution.workflow._unit_of_work._session is db
    assert execution.workflow._memory_producer.session is db
    assert execution.workflow._today_snapshot_validator.session is db


def test_unavailable_memory_fails_durably_before_any_provider_builder(
    response_session, monkeypatch
):
    db = response_session
    repository = SqlAlchemyResponseLifecycleRepository(db)
    record = repository.create_request(_command(datetime.now(UTC)))
    db.commit()
    thread = db.get(models.MessageThread, record.thread_id)
    provider_calls = []

    def forbidden_builder(*args, **kwargs):
        provider_calls.append((args, kwargs))
        raise AssertionError("Unavailable local runtime must not construct providers")

    monkeypatch.setattr(generation_service, "_mutation_thread", lambda *args: thread)
    monkeypatch.setattr(generation_service.workflows, "build", forbidden_builder)

    async def collect():
        return [
            event
            async for event in generation_service.stream_world_response(
                db,
                SimpleNamespace(id="response-owner"),
                "response-world",
                record.thread_id,
                record.request_id,
                memory_recall_service=None,
            )
        ]

    events = asyncio.run(collect())
    stored = repository.get_request(record.request_id)
    assert [event.event_type for event in events] == [
        GenerationEventType.ACCEPTED,
        GenerationEventType.FAILED,
    ]
    assert stored.state is ResponseRequestState.FAILED
    assert stored.node_state["failure_class"] == "local_runtime_unavailable"
    assert stored.retryable is True
    assert stored.committed_assistant_message_id is None
    assert db.scalar(select(func.count(models.MessageMessage.id))) == 1
    assert provider_calls == []
