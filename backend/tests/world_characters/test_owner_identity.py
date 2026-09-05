from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.core.db import Base, get_db
from app.cruds import agent_runs as agent_run_crud
from app.domains.world_characters.router.profile import router
from app.services import agent_runs as agent_run_service
from app.runtime.characters import management as agent_service


FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260818_0081_owner_controlled_world_character.py"
)


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
    app.include_router(router, prefix="/api/v1")

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
        name="마법학교",
        tagline="fixture",
        setting_description="fixture",
        daily_life_description="fixture",
        genre_tags=["fantasy"],
        tone_tags=["warm"],
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
        name="학생",
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


def _payload(**overrides):
    payload = {
        "display_name": "구름",
        "avatar_url": "https://example.test/avatar.png",
        "intro": "마법학교를 산책하는 앵무",
        "role_key": "student",
        "preferred_address": "구름이",
        "interests": ["산책", "마법약"],
        "background": "새로 전학 온 학생",
    }
    payload.update(overrides)
    return payload


def test_owner_identity_create_update_reentry_is_private_and_write_bounded() -> None:
    client, engine, principal = _fixture()
    _seed_world(engine, principal)

    created = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(),
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["control_mode"] == "owner_controlled"
    assert payload["autonomous_enabled"] is False
    assert payload["profile"]["display_name"] == "구름"
    assert "owner_user_id" not in created.text
    assert "owner-a@example.test" not in created.text

    duplicate = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(display_name="두 번째"),
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "owner_controlled_identity_exists"}

    updated = client.patch(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(display_name="구름 새 이름", interests=["친구"]),
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["profile"]["interests"] == ["친구"]

    reentered = client.get("/api/v1/worlds/world-a/owner-character")
    assert reentered.status_code == 200
    assert reentered.json() == updated.json()

    with Session(engine) as db:
        world_character = db.get(
            models.WorldCharacter, payload["world_character_id"]
        )
        character = db.get(models.Character, payload["character_id"])
        assert world_character is not None
        assert world_character.owner_user_id == "owner-a"
        assert world_character.control_mode == "owner_controlled"
        assert world_character.autonomous_enabled is False
        assert character is not None and character.execution_mode == "local"
        assert db.query(models.Post).count() == 0
        assert db.query(models.Comment).count() == 0
        assert db.query(models.AgentRun).count() == 0


def test_owner_identity_rejects_cross_owner_and_cross_world_role() -> None:
    client, engine, principal = _fixture()
    owner, outsider = _seed_world(engine, principal)
    principal["user"] = outsider

    forbidden = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(),
    )
    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "local_owner_required"}

    principal["user"] = owner
    invalid_role = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(role_key="other-world-role"),
    )
    assert invalid_role.status_code == 422
    assert invalid_role.json() == {"detail": "owner_controlled_role_invalid"}


