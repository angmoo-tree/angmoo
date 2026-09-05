from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.api.v1.routes.worlds import router as worlds_router
from app.domains.worlds.router import router as world_creator_router
from app.core.db import Base, get_db
from app.domains.world_characters.router.profile import router as studio_router


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


def _fixture():
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
    app.include_router(studio_router, prefix="/api/v1")
    app.include_router(worlds_router, prefix="/api/v1")
    app.include_router(world_creator_router, prefix="/api/v1")

    def db_dependency():
        with Session(engine) as db:
            yield db

    def user_dependency() -> models.User:
        if principal["user"] is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        return principal["user"]

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = user_dependency
    return TestClient(app, base_url="http://127.0.0.1:3000"), engine, principal


def _seed_world(engine, principal):
    owner = _user("owner-a")
    outsider = _user("owner-b")
    now = datetime.now(UTC)
    world = models.World(
        id="world-a",
        slug="world-a",
        owner_user_id=owner.id,
        name="히어로 학교",
        tagline="fixture",
        setting_description="fixture",
        daily_life_description="fixture",
        genre_tags=["hero-school"],
        tone_tags=["adventure"],
        banner_alt_text="",
        timezone="Asia/Seoul",
        language="ko",
        visibility="public",
        join_policy="open",
        status="published",
        definition_version=1,
        row_version=1,
        contract_version="world-v1",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        additional_generation_guidance="",
        create_idempotency_key="world-a-create",
    )
    membership = models.WorldMembership(
        id="membership-owner-a",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=now,
    )
    role = models.WorldRole(
        id="role-student",
        world_id=world.id,
        role_key="student",
        name="학생 히어로",
        description="",
        responsibilities=[],
        allowed_activity_scope=[],
        autonomous_allowed=True,
        status="enabled",
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, outsider])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="fixture-installation",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="fixture",
                claimed_at=now,
            )
        )
        db.add(world)
        db.flush()
        db.add_all([membership, role])
        db.commit()
    principal["user"] = owner
    return owner, outsider


def _character(
    character_id: str,
    owner_id: str,
    *,
    name: str,
    execution_mode: str = "llm",
    moderation_status: str = "active",
) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=name,
        handle=character_id,
        one_liner="히어로 학교 학생",
        personality="용감함",
        speech_style="또렷함",
        worldview="서로 돕는다",
        topic_preferences="훈련",
        safety_rules="안전 우선",
        status="inactive",
        moderation_status=moderation_status,
        execution_mode=execution_mode,
        persona_summary="fixture",
    )


def _world_character(
    world_character_id: str,
    character_id: str,
    *,
    status: str = "pending",
    control_mode: str = "autonomous",
    autonomous_enabled: bool = False,
    owner_user_id: str | None = None,
    version: int = 1,
) -> models.WorldCharacter:
    return models.WorldCharacter(
        id=world_character_id,
        world_id="world-a",
        character_id=character_id,
        membership_id="membership-owner-a",
        role_key="student",
        status=status,
        control_mode=control_mode,
        owner_user_id=owner_user_id,
        autonomous_enabled=autonomous_enabled,
        version=version,
    )


