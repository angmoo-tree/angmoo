from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.api.v1.routes.manual_social import router as manual_social_router
from app.api.v1.routes.world_chat import entry_router
from app.api.v1.routes.world_chat import router as world_chat_router
from app.core.db import Base, get_db
from app.domains.world_characters.router.profile import router as world_character_router

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


def _character(
    character_id: str,
    owner_id: str,
    *,
    display_name: str,
    handle: str,
) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=display_name,
        handle=handle,
        one_liner=f"{display_name}의 공개 소개",
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
    app.include_router(world_character_router, prefix="/api/v1")
    app.include_router(entry_router, prefix="/api/v1")
    app.include_router(world_chat_router, prefix="/api/v1")
    app.include_router(manual_social_router, prefix="/api/v1")

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


def _seed(engine, principal, *, include_requester: bool = True) -> None:
    owner = _user("owner")
    responder_owner = _user("responder-owner")
    requester_character = _character(
        "requester-character",
        owner.id,
        display_name="사용자 앵무",
        handle="owner_bird",
    )
    responding_character = _character(
        "responding-character",
        responder_owner.id,
        display_name="친구 앵무",
        handle="friend_bird",
    )
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
        role_key="student",
        status="active" if include_requester else "inactive",
        control_mode="owner_controlled",
        owner_user_id=owner.id,
        autonomous_enabled=False,
        local_profile={
            "display_name": "사용자 앵무",
            "intro": "사용자가 조종하는 앵무",
        },
        version=1,
    )
    responding = models.WorldCharacter(
        id="wc-responding",
        world_id=world.id,
        character_id=responding_character.id,
        membership_id=responder_membership.id,
        role_key="mentor",
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
        activity_runtime_mode="routine_resident_v1",
        local_profile={
            "avatar_url": "/media/friend.png",
            "banner_url": "/media/friend-banner.png",
            "display_name": "친구 앵무",
            "intro": "같은 World에서 활동하는 친구",
        },
        version=1,
    )
    post = models.Post(
        id="post-a",
        author_character_id=responding_character.id,
        world_id=world.id,
        author_world_character_id=responding.id,
        post_type="text",
        visibility="public",
        author_name="친구 앵무",
        title="오늘의 기록",
        body="World에서 있었던 일을 적었어요.",
        search_document="오늘의 기록 World에서 있었던 일",
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, responder_owner])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="p8-l-e-api-fixture",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="P8-L-E API fixture",
                claimed_at=now,
            )
        )
        db.add_all([requester_character, responding_character, world])
        db.flush()
        db.add_all([owner_membership, responder_membership])
        db.flush()
        db.add_all([requester, responding])
        db.flush()
        db.add(post)
        db.commit()
    principal["user"] = owner


def test_p8_l_e_api_contract_exposes_profile_and_chat_entry_operations() -> None:
    client, _engine, _principal = _fixture()
    paths = client.app.openapi()["paths"]

    assert set(paths["/api/v1/worlds/{world_id}/world-characters"]) == {"get"}
    assert set(
        paths["/api/v1/worlds/{world_id}/world-characters/{world_character_id}"]
    ) == {"get"}
    assert set(
        paths[
            "/api/v1/worlds/{world_id}/world-characters/{world_character_id}/social-profile"
        ]
    ) == {"get"}
    assert set(
        paths["/api/v1/worlds/{world_id}/world-characters/{responding_id}/chat-entry"]
    ) == {"get"}


def test_profile_and_social_author_use_exact_world_character_identity() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    listing = client.get("/api/v1/worlds/world-a/world-characters")
    assert listing.status_code == 200
    assert listing.json()["schema_version"] == "world-character-profile-list-v1"
    assert {
        (item["world_id"], item["world_character_id"])
        for item in listing.json()["items"]
    } == {("world-a", "wc-requester"), ("world-a", "wc-responding")}

    profile = client.get("/api/v1/worlds/world-a/world-characters/wc-responding")
    assert profile.status_code == 200
    assert profile.json() == {
        "schema_version": "world-character-profile-v1",
        "world_id": "world-a",
        "world_character_id": "wc-responding",
        "character_id": "responding-character",
        "display_name": "친구 앵무",
        "handle": "friend_bird",
        "avatar_url": "/media/friend.png",
        "banner_url": "/media/friend-banner.png",
        "intro": "같은 World에서 활동하는 친구",
        "role_key": "mentor",
        "control_mode": "autonomous",
        "status": "active",
        "profile_capability": "available",
    }

    feed = client.get("/api/v1/worlds/world-a/manual-social/feed")
    assert feed.status_code == 200
    author = feed.json()["items"][0]
    assert author["world_id"] == "world-a"
    assert author["author_world_character_id"] == "wc-responding"
    assert author["author_handle"] == "friend_bird"
    assert author["author_avatar_url"] == "/media/friend.png"
    assert author["author_profile_capability"] == "available"


