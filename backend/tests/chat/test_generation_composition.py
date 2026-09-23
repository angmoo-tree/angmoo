"""Actual streaming admission and provider composition preserve execution order."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import func, select

from app.domains.chat import models
from app.domains.chat.contracts import GenerationEventType, ResponseRequestState
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
from app.domains.chat.repository.response_lifecycle import (
    SqlAlchemyResponseLifecycleRepository,
)
from app.providers.contracts import ProviderToolCall
from app.runtime.chat import generation_workflows
from app.runtime.chat.message_composition import generation_service
from chat.test_p8_l_j_response_generation_lifecycle import _command, response_session
from chat.test_supervisor_argument_patches import material as selection_material
from chat.test_supervisor_control_tools import native


def test_runtime_builder_keeps_provider_order_material_and_session(monkeypatch):
    monkeypatch.setattr("app.domains.relationships.service.personalized_metrics.interpreted_policy", lambda db, world: None)
    db = object()
    material = selection_material()
    # This ordering contract specifically exercises the retained legacy planners.
    config = SimpleNamespace(CHAT_RECALL_MODE="legacy_checkpoint")
    lifecycle = object()
    labels = {"character": "Name"}
    observed = []
    selector_class = generation_workflows.DirectLlmSupervisorSelectionProvider

    def provider(name):
        def create(value, **options):
            assert value is material
            observed.append(name)
            if name == "router":
                return selector_class(value, **options)
            assert not options
            return SimpleNamespace(name=name)

        return create

    for symbol, name in (
        ("DirectLlmCanonicalRetrievalPlannerProvider", "canonical"),
        ("DirectLlmGraphRetrievalPlannerProvider", "graph"),
        # Preserve the historical selection-role trace label and order contract;
        # the factory is now Supervisor's native selector, not a Router node.
        ("DirectLlmSupervisorSelectionProvider", "router"),
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

    # Exercise the selector produced by the real builder at its LLM boundary.
    # Missing activation or a stale model-owned coordination field must fail here.
    captured = []
    control = native(RetrievalRoute.CURRENT_CONTEXT)
    arguments = control.arguments()
    arguments.pop("coordination_hint")

    async def generate_text(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            text="",
            finish_reason="STOP",
            tool_calls=(ProviderToolCall(control.name, arguments, control.call_id),),
        )

    monkeypatch.setattr("app.integrations.direct_llm.generate_text", generate_text)
    selection = asyncio.run(
        execution.workflow._router._router.route(RetrievalRouterRequest(user_message="hello"))
    )
    assert selection.intent.route is RetrievalRoute.CURRENT_CONTEXT
    assert selection.intent.coordination_source == "code"
    assert selection.selection_mode == "native_control"
    assert selection.argument_protocol == "selection-args.v1.a1b0"
    assert len(captured) == 1
    assert captured[0]["require_tool_call"] is True
    assert [tool.name for tool in captured[0]["tools"]] == [
        "CANONICAL", "GRAPH", "USE_CONTEXT", "REQUEST_CLARIFICATION"
    ]
    for tool in captured[0]["tools"]:
        assert "coordination_hint" not in tool.parameters["properties"]
        assert "ref" in tool.parameters["properties"]["entities"]["items"]["required"]


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
