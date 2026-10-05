"""World deletion through real routers and file SQLite, without provider work."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from model_fixture_support import models
from chat.test_p8_l_d_world_chat_api import _seed, FRONTEND_HEADERS
from app.database import get_db
from app.domains.identity.dependencies import get_current_user
from app.models import Base
from app.domains.media.models import MediaAsset
from app.domains.chat.models import MessageAttachment
from app.domains.chat import schemas
from app.domains.chat.contracts.generation_lifecycle import (
    GenerationContractError, GenerationFence, ResponseRequestState, ResponseTerminalReason, TERMINAL_STATES,
)
from app.domains.chat.exceptions import MessageInFlightError, MessageNotFoundError
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.router.messages import router as legacy_router
from app.domains.chat.router.world_chat import entry_router, router as thread_router
from app.domains.chat.router.world_chat_response import router as response_router
from app.domains.chat.service import generation as generation_module, threads as thread_module
from app.runtime.chat.message_composition import configure_chat_services


@pytest.fixture
def chat_delete_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'world-chat-delete.sqlite3'}",
                          connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    principal = {"user": None}
    app = FastAPI()
    configure_chat_services(app)
    app.include_router(thread_router, prefix="/api/v1")
    app.include_router(entry_router, prefix="/api/v1")
    app.include_router(response_router, prefix="/api/v1")
    app.include_router(legacy_router, prefix="/api/v1")

    def database():
        with Session(engine) as db:
            yield db

    def user():
        if principal["user"] is None:
            raise HTTPException(401, "Invalid token")
        return principal["user"]

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = user
    owner, outsider, responding_id = _seed(engine, principal)
    with TestClient(app, base_url="http://127.0.0.1:3000") as client:
        created = client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
                              json={"responding_world_character_id": responding_id})
        assert created.status_code == 200
        yield client, engine, principal, owner, outsider, created.json()["thread"]["id"]
    engine.dispose()


def _path(thread_id):
    return f"/api/v1/worlds/world-a/chat/threads/{thread_id}"


def _accept(app, db, owner, thread_id, suffix="first"):
    return app.state.chat_generation_service.accept_world_message(
        db, owner, "world-a", thread_id,
        schemas.WorldChatMessageCreate(content="Synthetic retained message",
                                       idempotency_key=f"delete-test-key-{suffix}"),
    )


def _fail(app, db, owner, thread_id):
    accepted = _accept(app, db, owner, thread_id)
    repository = SqlAlchemyResponseLifecycleRepository(db)
    now = datetime.now(UTC)
    record = repository.acquire_lease(request_id=accepted.response_request.request_id,
        lease_token="synthetic-delete-lease", now=now, lease_expires_at=now + timedelta(seconds=30))
    fence = GenerationFence(request_id=record.request_id, thread_id=record.thread_id,
        request_scope_hash=record.request_scope_hash, generation_id=record.generation_id,
        attempt_number=record.attempt_number,
        lease_generation=record.lease_generation, expected_prior_state=record.state)
    repository.mark_terminal(fence, target=ResponseRequestState.FAILED,
        reason=ResponseTerminalReason.PROVIDER_FAILURE, retryable=True,
        failure_class="synthetic_failure", now=now)
    db.commit()
    return accepted.response_request.request_id


def test_soft_delete_preserves_rows_replays_timestamp_and_creates_new_identity(chat_delete_fixture):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    with Session(engine) as db:
        request_id = _fail(client.app, db, owner, thread_id)
        message_id = db.get(models.ChatResponseRequest, request_id).user_message_id
        db.add_all([
            MediaAsset(id="retained-chat-photo", owner_id=owner.id, scope_kind="thread", scope_id=thread_id,
                storage_key="synthetic-retained-chat-photo.webp", content_type="image/webp", content_hash="a" * 64,
                byte_size=42, width=1, height=1, state="attached"),
            models.Post(id="retained-world-post", world_id="world-a", author_world_character_id="wc-responding",
                author_character_id="responding-character", author_name="Synthetic responder", title="Preserved SNS",
                body="Synthetic public history"),
            models.MemoryItem(id="retained-chat-memory", owner_id="responder-owner", world_id="world-a",
                subject_world_character_id="wc-responding", counterpart_world_character_id="wc-requester",
                thread_id=thread_id, memory_kind="THREAD_SUMMARY", summary="Synthetic remembered conversation",
                confidence=0.9, salience=0.8),
            models.RelationshipState(id="retained-chat-relationship", world_id="world-a",
                actor_world_character_id="wc-responding", target_world_character_id="wc-requester",
                familiarity=8, affinity=4, interaction_count=3),
        ])
        db.flush()
        db.add_all([
            MessageAttachment(message_id=message_id, asset_id="retained-chat-photo"),
            models.MemoryItemEvidence(id="retained-chat-evidence", memory_item_id="retained-chat-memory",
                source_type="CHAT_MESSAGE", source_id=str(message_id), source_world_id="world-a",
                actor_world_character_id="wc-requester", target_world_character_id="wc-responding",
                source_created_at=datetime.now(UTC), source_digest="b" * 64),
        ])
        db.commit()
        before_counts = {table.name: db.scalar(select(func.count()).select_from(table))
                         for table in Base.metadata.tables.values()}
        thread = db.get(models.MessageThread, thread_id)
        thread.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
        db.commit()
        before_rows = {table.name: deepcopy([dict(row) for row in db.execute(
            select(table).order_by(*table.primary_key.columns)).mappings()]) for table in Base.metadata.tables.values()}
    result = client.delete(_path(thread_id), headers=FRONTEND_HEADERS)
    assert result.status_code == 200
    assert result.json() == {"world_id": "world-a", "thread_id": thread_id, "outcome": "deleted"}
    with Session(engine) as db:
        timestamp = db.get(models.MessageThread, thread_id).deleted_at
        assert timestamp is not None
        assert db.get(models.ChatResponseRequest, request_id).state == "failed"
        assert db.scalar(select(func.count(models.MessageMessage.id))) == 1
        assert {table.name: db.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.tables.values()} == before_counts
        after_rows = {table.name: [dict(row) for row in db.execute(
            select(table).order_by(*table.primary_key.columns)).mappings()] for table in Base.metadata.tables.values()}
        for rows in (before_rows[models.MessageThread.__tablename__], after_rows[models.MessageThread.__tablename__]):
            for row in rows:
                row.pop("deleted_at")
        assert after_rows == before_rows
    assert client.get("/api/v1/worlds/world-a/chat/threads").json()["items"] == []
    assert client.get(_path(thread_id)).status_code == 404
    assert client.get(_path(thread_id) + "/requests/latest").status_code == 404
    assert client.post(_path(thread_id) + "/messages", headers=FRONTEND_HEADERS,
                       json={"content": "old send", "idempotency_key": "delete-old-send-key"}).status_code == 404
    assert client.post(_path(thread_id) + "/retry", headers=FRONTEND_HEADERS,
                       json={"failed_request_id": request_id, "idempotency_key": "delete-old-retry-key"}).status_code == 404
    assert client.get(_path(thread_id) + f"/requests/{request_id}/events").status_code == 404
    replay = client.delete(_path(thread_id), headers=FRONTEND_HEADERS)
    assert replay.status_code == 200 and replay.json()["outcome"] == "already_deleted"
    with Session(engine) as db:
        assert db.get(models.MessageThread, thread_id).deleted_at == timestamp
    fresh = client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
                        json={"responding_world_character_id": "wc-responding"})
    assert fresh.status_code == 200 and fresh.json()["outcome"] == "created"
    assert fresh.json()["thread"]["id"] != thread_id and fresh.json()["thread"]["messages"] == []
    with Session(engine) as db:
        assert db.scalar(select(func.count(models.ChatResponseRequest.request_id))) == 1
        assert db.scalar(select(func.count(models.MessageMessage.id))) == 1
        assert db.scalar(select(func.count(models.MessageThread.id))) == 2


def test_delete_permission_and_frontend_identity_do_not_change_storage(chat_delete_fixture):
    client, engine, principal, owner, outsider, thread_id = chat_delete_fixture
    principal["user"] = None
    assert client.delete(_path(thread_id), headers=FRONTEND_HEADERS).status_code == 401
    principal["user"] = outsider
    assert client.delete(_path(thread_id), headers=FRONTEND_HEADERS).status_code == 403
    principal["user"] = owner
    assert client.delete(_path(thread_id)).status_code == 403
    assert client.delete(_path(thread_id), headers={"Origin": "https://example.test"}).status_code == 403
    assert client.delete(_path(thread_id).replace("world-a", "world-other"), headers=FRONTEND_HEADERS).status_code == 404
    assert client.delete(_path("missing"), headers=FRONTEND_HEADERS).status_code == 404
    assert client.delete(f"/api/v1/messages/threads/{thread_id}").status_code == 422
    with Session(engine) as db:
        assert db.get(models.MessageThread, thread_id).deleted_at is None
        db.get(models.MessageThread, thread_id).requester_id = outsider.id
        db.commit()
    assert client.delete(_path(thread_id), headers=FRONTEND_HEADERS).status_code == 404
    with Session(engine) as db:
        assert db.get(models.MessageThread, thread_id).deleted_at is None


def test_inactive_counterpart_is_still_owned_and_cleanable(chat_delete_fixture):
    client, engine, _principal, _owner, _outsider, thread_id = chat_delete_fixture
    with Session(engine) as db:
        db.get(models.WorldCharacter, "wc-responding").status = "inactive"
        db.get(models.Character, "responding-character").status = "inactive"
        db.commit()
    assert client.delete(_path(thread_id), headers=FRONTEND_HEADERS).status_code == 200
    with Session(engine) as db:
        assert db.get(models.WorldCharacter, "wc-responding").status == "inactive"
        assert db.get(models.Character, "responding-character").status == "inactive"


@pytest.mark.parametrize("state", [state.value for state in ResponseRequestState if state not in TERMINAL_STATES])
def test_every_nonterminal_state_refuses_delete_without_touching_request_or_lease(chat_delete_fixture, state):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    with Session(engine) as db:
        accepted = _accept(client.app, db, owner, thread_id)
        row = db.get(models.ChatResponseRequest, accepted.response_request.request_id)
        row.state = state
        row.lease_token = "retained-lease"
        row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
        db.commit()
        before = db.execute(select(models.ChatResponseRequest.__table__)).mappings().one()
    response = client.delete(_path(thread_id), headers=FRONTEND_HEADERS)
    assert response.status_code == 409
    assert response.json()["detail"] == "world_chat_response_in_flight"
    with Session(engine) as db:
        assert db.execute(select(models.ChatResponseRequest.__table__)).mappings().one() == before
        assert db.get(models.MessageThread, thread_id).deleted_at is None
        assert db.scalar(select(func.count(models.MessageMessage.id))) == 1


def test_expired_response_uses_existing_lifecycle_before_user_retries_delete(chat_delete_fixture):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    with Session(engine) as db:
        accepted = _accept(client.app, db, owner, thread_id)
        leased_at = datetime.now(UTC)
        record = SqlAlchemyResponseLifecycleRepository(db).acquire_lease(
            request_id=accepted.response_request.request_id, lease_token="synthetic-expired-worker",
            now=leased_at, lease_expires_at=leased_at + timedelta(seconds=30))
        old_fence = GenerationFence(request_id=record.request_id, thread_id=record.thread_id,
            request_scope_hash=record.request_scope_hash, generation_id=record.generation_id,
            attempt_number=record.attempt_number, lease_generation=record.lease_generation,
            expected_prior_state=record.state)
        db.get(models.ChatResponseRequest, accepted.response_request.request_id).deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.delete(_path(thread_id), headers=FRONTEND_HEADERS).status_code == 409
    latest = client.get(_path(thread_id) + "/requests/latest")
    assert latest.status_code == 200 and latest.json()["response_request"]["state"] == "timed_out"
    assert client.delete(_path(thread_id), headers=FRONTEND_HEADERS).status_code == 200
    with Session(engine) as db:
        request = db.get(models.ChatResponseRequest, accepted.response_request.request_id)
        assert request.state == "timed_out" and request.lease_token is None
        before = db.execute(select(models.ChatResponseRequest.__table__)).mappings().one()
        repository = SqlAlchemyResponseLifecycleRepository(db)
        with pytest.raises(GenerationContractError, match="response_transition_fence_conflict"):
            repository.transition(old_fence, target=ResponseRequestState.PREFLIGHTED, now=datetime.now(UTC))
        with pytest.raises(GenerationContractError, match="response_lease_renew_conflict"):
            repository.renew_lease(old_fence, lease_token="synthetic-expired-worker", now=datetime.now(UTC),
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=30))
        assert db.execute(select(models.ChatResponseRequest.__table__)).mappings().one() == before
        assert db.scalar(select(func.count(models.MessageMessage.id)).where(models.MessageMessage.role == "assistant")) == 0
        assert db.get(models.MessageThread, thread_id).deleted_at is not None


@pytest.mark.parametrize("operation", ["accept", "retry", "model"])
@pytest.mark.parametrize("delete_first", [False, True])
def test_two_sessions_serialize_admission_retry_model_and_delete(chat_delete_fixture, monkeypatch, operation, delete_first):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    failed_id = None
    if operation == "retry":
        with Session(engine) as db:
            failed_id = _fail(client.app, db, owner, thread_id)
    held, second_attempted, release = Event(), Event(), Event()
    original_lock = thread_module.lock_environment_admission

    def lock(db, owner_id=None):
        if db.info["race_lane"] == "second":
            second_attempted.set()
        original_lock(db, owner_id)
        if db.info["race_lane"] == "first":
            held.set()
            assert release.wait(10)

    monkeypatch.setattr(thread_module, "lock_environment_admission", lock)
    monkeypatch.setattr(generation_module, "lock_environment_admission", lock)

    def run(deleting, lane):
        with Session(engine) as db:
            db.info["race_lane"] = lane
            try:
                if deleting:
                    return client.app.state.chat_thread_service.delete_world_thread(db, owner, "world-a", thread_id).outcome
                if operation == "accept":
                    return _accept(client.app, db, owner, thread_id, "race").outcome
                if operation == "retry":
                    return client.app.state.chat_generation_service.retry_world_response(db, owner, "world-a", thread_id,
                        schemas.WorldChatRetryCreate(failed_request_id=failed_id, idempotency_key="delete-race-retry-key")).outcome
                client.app.state.chat_thread_service.update_world_thread_model(db, owner, "world-a", thread_id,
                    schemas.WorldChatThreadModelUpdate(mode="thread_override", selected_model="gemini-3.1-flash-lite"))
                return "model_updated"
            except MessageInFlightError:
                return "409"
            except MessageNotFoundError:
                return "404"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run, delete_first, "first")
        assert held.wait(10)
        second = executor.submit(run, not delete_first, "second")
        assert second_attempted.wait(10)
        release.set()
        results = [first.result(timeout=15), second.result(timeout=15)]
    if delete_first:
        assert results == ["deleted", "404"]
    elif operation == "model":
        assert results == ["model_updated", "deleted"]
    else:
        assert results == ["accepted", "409"]
    with Session(engine) as db:
        deleted = db.get(models.MessageThread, thread_id).deleted_at is not None
        assert deleted == (delete_first or operation == "model")
        assert db.scalar(select(func.count(models.MessageMessage.id))) == (1 if operation == "retry" or (operation == "accept" and not delete_first) else 0)
        assert db.scalar(select(func.count(models.ChatResponseRequest.request_id))) == (2 if operation == "retry" and not delete_first else 1 if operation == "retry" or (operation == "accept" and not delete_first) else 0)