def test_letter_entry_creates_once_then_reuses_the_active_world_thread() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    entry = client.get(
        "/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry"
    )
    assert entry.status_code == 200
    assert entry.json()["requester_cardinality"] == "one"
    assert entry.json()["requester"]["world_character_id"] == "wc-requester"
    assert entry.json()["responding"]["world_character_id"] == "wc-responding"
    assert entry.json()["create_or_get_capability"] == "available"

    body = {
        "requester_world_character_id": "wc-requester",
        "responding_world_character_id": "wc-responding",
    }
    first = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json=body,
    )
    second = client.post(
        "/api/v1/worlds/world-a/chat/threads",
        headers=FRONTEND_HEADERS,
        json=body,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["outcome"] == "created"
    assert second.json()["outcome"] == "reused"
    assert first.json()["thread"]["id"] == second.json()["thread"]["id"]
    with Session(engine) as db:
        assert len(list(db.scalars(select(models.MessageThread)))) == 1


def test_letter_entry_zero_self_blocked_and_anomaly_fail_closed() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal, include_requester=False)

    zero = client.get(
        "/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry"
    )
    assert zero.status_code == 200
    assert zero.json()["requester_cardinality"] == "zero"
    assert zero.json()["disabled_reason"] == "requester_missing"

    with Session(engine) as db:
        requester = db.get(models.WorldCharacter, "wc-requester")
        assert requester is not None
        requester.status = "active"
        db.commit()

    self_entry = client.get(
        "/api/v1/worlds/world-a/world-characters/wc-requester/chat-entry"
    )
    assert self_entry.status_code == 200
    assert self_entry.json()["disabled_reason"] == "self_target"

    with Session(engine) as db:
        db.add(
            models.WorldCharacterBlock(
                id="block-a",
                world_id="world-a",
                blocker_world_character_id="wc-requester",
                blocked_world_character_id="wc-responding",
            )
        )
        db.commit()
    blocked = client.get(
        "/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry"
    )
    assert blocked.status_code == 200
    assert blocked.json()["disabled_reason"] == "blocked"
    feed = client.get("/api/v1/worlds/world-a/manual-social/feed")
    assert feed.json()["items"][0]["author_profile_capability"] == "unavailable"

    with Session(engine) as db:
        db.execute(text("DROP INDEX uq_world_characters_active_owner_controlled"))
        second_character = _character(
            "requester-character-2",
            "owner",
            display_name="두 번째 사용자 앵무",
            handle="owner_bird_2",
        )
        db.add(second_character)
        db.flush()
        db.add(
            models.WorldCharacter(
                id="wc-requester-2",
                world_id="world-a",
                character_id=second_character.id,
                membership_id="membership-owner",
                role_key="student",
                status="active",
                control_mode="owner_controlled",
                owner_user_id="owner",
                autonomous_enabled=False,
                version=1,
            )
        )
        db.commit()
    anomaly = client.get(
        "/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry"
    )
    assert anomaly.status_code == 200
    assert anomaly.json()["requester_cardinality"] == "anomaly"
    assert anomaly.json()["disabled_reason"] == "requester_cardinality_anomaly"


def test_inactive_and_cross_world_profile_routes_do_not_leak_identity() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    with Session(engine) as db:
        responding = db.get(models.WorldCharacter, "wc-responding")
        assert responding is not None
        responding.status = "left"
        db.commit()

    assert (
        client.get("/api/v1/worlds/world-a/world-characters/wc-responding").status_code
        == 404
    )
    assert (
        client.get("/api/v1/worlds/world-b/world-characters/wc-responding").status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry"
        ).status_code
        == 404
    )
    feed = client.get("/api/v1/worlds/world-a/manual-social/feed")
    assert feed.status_code == 200
    assert feed.json()["items"][0]["author_profile_capability"] == "unavailable"
