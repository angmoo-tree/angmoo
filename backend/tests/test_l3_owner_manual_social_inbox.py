from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import pytest

from app import models
from app.api.v1.deps import get_current_user
from app.core.db import Base, get_db
from app.domains.manual_social.api.routes import router as manual_social_router
from app.domains.world_characters.api.routes import router as owner_identity_router
from app.services import world_character_contracts


FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "app/alembic/versions/20260819_0082_owner_manual_social_inbox.py"
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
    app.include_router(owner_identity_router, prefix="/api/v1")
    app.include_router(manual_social_router, prefix="/api/v1")

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


def _seed(engine, principal):
    owner = _user("owner-manual")
    now = datetime.now(UTC)
    world = models.World(
        id="world-manual",
        slug="world-manual",
        owner_user_id=owner.id,
        name="Manual World",
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
        create_idempotency_key="world-manual-create",
    )
    membership = models.WorldMembership(
        id="membership-manual",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
        joined_at=now,
    )
    role = models.WorldRole(
        id="role-manual",
        world_id=world.id,
        role_key="student",
        name="학생",
        description="",
        responsibilities=[],
        allowed_activity_scope=[],
        autonomous_allowed=True,
        status="enabled",
    )
    autonomous_character = models.Character(
        id="character-autonomous-target",
        owner_id=owner.id,
        name="Sage",
        handle="sage-manual-target",
        one_liner="target",
        personality="warm",
        speech_style="brief",
        worldview="friends matter",
        topic_preferences="school",
        safety_rules="safe",
        persona_summary="target fixture",
        moderation_status="active",
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add(owner)
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="manual-installation",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="fixture",
                claimed_at=now,
            )
        )
        db.add_all([world, autonomous_character])
        db.flush()
        db.add_all([membership, role])
        db.flush()
        autonomous = models.WorldCharacter(
            id="world-character-autonomous-target",
            world_id=world.id,
            character_id=autonomous_character.id,
            membership_id=membership.id,
            role_key="student",
            status="active",
            control_mode="autonomous",
            owner_user_id=None,
            autonomous_enabled=True,
            activity_runtime_mode="routine_resident_v1",
            feed_runtime_mode="keyword_search_v1",
            local_profile={"background": "fixture"},
            character_contract_hash=world_character_contracts.character_contract_hash(
                autonomous_character
            ),
            world_contract_hash=world.contract_hash,
        )
        db.add(autonomous)
        db.flush()
        target_post = models.Post(
            id="post-autonomous-target",
            author_user_id=owner.id,
            author_character_id=autonomous_character.id,
            world_id=world.id,
            author_world_character_id=autonomous.id,
            post_type="post",
            visibility="public",
            author_name=autonomous_character.name,
            title="오늘의 연금술 수업",
            body="온도를 조금 낮춰 보았어요.",
            search_document="연금술 온도",
            created_at=now,
            updated_at=now,
        )
        db.add(target_post)
        db.commit()
    principal["user"] = owner
    return owner


def _owner_payload() -> dict[str, object]:
    return {
        "display_name": "Owner Bird",
        "avatar_url": "https://example.test/owner.png",
        "intro": "사용자가 직접 조종하는 앵무",
        "role_key": "student",
        "preferred_address": "Owner Bird",
        "interests": ["연금술"],
        "background": "fixture",
    }