def test_creator_studio_lists_existing_world_characters_without_writes() -> None:
    client, engine, principal = _fixture()
    owner, outsider = _seed_world(engine, principal)
    owner_identity = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(display_name="모모"),
    ).json()
    now = datetime.now(UTC)
    autonomous = models.Character(
        id="autonomous-studio",
        owner_id=owner.id,
        name="망고",
        handle="autonomous-studio",
        avatar_url="https://example.test/mango.png",
        one_liner="마법학교의 자율 앵무",
        personality="",
        speech_style="",
        worldview="",
        topic_preferences="",
        safety_rules="",
        status="active",
        execution_mode="llm",
        persona_summary="fixture",
    )
    with Session(engine) as db:
        db.add(autonomous)
        db.flush()
        db.add(
            models.WorldCharacter(
                id="wc-autonomous-studio",
                world_id="world-a",
                character_id=autonomous.id,
                membership_id="membership-owner-a",
                role_key="student",
                status="active",
                control_mode="autonomous",
                owner_user_id=None,
                autonomous_enabled=False,
                version=3,
            )
        )
        db.add(
            models.WorldCommunityProfile(
                id="profile-studio",
                world_character_id="wc-autonomous-studio",
                status="ready",
                visible_summary="fixture",
                core_interests=["books"],
                adjacent_interests=[],
                avoid_topics=[],
                discovery_openness=50,
                search_keywords=["books"],
                action_profile={},
                schema_version=1,
                generator_version="fixture",
                character_contract_hash="c" * 64,
                world_contract_hash="w" * 64,
                provider="fake",
                model="fixture",
                credential_id="credential-fixture",
                generated_at=now,
                approved_at=now,
            )
        )
        db.flush()
        db.add(
            models.WorldActivityRepertoire(
                id="repertoire-studio",
                world_character_id="wc-autonomous-studio",
                status="ready",
                schema_version=1,
                generator_version="fixture",
                character_contract_hash="c" * 64,
                world_contract_hash="w" * 64,
                community_profile_id="profile-studio",
                provider="fake",
                model="fixture",
                credential_id="credential-fixture",
                validation_summary={"count": 40},
                generated_at=now,
                approved_at=now,
            )
        )
        db.commit()

    before = None
    with Session(engine) as db:
        before = (
            db.query(models.Post).count(),
            db.query(models.Comment).count(),
            db.query(models.AgentRun).count(),
        )

    response = client.get(
        "/api/v1/worlds/world-a/characters?surface=studio",
        headers=FRONTEND_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "studio-world-character-list-v1"
    assert payload["world_id"] == "world-a"
    by_mode = {item["control_mode"]: item for item in payload["items"]}
    assert by_mode["autonomous"] == {
        "world_character_id": "wc-autonomous-studio",
        "character_id": "autonomous-studio",
        "display_name": "망고",
        "confirmation_name": "망고",
        "avatar_url": "https://example.test/mango.png",
        "intro": "마법학교의 자율 앵무",
        "role_key": "student",
        "control_mode": "autonomous",
        "status": "active",
        "autonomous_enabled": False,
        "selected_active_world": False,
        "version": 3,
        "activity_setup_state": "approved",
    }
    assert by_mode["owner_controlled"]["character_id"] == owner_identity["character_id"]
    assert by_mode["owner_controlled"]["activity_setup_state"] == (
        "unavailable_for_owner_controlled"
    )

    with Session(engine) as db:
        assert before == (
            db.query(models.Post).count(),
            db.query(models.Comment).count(),
            db.query(models.AgentRun).count(),
        )

    principal["user"] = outsider
    forbidden = client.get(
        "/api/v1/worlds/world-a/characters?surface=studio",
        headers=FRONTEND_HEADERS,
    )
    assert forbidden.status_code == 403


def test_scheduler_claim_excludes_owner_controlled_but_keeps_autonomous() -> None:
    client, engine, principal = _fixture()
    owner, _ = _seed_world(engine, principal)
    created = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(),
    ).json()
    now = datetime.now(UTC)

    autonomous = models.Character(
        id="autonomous-a",
        owner_id=owner.id,
        name="자동 앵무",
        handle="autonomous-a",
        one_liner="",
        personality="",
        speech_style="",
        worldview="",
        topic_preferences="",
        safety_rules="",
        status="active",
        execution_mode="llm",
        persona_summary="fixture",
    )
    with Session(engine) as db:
        db.add(autonomous)
        db.flush()
        db.add(
            models.WorldCharacter(
                id="wc-autonomous-a",
                world_id="world-a",
                character_id=autonomous.id,
                membership_id="membership-owner-a",
                status="active",
                control_mode="autonomous",
                owner_user_id=None,
                autonomous_enabled=True,
            )
        )
        owner_credential = models.LlmCredential(
            id="credential-owner",
            owner_id=owner.id,
            character_id=created["character_id"],
            provider="gemini",
            purpose="agent",
            model="fixture",
            auth_profile_id="owner-profile",
            label="fixture",
            encrypted_api_key="fixture",
        )
        autonomous_credential = models.LlmCredential(
            id="credential-autonomous",
            owner_id=owner.id,
            character_id=autonomous.id,
            provider="gemini",
            purpose="agent",
            model="fixture",
            auth_profile_id="autonomous-profile",
            label="fixture",
            encrypted_api_key="fixture",
        )
        db.add_all([owner_credential, autonomous_credential])
        db.flush()
        db.add_all(
            [
                models.AgentSlot(
                    agent_id="slot-owner",
                    status=agent_run_crud.SLOT_STATUS_ASSIGNED_IDLE,
                    assigned_user_id=owner.id,
                    assigned_character_id=created["character_id"],
                    assigned_credential_id=owner_credential.id,
                    next_tick_at=now - timedelta(minutes=1),
                ),
                models.AgentSlot(
                    agent_id="slot-autonomous",
                    status=agent_run_crud.SLOT_STATUS_ASSIGNED_IDLE,
                    assigned_user_id=owner.id,
                    assigned_character_id=autonomous.id,
                    assigned_credential_id=autonomous_credential.id,
                    next_tick_at=now - timedelta(minutes=1),
                ),
            ]
        )
        db.commit()

        claimed = agent_run_crud.claim_due_resident_slots(
            db,
            now=now,
            max_count=5,
            lease_seconds=120,
        )
        assert [slot.agent_id for slot in claimed] == ["slot-autonomous"]
        assert db.get(models.AgentSlot, "slot-owner").status == (
            agent_run_crud.SLOT_STATUS_ASSIGNED_IDLE
        )


