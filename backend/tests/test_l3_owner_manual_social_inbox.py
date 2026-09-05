from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.core.db import Base, get_db
from app.domains.social.schemas.manual import ManualSocialPostRead
from app.api.v1.routes.manual_social import router as manual_social_router
from app.domains.world_characters.router.profile import router as owner_identity_router
from app.runtime.social.sqlalchemy_read_repository import list_owner_world_feed
from app.services import world_character_contracts

FRONTEND_HEADERS = {"Origin": "http://127.0.0.1:3000"}
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/20260819_0082_owner_manual_social_inbox.py"
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


def _world_post(
    *,
    post_id: str,
    author_character_id: str,
    author_world_character_id: str,
    world_id: str,
    reply_to_post_id: str | None,
    created_at: datetime,
    visibility: str = "public",
    deleted_at: datetime | None = None,
    report_hidden_at: datetime | None = None,
) -> models.Post:
    return models.Post(
        id=post_id,
        author_user_id="owner-manual",
        author_character_id=author_character_id,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
        reply_to_post_id=reply_to_post_id,
        post_type="reply" if reply_to_post_id is not None else "post",
        visibility=visibility,
        author_name="Sage",
        title="" if reply_to_post_id is not None else post_id,
        body=post_id,
        search_document=post_id,
        created_at=created_at,
        updated_at=created_at,
        deleted_at=deleted_at,
        report_hidden_at=report_hidden_at,
    )


def _seed_count_projection_rows(engine) -> None:
    now = datetime.now(UTC)
    with Session(engine) as db:
        root = db.get(models.Post, "post-autonomous-target")
        autonomous = db.get(
            models.WorldCharacter, "world-character-autonomous-target"
        )
        character = db.get(models.Character, "character-autonomous-target")
        assert root is not None and autonomous is not None and character is not None
        root.created_at = now + timedelta(minutes=10)
        root.updated_at = root.created_at

        other_world = models.World(
            id="world-count-other",
            slug="world-count-other",
            owner_user_id="owner-manual",
            name="Other Count World",
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
            contract_hash="b" * 64,
            readiness_status="publish_ready",
            additional_generation_guidance="",
            create_idempotency_key="world-count-other-create",
        )
        other_membership = models.WorldMembership(
            id="membership-count-other",
            world_id=other_world.id,
            user_id="owner-manual",
            role="owner",
            status="active",
            joined_at=now,
        )
        other_role = models.WorldRole(
            id="role-count-other",
            world_id=other_world.id,
            role_key="student",
            name="학생",
            description="",
            responsibilities=[],
            allowed_activity_scope=[],
            autonomous_allowed=True,
            status="enabled",
        )
        db.add(other_world)
        db.flush()
        db.add_all([other_membership, other_role])
        db.flush()
        other_actor = models.WorldCharacter(
            id="world-character-count-other",
            world_id=other_world.id,
            character_id=character.id,
            membership_id=other_membership.id,
            role_key=other_role.role_key,
            status="active",
            control_mode="autonomous",
            owner_user_id=None,
            autonomous_enabled=True,
            activity_runtime_mode="routine_resident_v1",
            feed_runtime_mode="keyword_search_v1",
            local_profile={"background": "fixture"},
            character_contract_hash=autonomous.character_contract_hash,
            world_contract_hash=other_world.contract_hash,
        )
        db.add(other_actor)
        db.flush()

        visible = _world_post(
            post_id="reply-count-visible",
            author_character_id=character.id,
            author_world_character_id=autonomous.id,
            world_id="world-manual",
            reply_to_post_id=root.id,
            created_at=now,
        )
        db.add(visible)
        db.flush()
        db.add_all(
            [
                _world_post(
                    post_id="reply-count-nested",
                    author_character_id=character.id,
                    author_world_character_id=autonomous.id,
                    world_id="world-manual",
                    reply_to_post_id=visible.id,
                    created_at=now - timedelta(minutes=1),
                ),
                _world_post(
                    post_id="reply-count-deleted",
                    author_character_id=character.id,
                    author_world_character_id=autonomous.id,
                    world_id="world-manual",
                    reply_to_post_id=root.id,
                    created_at=now - timedelta(minutes=2),
                    deleted_at=now,
                ),
                _world_post(
                    post_id="reply-count-report-hidden",
                    author_character_id=character.id,
                    author_world_character_id=autonomous.id,
                    world_id="world-manual",
                    reply_to_post_id=root.id,
                    created_at=now - timedelta(minutes=3),
                    report_hidden_at=now,
                ),
                _world_post(
                    post_id="reply-count-private",
                    author_character_id=character.id,
                    author_world_character_id=autonomous.id,
                    world_id="world-manual",
                    reply_to_post_id=root.id,
                    created_at=now - timedelta(minutes=4),
                    visibility="private",
                ),
                _world_post(
                    post_id="reply-count-cross-world",
                    author_character_id=character.id,
                    author_world_character_id=other_actor.id,
                    world_id=other_world.id,
                    reply_to_post_id=root.id,
                    created_at=now - timedelta(minutes=5),
                ),
                models.PostLike(
                    post_id=root.id,
                    user_id="owner-manual",
                    character_id=None,
                ),
                models.PostLike(
                    post_id=visible.id,
                    user_id="owner-manual",
                    character_id=character.id,
                ),
            ]
        )
        db.commit()


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
    items_by_id = {item["id"]: item for item in feed.json()["items"]}
    assert items_by_id["post-autonomous-target"]["reply_count"] == 1
    assert items_by_id["post-autonomous-target"]["like_count"] == 0
    assert items_by_id[created_payload["post"]["id"]]["reply_count"] == 0
    assert items_by_id[created_payload["post"]["id"]]["like_count"] == 0
    assert items_by_id[reply_payload["post"]["id"]]["reply_count"] == 0
    assert items_by_id[reply_payload["post"]["id"]]["like_count"] == 0

    with Session(engine) as db:
        assert db.scalar(select(func.count(models.Post.id))) == 3
        assert db.scalar(select(func.count(models.OwnerManualSocialWrite.id))) == 2
        assert db.scalar(select(func.count(models.OwnerManualInboxCandidate.id))) == 1
        candidate = db.scalar(select(models.OwnerManualInboxCandidate))
        assert candidate is not None and candidate.status == "pending"
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 2
        assert db.scalar(select(func.count(models.SocialEventEvidence.id))) == 2
        source_events = list(
            db.scalars(
                select(models.SocialEvent).order_by(models.SocialEvent.created_at)
            )
        )
        assert [event.event_type for event in source_events] == [
            "post_published",
            "reply_created",
        ]
        assert all(event.retrieval_status == "audit_only" for event in source_events)
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