def test_owner_manual_post_and_reply_are_idempotent_and_provider_free() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    identity = client.post(
        "/api/v1/worlds/world-manual/owner-character",
        headers=FRONTEND_HEADERS,
        json=_owner_payload(),
    )
    assert identity.status_code == 201
    actor_id = identity.json()["world_character_id"]

    root_headers = {**FRONTEND_HEADERS, "Idempotency-Key": "manual-root-request-1"}
    created = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts",
        headers=root_headers,
        json={"title": "직접 남긴 글", "body": "이 World에만 저장됩니다."},
    )
    assert created.status_code == 201
    created_payload = created.json()
    assert created_payload["post"]["author_world_character_id"] == actor_id
    assert created_payload["delivery"] == {
        "provider_call_count": 0,
        "inbox_candidate_id": None,
        "inbox_status": "not_applicable",
        "public_reaction_required": False,
    }

    replay = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts",
        headers=root_headers,
        json={"title": "직접 남긴 글", "body": "이 World에만 저장됩니다."},
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    assert replay.json()["post"]["id"] == created_payload["post"]["id"]

    reply_headers = {**FRONTEND_HEADERS, "Idempotency-Key": "manual-reply-request-1"}
    reply = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts/post-autonomous-target/replies",
        headers=reply_headers,
        json={"body": "다음 실험에서는 불꽃 색도 함께 볼게요."},
    )
    assert reply.status_code == 201
    reply_payload = reply.json()
    assert reply_payload["post"]["author_world_character_id"] == actor_id
    assert reply_payload["post"]["reply_to_post_id"] == "post-autonomous-target"
    assert reply_payload["delivery"]["provider_call_count"] == 0
    assert reply_payload["delivery"]["inbox_status"] == "pending"
    assert reply_payload["delivery"]["public_reaction_required"] is False
    assert reply_payload["delivery"]["inbox_candidate_id"]

    replay_reply = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts/post-autonomous-target/replies",
        headers=reply_headers,
        json={"body": "다음 실험에서는 불꽃 색도 함께 볼게요."},
    )
    assert replay_reply.status_code == 201
    assert replay_reply.json()["replayed"] is True
    assert replay_reply.json()["post"]["id"] == reply_payload["post"]["id"]
    assert (
        replay_reply.json()["delivery"]["inbox_candidate_id"]
        == reply_payload["delivery"]["inbox_candidate_id"]
    )

    feed = client.get(
        "/api/v1/worlds/world-manual/manual-social/feed",
        headers=FRONTEND_HEADERS,
    )
    assert feed.status_code == 200
    assert feed.json()["world_id"] == "world-manual"
    assert len(feed.json()["items"]) == 3

    with Session(engine) as db:
        assert db.scalar(select(func.count(models.Post.id))) == 3
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 2
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 1
        candidate = db.scalar(select(models.OwnerManualInboxCandidate))
        assert candidate is not None and candidate.status == "pending"
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0


def test_owner_manual_reply_fails_closed_for_owner_and_hidden_targets() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    identity = client.post(
        "/api/v1/worlds/world-manual/owner-character",
        headers=FRONTEND_HEADERS,
        json=_owner_payload(),
    )
    actor_id = identity.json()["world_character_id"]
    created = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "manual-owner-root-1"},
        json={"title": "owner root", "body": "self target"},
    )
    owner_post_id = created.json()["post"]["id"]

    owner_target = client.post(
        f"/api/v1/worlds/world-manual/manual-social/posts/{owner_post_id}/replies",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "manual-owner-reply-1"},
        json={"body": "self reply"},
    )
    assert owner_target.status_code == 403
    assert owner_target.json() == {"detail": "reply_target_not_autonomous"}

    with Session(engine) as db:
        target = db.get(models.Post, "post-autonomous-target")
        assert target is not None
        target.report_hidden_at = datetime.now(UTC)
        db.commit()

    hidden = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts/post-autonomous-target/replies",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "manual-hidden-reply-1"},
        json={"body": "hidden reply"},
    )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "reply_target_unavailable"}

    with Session(engine) as db:
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 0
        assert db.scalar(select(func.count(models.Post.id))) == 2
        actor = db.get(models.WorldCharacter, actor_id)
        assert actor is not None and actor.autonomous_enabled is False


def test_owner_manual_social_migration_refuses_history_losing_downgrade(
    monkeypatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "owner_manual_social_inbox_migration",
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
        match="cannot downgrade 0082 while owner_manual_inbox_candidates contains L3 rows",
    ):
        migration.downgrade()
