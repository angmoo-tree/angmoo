from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.core.db import Base, get_db
from app.api.v1.routes.messages import router as messages_router
from app.api.v1.routes.world_chat import router as world_chat_router


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
    app.include_router(messages_router, prefix="/api/v1")
    app.include_router(world_chat_router, prefix="/api/v1")

    def db_dependency():
        with Session(engine) as db:
            yield db

    def user_dependency() -> models.User:
        user = principal["user"]
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        return user

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = user_dependency
    client = TestClient(app, base_url="http://127.0.0.1:3000")
    return client, engine, principal


def _seed(engine, principal) -> tuple[models.User, models.User, str]:
    owner = _user("owner")
    outsider = _user("outsider")
    responder_owner = _user("responder-owner")
    requester_character = _character("requester-character", owner.id)
    responding_character = _character("responding-character", responder_owner.id)
    now = datetime.now(UTC)
    world = models.World(
        id="world-a",
        slug="world-a",
        owner_user_id=owner.id,
        name="World A",
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
        create_idempotency_key="world-a",
    )
    owner_membership = models.WorldMembership(
        id="membership-owner",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=now,
    )
    responder_membership = models.WorldMembership(
        id="membership-responder",
        world_id=world.id,
        user_id=responder_owner.id,
        role="member",
        status="active",
        joined_at=now,
    )
    requester = models.WorldCharacter(
        id="wc-requester",
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
        id="wc-responding",
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
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, outsider, responder_owner])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="p8-l-d-api-fixture",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="P8-L-D API fixture",
                claimed_at=now,
            )
        )
        db.add_all([requester_character, responding_character, world])
        db.flush()
        db.add_all([owner_membership, responder_membership])
        db.flush()
        db.add_all([requester, responding])
        db.commit()
    principal["user"] = owner
    return owner, outsider, responding.id


def test_world_chat_api_exposes_the_three_d_owned_operations() -> None:
    client, _engine, _principal = _fixture()
    paths = client.app.openapi()["paths"]
    assert set(paths["/api/v1/worlds/{world_id}/chat/threads"]) == {
        "get",
        "post",
    }
    assert set(paths["/api/v1/worlds/{world_id}/chat/threads/{thread_id}"]) == {
        "get"
    }

    create_operation = paths["/api/v1/worlds/{world_id}/chat/threads"]["post"]
    request_schema = create_operation["requestBody"]["content"][
        "application/json"
    ]["schema"]
    schema_name = request_schema["$ref"].rsplit("/", 1)[-1]
    properties = client.app.openapi()["components"]["schemas"][schema_name][
        "properties"
    ]
    assert "owner_id" not in properties
    assert "requester_id" not in properties


def test_world_chat_api_owner_body_spoof_cannot_change_canonical_owner() -> None:
    client, engine, principal = _fixture()
    owner, _outsider, responding_id = _seed(engine, principal)

    response = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json={
            "responding_world_character_id": responding_id,
            "owner_id": "attacker",
            "requester_id": "attacker",
        },
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "created"
    with Session(engine) as db:
        row = db.scalar(select(models.MessageThread))
        assert row is not None
        assert row.requester_id == owner.id
        assert row.requester_world_character_id == "wc-requester"

    requester_spoof = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json={
            "responding_world_character_id": responding_id,
            "requester_world_character_id": "wc-attacker",
        },
    )
    assert requester_spoof.status_code == 403
    with Session(engine) as db:
        assert len(list(db.scalars(select(models.MessageThread)))) == 1


def test_world_chat_api_list_and_get_do_not_cross_owner_or_world() -> None:
    client, engine, principal = _fixture()
    owner, outsider, responding_id = _seed(engine, principal)
    created = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json={"responding_world_character_id": responding_id},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread"]["id"]

    principal["user"] = outsider
    other_owner_list = client.get("/api/v1/worlds/world-a/chat/threads")
    assert other_owner_list.status_code == 403
    assert client.get(
        f"/api/v1/worlds/world-a/chat/threads/{thread_id}"
    ).status_code == 403

    principal["user"] = owner
    other_world_list = client.get("/api/v1/worlds/world-b/chat/threads")
    assert other_world_list.status_code == 404
    assert client.get(
        f"/api/v1/worlds/world-b/chat/threads/{thread_id}"
    ).status_code == 404


def test_world_chat_api_stale_participant_membership_is_not_readable() -> None:
    client, engine, principal = _fixture()
    _owner, _outsider, responding_id = _seed(engine, principal)
    created = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json={"responding_world_character_id": responding_id},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread"]["id"]

    with Session(engine) as db:
        membership = db.get(models.WorldMembership, "membership-responder")
        assert membership is not None
        membership.status = "left"
        db.commit()

    listing = client.get("/api/v1/worlds/world-a/chat/threads")
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    detail = client.get(f"/api/v1/worlds/world-a/chat/threads/{thread_id}")
    assert detail.status_code == 404


def test_resolved_world_thread_legacy_endpoints_are_redirect_only() -> None:
    client, engine, principal = _fixture()
    owner, _outsider, responding_id = _seed(engine, principal)
    created = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json={"responding_world_character_id": responding_id},
    )
    assert created.status_code == 200
    thread_id = created.json()["thread"]["id"]
    with Session(engine) as db:
        db.add(
            models.MessageMessage(
                thread_id=thread_id,
                role="user",
                content="legacy endpoint에서 숨겨야 하는 원문",
                model="gemini-2.5-flash-lite",
                status="ok",
            )
        )
        db.commit()

    listing = client.get("/api/v1/messages/threads")
    assert listing.status_code == 200
    resolved = next(
        item for item in listing.json()["items"] if item["id"] == thread_id
    )
    assert resolved["world_scope_status"] == "resolved"
    assert resolved["world_id"] == "world-a"
    assert resolved["latest_message"] is None
    assert resolved["messages"] == []

    detail = client.get(f"/api/v1/messages/threads/{thread_id}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []
    assert detail.json()["latest_message"] is None

    assert client.patch(
        f"/api/v1/messages/threads/{thread_id}",
        json={"selected_model": "gemini-2.5-flash"},
    ).status_code == 422
    assert client.delete(f"/api/v1/messages/threads/{thread_id}").status_code == 422
    assert client.post(
        f"/api/v1/messages/threads/{thread_id}/messages",
        json={"content": "legacy send 차단"},
    ).status_code == 422
    assert client.post(
        f"/api/v1/messages/threads/{thread_id}/messages/1/retry"
    ).status_code == 422

    with Session(engine) as db:
        thread = db.get(models.MessageThread, thread_id)
        assert thread is not None
        assert thread.requester_id == owner.id
        assert thread.deleted_at is None
        assert thread.selected_model == "gemini-2.5-flash-lite"
        assert len(list(db.scalars(select(models.MessageMessage)))) == 1


def test_claimed_local_installation_legacy_create_requires_world_chat() -> None:
    client, engine, principal = _fixture()
    owner, _outsider, _responding_id = _seed(engine, principal)
    target = _character("legacy-target", owner.id)
    target.execution_mode = "llm"
    target_id = target.id
    with Session(engine) as db:
        db.add(target)
        db.commit()

    response = client.post(
        "/api/v1/messages/threads",
        json={"character_id": target_id},
    )
    assert response.status_code == 422
    assert "World Chat에서 시작" in response.json()["detail"]
    with Session(engine) as db:
        assert list(db.scalars(select(models.MessageThread))) == []