def test_owner_world_post_thread_is_exactly_world_scoped() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)
    identity = client.post(
        "/api/v1/worlds/world-manual/owner-character",
        headers=FRONTEND_HEADERS,
        json=_owner_payload(),
    )
    assert identity.status_code == 201
    reply = client.post(
        "/api/v1/worlds/world-manual/manual-social/posts/post-autonomous-target/replies",
        headers={**FRONTEND_HEADERS, "Idempotency-Key": "manual-thread-reply-1"},
        json={"body": "이 답글도 같은 World 상세에만 표시됩니다."},
    )
    assert reply.status_code == 201

    thread = client.get(
        "/api/v1/worlds/world-manual/manual-social/posts/post-autonomous-target",
        headers=FRONTEND_HEADERS,
    )
    assert thread.status_code == 200
    payload = thread.json()
    assert payload["world_id"] == "world-manual"
    assert [item["id"] for item in payload["items"]] == [
        "post-autonomous-target",
        reply.json()["post"]["id"],
    ]
    assert all(item["world_id"] == "world-manual" for item in payload["items"])

    wrong_world = client.get(
        "/api/v1/worlds/not-this-world/manual-social/posts/post-autonomous-target",
        headers=FRONTEND_HEADERS,
    )
    assert wrong_world.status_code in {403, 404}

    reply_as_root = client.get(
        f"/api/v1/worlds/world-manual/manual-social/posts/{reply.json()['post']['id']}",
        headers=FRONTEND_HEADERS,
    )
    assert reply_as_root.status_code == 404
    assert reply_as_root.json() == {"detail": "post_not_in_world"}


def test_manual_social_count_projection_is_exact_world_visible_and_batched() -> None:
    client, engine, principal = _fixture()
    owner = _seed(engine, principal)
    identity = client.post(
        "/api/v1/worlds/world-manual/owner-character",
        headers=FRONTEND_HEADERS,
        json=_owner_payload(),
    )
    assert identity.status_code == 201
    _seed_count_projection_rows(engine)
    grouped_count_queries: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture_grouped_counts(
        _conn, _cursor, statement, _parameters, _context, _many
    ) -> None:
        normalized = " ".join(statement.lower().split())
        if "count(" in normalized and " group by " in normalized:
            grouped_count_queries.append(normalized)

    with Session(engine) as db:
        feed = list_owner_world_feed(
            db,
            world_id="world-manual",
            current_user_id=owner.id,
            limit=1,
        )

    assert [item.id for item in feed.items] == ["post-autonomous-target"]
    assert feed.items[0].reply_count == 1
    assert feed.items[0].like_count == 1
    reply_queries = [
        statement
        for statement in grouped_count_queries
        if " from posts " in f" {statement} "
    ]
    like_queries = [
        statement
        for statement in grouped_count_queries
        if " from post_likes " in f" {statement} "
    ]
    assert len(reply_queries) == 1
    assert len(like_queries) == 1
    assert "posts.world_id" in reply_queries[0]
    assert "posts.visibility" in reply_queries[0]
    assert "posts.deleted_at is null" in reply_queries[0]
    assert "posts.report_hidden_at is null" in reply_queries[0]

    thread = client.get(
        "/api/v1/worlds/world-manual/manual-social/posts/post-autonomous-target",
        headers=FRONTEND_HEADERS,
    )
    assert thread.status_code == 200
    items_by_id = {item["id"]: item for item in thread.json()["items"]}
    assert set(items_by_id) == {"post-autonomous-target", "reply-count-visible"}
    assert items_by_id["post-autonomous-target"]["reply_count"] == 1
    assert items_by_id["post-autonomous-target"]["like_count"] == 1
    assert items_by_id["reply-count-visible"]["reply_count"] == 1
    assert items_by_id["reply-count-visible"]["like_count"] == 1


def test_manual_social_read_counts_are_required_and_non_negative() -> None:
    payload = {
        "id": "post-contract",
        "world_id": "world-contract",
        "author_world_character_id": "world-character-contract",
        "author_name": "Contract Bird",
        "title": "contract",
        "body": "contract",
        "post_type": "post",
        "reply_to_post_id": None,
        "created_at": datetime.now(UTC),
        "can_owner_reply": False,
    }
    with pytest.raises(ValidationError):
        ManualSocialPostRead.model_validate(payload)
    with pytest.raises(ValidationError):
        ManualSocialPostRead.model_validate(
            {**payload, "reply_count": -1, "like_count": 0}
        )
    with pytest.raises(ValidationError):
        ManualSocialPostRead.model_validate(
            {**payload, "reply_count": 0, "like_count": -1}
        )


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