def test_owner_controlled_execution_preflight_blocks_run_now_and_provider(
    monkeypatch,
) -> None:
    client, engine, principal = _fixture()
    _seed_world(engine, principal)
    created = client.post(
        "/api/v1/worlds/world-a/owner-character",
        headers=FRONTEND_HEADERS,
        json=_payload(),
    ).json()

    def provider_must_not_start(**_kwargs):
        raise AssertionError("owner-controlled preflight must run before provider")

    monkeypatch.setattr(
        agent_run_service,
        "OpenClawGatewayClient",
        provider_must_not_start,
    )

    with Session(engine) as db:
        owner = db.get(models.User, "owner-a")
        character = db.get(models.Character, created["character_id"])
        assert owner is not None and character is not None
        with pytest.raises(
            agent_service.AgentExecutionModeError,
            match="owner_controlled_manual_write_not_available",
        ):
            asyncio.run(agent_service.run_agent_now(db, owner, character.id))

        credential = models.LlmCredential(
            id="credential-owner-preflight",
            owner_id=owner.id,
            character_id=character.id,
            provider="gemini",
            purpose="agent",
            model="fixture",
            auth_profile_id="owner-preflight-profile",
            label="fixture",
            encrypted_api_key="fixture",
        )
        db.add(credential)
        db.flush()
        slot = models.AgentSlot(
            agent_id="slot-owner-preflight",
            status=agent_run_crud.SLOT_STATUS_RUNNING,
            assigned_user_id=owner.id,
            assigned_character_id=character.id,
            assigned_credential_id=credential.id,
            locked_by_run_id="pending:slot-owner-preflight:test",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            next_tick_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        db.add(slot)
        db.commit()

        result = asyncio.run(
            agent_run_service._run_resident_slot_once(
                db,
                slot=slot,
                post_id=None,
                timeout_seconds=30,
                message="owner controlled forged execution fixture",
            )
        )
        assert result.status == "no_action"
        assert result.gateway_result == {
            "status": "no_action",
            "reason_code": "owner_controlled_automation_disabled",
            "provider_call_count": 0,
            "public_write_count": 0,
        }
        db.expire_all()
        released = db.get(models.AgentSlot, slot.agent_id)
        assert released is not None
        assert released.status == agent_run_crud.SLOT_STATUS_ASSIGNED_IDLE
        assert released.locked_by_run_id is None
        assert released.last_error == "owner_controlled_automation_disabled"
        assert db.query(models.AgentRun).count() == 0
        assert db.query(models.Post).count() == 0
        assert db.query(models.Comment).count() == 0


def test_owner_controlled_migration_refuses_provenance_losing_downgrade(
    monkeypatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "owner_controlled_world_character_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = migration
    spec.loader.exec_module(migration)

    class Bind:
        @staticmethod
        def scalar(_statement) -> int:
            return 1

    monkeypatch.setattr(migration.op, "get_bind", lambda: Bind())
    with pytest.raises(
        RuntimeError,
        match="downgrade_refused_owner_controlled_world_characters_exist",
    ):
        migration.downgrade()