def test_candidate_read_is_owner_scoped_and_returns_typed_reasons() -> None:
    client, engine, principal = _fixture()
    owner, outsider = _seed_world(engine, principal)
    with Session(engine) as db:
        eligible = _character("eligible", owner.id, name="번개새")
        local = _character(
            "local", owner.id, name="외부 조종새", execution_mode="local"
        )
        linked = _character("linked", owner.id, name="연결된 새")
        left = _character("left", owner.id, name="떠난 새")
        suspended = _character(
            "suspended", owner.id, name="검토 중인 새", moderation_status="suspended"
        )
        hidden = _character("hidden", outsider.id, name="다른 사람 새")
        db.add_all([eligible, local, linked, left, suspended, hidden])
        db.flush()
        db.add_all(
            [
                _world_character("wc-linked", linked.id, status="active"),
                _world_character("wc-left", left.id, status="left"),
            ]
        )
        db.commit()

    response = client.get(
        "/api/v1/worlds/world-a/character-candidates",
        headers=FRONTEND_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "studio-character-candidates-v1"
    by_id = {item["character_id"]: item for item in payload["items"]}
    assert "hidden" not in by_id
    assert by_id["eligible"]["eligible"] is True
    assert by_id["eligible"]["reason_code"] is None
    assert by_id["local"]["reason_code"] == "local_execution_mode_unsupported"
    assert by_id["linked"]["reason_code"] == "already_linked"
    assert by_id["linked"]["current_world_status"] == "active"
    assert by_id["left"]["reason_code"] == (
        "world_character_left_restore_unsupported"
    )
    assert by_id["suspended"]["reason_code"] == (
        "character_moderation_inactive"
    )


def test_leave_is_world_local_idempotent_and_preserves_setup_history() -> None:
    client, engine, principal = _fixture()
    owner, _ = _seed_world(engine, principal)
    character = _character("hero-a", owner.id, name="빛나")
    character.status = "inactive"
    world_character = _world_character(
        "wc-hero-a",
        character.id,
        status="active",
        version=4,
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add(character)
        db.flush()
        db.add(world_character)
        db.flush()
        db.add(
            models.CharacterActiveWorld(
                character_id=character.id,
                world_character_id=world_character.id,
                selected_at=datetime.now(UTC),
                idempotency_key="approval-fixture",
                version=1,
            )
        )
        db.add(
            models.AgentActivitySetting(
                character_id=character.id,
                auto_enabled=False,
            )
        )
        db.add(
            models.WorldCommunityProfile(
                id="profile-history",
                world_character_id=world_character.id,
                status="ready",
                visible_summary="보존할 프로필",
                core_interests=["훈련", "우정", "정의"],
                adjacent_interests=["학교", "도시"],
                avoid_topics=[],
                discovery_openness=50,
                search_keywords=["훈련"] * 8,
                action_profile={},
                schema_version=1,
                generator_version="fixture",
                character_contract_hash="c" * 64,
                world_contract_hash="w" * 64,
                provider="fake",
                model="fixture",
                credential_id="credential-history",
                generated_at=datetime.now(UTC),
                approved_at=datetime.now(UTC),
            )
        )
        db.commit()

    studio = client.get(
        "/api/v1/worlds/world-a/characters?surface=studio",
        headers=FRONTEND_HEADERS,
    )
    assert studio.status_code == 200
    assert studio.json()["items"][0]["selected_active_world"] is True

    request = {
        "world_character_id": world_character.id,
        "version": 4,
        "confirmation_name": "빛나",
        "idempotency_key": "leave-fixture-hero-a",
    }
    rejected_origin = client.post(
        "/api/v1/worlds/world-a/characters/hero-a/leave",
        json=request,
    )
    assert rejected_origin.status_code == 403

    left = client.post(
        "/api/v1/worlds/world-a/characters/hero-a/leave",
        headers=FRONTEND_HEADERS,
        json=request,
    )
    assert left.status_code == 200
    assert left.json() == {
        "world_character_id": "wc-hero-a",
        "world_id": "world-a",
        "character_id": "hero-a",
        "status": "left",
        "autonomous_enabled": False,
        "version": 5,
        "scheduler_assignment_released": True,
        "history_preserved": True,
        "replayed": False,
    }

    replay = client.post(
        "/api/v1/worlds/world-a/characters/hero-a/leave",
        headers=FRONTEND_HEADERS,
        json=request,
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["version"] == 5

    with Session(engine) as db:
        stored = db.get(models.WorldCharacter, world_character.id)
        assert stored is not None
        assert stored.status == "left"
        assert stored.autonomous_enabled is False
        assert stored.version == 5
        assert db.get(models.CharacterActiveWorld, character.id) is None
        assert db.get(models.Character, character.id) is not None
        assert db.get(models.WorldCommunityProfile, "profile-history") is not None

    studio = client.get(
        "/api/v1/worlds/world-a/characters?surface=studio",
        headers=FRONTEND_HEADERS,
    )
    assert studio.status_code == 200
    assert studio.json()["items"] == []
    candidates = client.get(
        "/api/v1/worlds/world-a/character-candidates",
        headers=FRONTEND_HEADERS,
    ).json()["items"]
    assert candidates[0]["reason_code"] == (
        "world_character_left_restore_unsupported"
    )
    reentry = client.post(
        "/api/v1/worlds/world-a/characters",
        json={
            "character_id": "hero-a",
            "role_key": "student",
            "idempotency_key": "reenter-fixture-hero-a",
        },
    )
    assert reentry.status_code == 422
    assert reentry.json() == {
        "detail": "world_character_left_restore_unsupported"
    }


def test_leave_rejects_stale_busy_autonomy_and_owner_controlled_targets() -> None:
    client, engine, principal = _fixture()
    owner, _ = _seed_world(engine, principal)
    stale_character = _character("stale", owner.id, name="시간새")
    busy_character = _character("busy", owner.id, name="바쁜새")
    slot_character = _character("slot", owner.id, name="슬롯새")
    auto_character = _character("auto", owner.id, name="활동새")
    owner_character = _character(
        "owner-character", owner.id, name="내 캐릭터", execution_mode="local"
    )
    with Session(engine) as db:
        db.add_all(
            [
                stale_character,
                busy_character,
                slot_character,
                auto_character,
                owner_character,
            ]
        )
        db.flush()
        stale_wc = _world_character("wc-stale", stale_character.id, version=2)
        busy_wc = _world_character("wc-busy", busy_character.id, status="active")
        slot_wc = _world_character("wc-slot", slot_character.id, status="active")
        auto_wc = _world_character(
            "wc-auto",
            auto_character.id,
            status="active",
            autonomous_enabled=True,
        )
        owner_wc = _world_character(
            "wc-owner",
            owner_character.id,
            status="active",
            control_mode="owner_controlled",
            owner_user_id=owner.id,
        )
        db.add_all([stale_wc, busy_wc, slot_wc, auto_wc, owner_wc])
        db.flush()
        db.add(
            models.CharacterActiveWorld(
                character_id=busy_character.id,
                world_character_id=busy_wc.id,
                selected_at=datetime.now(UTC),
                idempotency_key="approval-busy",
                version=1,
            )
        )
        db.add(
            models.AgentRun(
                id="run-busy",
                user_id=owner.id,
                character_id=busy_character.id,
                agent_id="slot-busy",
                session_key="session-busy",
                status="running",
            )
        )
        db.add(
            models.CharacterActiveWorld(
                character_id=slot_character.id,
                world_character_id=slot_wc.id,
                selected_at=datetime.now(UTC),
                idempotency_key="approval-slot",
                version=1,
            )
        )
        db.add(
            models.AgentSlot(
                agent_id="slot-assigned",
                status="idle",
                assigned_user_id=owner.id,
                assigned_character_id=slot_character.id,
            )
        )
        db.commit()

    def leave(character_id: str, world_character_id: str, version: int, name: str):
        return client.post(
            f"/api/v1/worlds/world-a/characters/{character_id}/leave",
            headers=FRONTEND_HEADERS,
            json={
                "world_character_id": world_character_id,
                "version": version,
                "confirmation_name": name,
                "idempotency_key": f"leave-{character_id}-fixture",
            },
        )

    stale = leave("stale", "wc-stale", 1, "시간새")
    assert stale.status_code == 409
    assert stale.json() == {"detail": "stale_world_character_version"}

    busy = leave("busy", "wc-busy", 1, "바쁜새")
    assert busy.status_code == 409
    assert busy.json() == {"detail": "world_character_run_in_progress"}

    assigned = leave("slot", "wc-slot", 1, "슬롯새")
    assert assigned.status_code == 409
    assert assigned.json() == {"detail": "scheduler_assignment_active"}

    autonomy = leave("auto", "wc-auto", 1, "활동새")
    assert autonomy.status_code == 409
    assert autonomy.json() == {"detail": "world_character_autonomy_enabled"}

    protected = leave("owner-character", "wc-owner", 1, "내 캐릭터")
    assert protected.status_code == 422
    assert protected.json() == {
        "detail": "owner_controlled_world_character_protected"
    }
