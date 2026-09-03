from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api.v1.deps import get_current_user
from app.api.v1.routes.memory import router as memory_router
from app.api.v1.routes.world_chat_response import router as response_router
from app.core.db import Base, get_db
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from app.domains.memory.public import (
    MemoryEvidenceAvailability,
    MemoryKindV1,
    MemoryReadService,
    MemoryScope,
    MemoryScopeService,
    MemorySourceTypeV1,
    MemoryWriteLifecycleService,
)
from app.runtime.memory import SqlAlchemyMemorySourceEvidenceReader


NOW = datetime(2026, 9, 3, 9, tzinfo=UTC)
FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        display_name_normalized=user_id,
        privacy_policy_version="test",
        terms_version="test",
        profile_setup_completed=True,
    )


def _character(character_id: str, owner_id: str, name: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=name,
        handle=character_id,
        one_liner="fixture",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="memory",
        safety_rules="safe",
        status="active",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


def _world_character(
    identifier: str,
    *,
    world_id: str,
    character_id: str,
    membership_id: str,
    owner_id: str | None,
) -> models.WorldCharacter:
    return models.WorldCharacter(
        id=identifier,
        world_id=world_id,
        character_id=character_id,
        membership_id=membership_id,
        role_key="no_specific_role",
        status="active",
        control_mode="owner_controlled" if owner_id else "autonomous",
        owner_user_id=owner_id,
        autonomous_enabled=owner_id is None,
        version=1,
    )


def _fixture() -> tuple[TestClient, object, dict[str, models.User | None]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    principal: dict[str, models.User | None] = {"user": None}
    app = FastAPI()
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(response_router, prefix="/api/v1")

    def db_dependency():
        with Session(engine) as db:
            yield db

    def user_dependency() -> models.User:
        user = principal["user"]
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return user

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = user_dependency
    return (
        TestClient(app, base_url="http://127.0.0.1:3000"),
        engine,
        principal,
    )


def _seed(engine, principal) -> dict[str, object]:
    owner = _user("q-owner")
    outsider = _user("q-outsider")
    responder_owner = _user("q-responder-owner")
    requester_character = _character("q-requester-character", owner.id, "하루")
    responding_character = _character(
        "q-responding-character", responder_owner.id, "이즈쿠"
    )
    world = models.World(
        id="q-world",
        slug="q-world",
        owner_user_id=owner.id,
        name="Q World",
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
        contract_hash="q" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="q-world",
    )
    owner_membership = models.WorldMembership(
        id="q-owner-membership",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=NOW,
    )
    responder_membership = models.WorldMembership(
        id="q-responder-membership",
        world_id=world.id,
        user_id=responder_owner.id,
        role="member",
        status="active",
        joined_at=NOW,
    )
    requester = _world_character(
        "q-requester",
        world_id=world.id,
        character_id=requester_character.id,
        membership_id=owner_membership.id,
        owner_id=owner.id,
    )
    responding = _world_character(
        "q-responding",
        world_id=world.id,
        character_id=responding_character.id,
        membership_id=responder_membership.id,
        owner_id=None,
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, outsider, responder_owner])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="p8-l-q-installation",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="P8-L-Q fixture",
                claimed_at=NOW,
            )
        )
        db.add_all([requester_character, responding_character, world])
        db.flush()
        db.add_all([owner_membership, responder_membership])
        db.flush()
        db.add_all([requester, responding])
        db.flush()
        thread = models.MessageThread(
            id="q-thread",
            requester_id=owner.id,
            character_id=responding_character.id,
            world_id=world.id,
            requester_world_character_id=requester.id,
            responding_world_character_id=responding.id,
            world_scope_status="resolved",
            selected_model="gemini-3.1-flash-lite",
            model_binding_mode="thread_override",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(thread)
        db.flush()
        source_message = models.MessageMessage(
            thread_id=thread.id,
            role="assistant",
            content="오늘 훈련을 마치고 함께 한 약속을 지켰어.",
            status="ok",
            created_at=NOW,
        )
        user_message = models.MessageMessage(
            thread_id=thread.id,
            role="user",
            content="그 약속을 기억해?",
            status="ok",
            created_at=NOW + timedelta(minutes=1),
        )
        response_message = models.MessageMessage(
            thread_id=thread.id,
            role="assistant",
            content="응, 함께 한 약속을 기억하고 있어.",
            status="ok",
            created_at=NOW + timedelta(minutes=2),
        )
        db.add_all([source_message, user_message, response_message])
        db.flush()

        scope = MemoryScope(owner.id, world.id, responding.id)
        repository = SqlAlchemyMemoryRepository(db)
        scope_service = MemoryScopeService(repository)
        initial = scope_service.get_or_create(scope)
        enabled = scope_service.update(
            scope,
            expected_version=initial.version,
            enabled=True,
            retention_days=180,
        )
        source_reader = SqlAlchemyMemorySourceEvidenceReader(db)
        lifecycle = MemoryWriteLifecycleService(repository, source_reader)
        proposal = lifecycle.propose_candidate(
            scope=scope,
            source_type=MemorySourceTypeV1.CHAT_MESSAGE,
            source_id=str(source_message.id),
            memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT,
        )
        assert proposal.candidate is not None
        accepted = lifecycle.accept_candidate(
            scope=scope,
            candidate_id=proposal.candidate.id,
            expected_candidate_version=proposal.candidate.version,
            expected_scope_version=enabled.version,
            now=NOW,
        )
        assert accepted.item is not None
        scope_service.update(
            scope,
            expected_version=enabled.version,
            enabled=False,
            retention_days=180,
        )

        fresh = source_reader.read_evidence(
            scope=scope,
            source_type=MemorySourceTypeV1.CHAT_MESSAGE,
            source_id=str(source_message.id),
        )
        assert fresh is not None
        inspector_snapshot = {
            "version": "evidence-inspector.v1",
            "items": [
                {
                    "ref": "evidence-q-source",
                    "kind": "canonical_source",
                    "text": source_message.content,
                    "occurred_at": NOW.isoformat(),
                    "axes": ["canonical"],
                    "locator": {
                        "kind": "canonical_source",
                        "source_type": "CHAT_MESSAGE",
                        "source_id": str(source_message.id),
                        "source_revision": fresh.source_digest,
                        "actor_world_character_id": responding.id,
                        "target_world_character_id": requester.id,
                    },
                }
            ],
        }
        db.add(
            models.ChatResponseRequest(
                request_id="q-response-request",
                thread_id=thread.id,
                user_message_id=user_message.id,
                response_slot_id="q-response-slot",
                request_scope_hash="a" * 64,
                idempotency_key="q-response-idempotency",
                generation_id="q-generation",
                attempt_number=1,
                selected_model="gemini-3.1-flash-lite",
                route="CANONICAL",
                workflow_recipe=None,
                state="committed",
                last_emitted_sequence=2,
                terminal_reason="committed",
                retryable=False,
                committed_assistant_message_id=response_message.id,
                node_state_json="{}",
                call_tracker_json="{}",
                response_metadata_json=json.dumps(
                    {
                        "route": "CANONICAL",
                        "retrieval_outcome": "memory_used",
                        "evidence_capability": "available",
                        "public_evidence_count": 1,
                        "_evidence_inspector_v1": inspector_snapshot,
                    }
                ),
                deadline_at=NOW + timedelta(minutes=5),
                terminal_at=NOW + timedelta(minutes=2),
            )
        )
        db.commit()
        result = {
            "owner": owner,
            "outsider": outsider,
            "scope": scope,
            "memory_id": accepted.item.id,
            "source_message_id": source_message.id,
            "response_message_id": response_message.id,
        }
    principal["user"] = owner
    return result


def test_setting_get_is_side_effect_free_and_defaults_to_off() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    with Session(engine) as db:
        before = db.scalar(
            select(func.count()).select_from(models.MemoryScopeSettingModel)
        )

    response = client.get(
        "/api/v1/worlds/q-world/world-characters/q-requester/memory/settings",
        headers=FRONTEND_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["enabled"] is False
    assert response.json()["capabilities"]["mutate"] == "not_available_in_p8_l_q"
    with Session(engine) as db:
        after = db.scalar(
            select(func.count()).select_from(models.MemoryScopeSettingModel)
        )
    assert after == before
    assert seeded["memory_id"]


def test_memory_off_keeps_existing_scoped_items_readable() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    memory_id = seeded["memory_id"]

    listing = client.get(
        "/api/v1/worlds/q-world/world-characters/q-responding/memories",
        headers=FRONTEND_HEADERS,
    )
    detail = client.get(
        f"/api/v1/worlds/q-world/world-characters/q-responding/memories/{memory_id}",
        headers=FRONTEND_HEADERS,
    )

    assert listing.status_code == 200
    assert listing.json()["memory_enabled"] is False
    assert [item["id"] for item in listing.json()["items"]] == [memory_id]
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["summary"] == "오늘 훈련을 마치고 함께 한 약속을 지켰어."
    assert payload["evidence"][0]["availability"] == "available"
    assert payload["evidence"][0]["excerpt"] == payload["summary"]
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "source_id" not in encoded
    assert "prompt" not in encoded
    assert "provider" not in encoded


def test_memory_detail_revalidates_source_revision_and_hides_stale_text() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    scope = seeded["scope"]
    memory_id = str(seeded["memory_id"])
    with Session(engine) as db:
        source = db.get(models.MessageMessage, seeded["source_message_id"])
        assert source is not None
        source.content = "나중에 수정된 내용"
        db.commit()
        detail = MemoryReadService(
            SqlAlchemyMemoryRepository(db),
            SqlAlchemyMemorySourceEvidenceReader(db),
        ).detail(scope, item_id=memory_id, now=NOW)

    assert detail.evidence[0].availability is MemoryEvidenceAvailability.UNAVAILABLE
    assert detail.evidence[0].excerpt is None


def test_memory_api_fails_closed_for_cross_subject_and_cross_owner() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    memory_id = seeded["memory_id"]

    cross_subject = client.get(
        f"/api/v1/worlds/q-world/world-characters/q-requester/memories/{memory_id}",
        headers=FRONTEND_HEADERS,
    )
    principal["user"] = seeded["outsider"]
    cross_owner = client.get(
        "/api/v1/worlds/q-world/world-characters/q-responding/memories",
        headers=FRONTEND_HEADERS,
    )

    assert cross_subject.status_code == 404
    assert cross_owner.status_code == 404


def test_chat_inspector_revalidates_and_never_leaks_hidden_locator() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    path = (
        "/api/v1/worlds/q-world/chat/threads/q-thread/requests/"
        "q-response-request/evidence"
    )

    current = client.get(path, headers=FRONTEND_HEADERS)
    assert current.status_code == 200
    payload = current.json()
    assert payload["items"][0]["availability"] == "available"
    assert payload["items"][0]["excerpt"] == (
        "오늘 훈련을 마치고 함께 한 약속을 지켰어."
    )
    encoded = json.dumps(payload, ensure_ascii=False)
    assert all("source_id" not in item for item in payload["items"])
    assert "source_revision" not in encoded
    assert "locator" not in encoded

    with Session(engine) as db:
        source = db.get(models.MessageMessage, seeded["source_message_id"])
        assert source is not None
        source.content = "수정되어 더는 같은 근거가 아닌 내용"
        db.commit()

    stale = client.get(path, headers=FRONTEND_HEADERS)
    assert stale.status_code == 200
    assert stale.json()["capability"] == "degraded"
    assert stale.json()["items"][0]["availability"] == "unavailable"
    assert stale.json()["items"][0]["excerpt"] is None
    assert stale.json()["items"][0]["canonical_href"] is None


def test_chat_inspector_is_not_available_to_an_outsider() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    principal["user"] = seeded["outsider"]

    response = client.get(
        "/api/v1/worlds/q-world/chat/threads/q-thread/requests/"
        "q-response-request/evidence",
        headers=FRONTEND_HEADERS,
    )

    assert response.status_code in {403, 404}


def test_chat_inspector_degrades_an_item_without_a_revalidation_locator() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    with Session(engine) as db:
        row = db.get(models.ChatResponseRequest, "q-response-request")
        assert row is not None
        metadata = json.loads(row.response_metadata_json)
        metadata["_evidence_inspector_v1"]["items"][0]["locator"] = None
        row.response_metadata_json = json.dumps(metadata)
        db.commit()

    response = client.get(
        "/api/v1/worlds/q-world/chat/threads/q-thread/requests/"
        "q-response-request/evidence",
        headers=FRONTEND_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["capability"] == "degraded"
    assert response.json()["items"][0]["availability"] == "unavailable"
    assert response.json()["items"][0]["excerpt"] is None
    assert response.json()["items"][0]["canonical_href"] is None
