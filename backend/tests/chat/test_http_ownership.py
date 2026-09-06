"""Actual Chat HTTP uses the configured services and preserves response transport."""

import importlib
import json
from types import SimpleNamespace

import pytest
from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
from fastapi import FastAPI, Request
from fastapi.routing import _iter_routes_with_context
from fastapi.testclient import TestClient

from app.api.identity_dependencies import get_current_user
from app.core.db import get_db
from app.domains.chat import dependencies
from app.domains.chat.router import messages, world_chat, world_chat_response
from app.runtime.chat import message_composition


@pytest.mark.parametrize("module_name", ["app.main", "app.public_main"])
def test_both_factories_register_the_same_actual_chat_services(module_name):
    factory = importlib.import_module(module_name).create_app
    options = (
        {"prepare_media_directories": False}
        if module_name.endswith("public_main")
        else {}
    )
    app = factory(**options)
    request = Request({"type": "http", "app": app})
    for name in (
        "thread_service",
        "settings_service",
        "message_service",
        "generation_service",
        "evidence_service",
    ):
        getter = getattr(dependencies, "get_" + name)
        assert getter(request) is getattr(message_composition, name)
    assert dependencies.get_current_user is get_current_user
    assert dependencies.get_db is get_db
    assert world_chat.get_current_user is get_current_user
    assert world_chat_response.get_current_user is get_current_user
    endpoints = [
        route.endpoint
        for route, _ in _iter_routes_with_context(app.routes)
        if hasattr(route, "endpoint")
    ]
    assert messages.list_threads in endpoints
    assert world_chat.get_world_chat_entry in endpoints
    assert world_chat_response.stream_world_response_events in endpoints


def test_request_injected_service_receives_the_original_session_and_user():
    session = object()
    user = SimpleNamespace(id="owner")
    calls = []

    def list_threads(db, principal):
        calls.append((db, principal))
        return {"items": []}

    app = FastAPI()
    message_composition.configure_chat_services(app)
    app.state.chat_thread_service = SimpleNamespace(list_threads=list_threads)
    app.include_router(messages.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    response = TestClient(app).get("/api/v1/messages/threads")
    assert response.status_code == 200
    assert response.json() == {"items": [], "max_threads": 5}
    assert calls == [(session, user)]


def test_stream_uses_injected_generation_and_preserves_ndjson_and_runtime_context():
    session = object()
    user = SimpleNamespace(id="owner")
    memory = object()
    config = object()
    calls = []
    event = SimpleNamespace(
        protocol_version="chat-generation.v1",
        request_id="request",
        request_scope_hash="scope",
        generation_id="generation",
        attempt_number=1,
        sequence=2,
        event_type=GenerationEventType.ACCEPTED,
        payload={"text": "앵무"},
    )

    def read(*args):
        calls.append(("read", args))
        return SimpleNamespace(state="accepted")

    async def stream(*args, **kwargs):
        calls.append(("stream", args, kwargs))
        yield event

    app = FastAPI()
    message_composition.configure_chat_services(app)
    app.state.chat_generation_service = SimpleNamespace(
        get_world_response_request=read,
        stream_world_response=stream,
    )
    app.state.runtime_composition = SimpleNamespace(
        memory_recall_service=memory, settings=config
    )
    app.include_router(world_chat_response.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    response = TestClient(app, base_url="http://127.0.0.1:3000").get(
        "/api/v1/worlds/world/chat/threads/thread/requests/request/events",
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    payload = {
        "protocol_version": event.protocol_version,
        "request_id": "request",
        "request_scope_hash": "scope",
        "generation_id": "generation",
        "attempt_number": 1,
        "sequence": 2,
        "type": "accepted",
        "payload": {"text": "앵무"},
    }
    assert response.content == (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    assert calls == [
        ("read", (session, user, "world", "thread", "request")),
        (
            "stream",
            (session, user, "world", "thread", "request"),
            {"memory_recall_service": memory, "runtime_settings": config},
        ),
    ]


def test_missing_service_configuration_does_not_construct_an_implicit_fallback():
    request = Request({"type": "http", "app": FastAPI()})
    with pytest.raises(RuntimeError, match="Chat generation_service is not configured"):
        dependencies.get_generation_service(request)
