from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.dependencies import get_current_user
from app.api.v1.routes.manual_social import router as manual_social_router
from app.core.db import Base, get_db
from app.domains.world_characters.api.routes import router as world_character_router


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
    name: str,
    handle: str,
) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=name,
        handle=handle,
        one_liner=f"{name} 소개",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="social",
        safety_rules="safe",
        status="active",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


def _world(world_id: str, owner_id: str) -> models.World:
    return models.World(
        id=world_id,
        slug=world_id,
        owner_user_id=owner_id,
        name=world_id,
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
        contract_hash=world_id[-1] * 64,
        readiness_status="publish_ready",
        create_idempotency_key=world_id,
    )


def _post(
    post_id: str,
    *,
    world_id: str,
    author_character_id: str,
    author_world_character_id: str,
    author_name: str,
    body: str,
    created_at: datetime,
    reply_to_post_id: str | None = None,
    deleted_at: datetime | None = None,
    report_hidden_at: datetime | None = None,
) -> models.Post:
    return models.Post(
        id=post_id,
        author_character_id=author_character_id,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
        reply_to_post_id=reply_to_post_id,
        post_type="reply" if reply_to_post_id else "text",
        visibility="public",
        author_name=author_name,
        title="답글" if reply_to_post_id else f"제목 {post_id}",
        body=body,
        search_document=body,
        created_at=created_at,
        updated_at=created_at,
        deleted_at=deleted_at,
        report_hidden_at=report_hidden_at,
    )


def _like(
    *,
    post: models.Post,
    actor_character_id: str,
    actor_world_character_id: str,
    user_id: str,
    created_at: datetime,
) -> models.PostLike:
    return models.PostLike(
        post_id=post.id,
        user_id=user_id,
        character_id=actor_character_id,
        world_id=post.world_id,
        actor_world_character_id=actor_world_character_id,
        target_world_character_id=post.author_world_character_id,
        created_at=created_at,
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
    return (
        TestClient(app, base_url="http://127.0.0.1:3000"),
        engine,
        principal,
    )


def _seed(engine, principal: dict[str, models.User | None]) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    owner = _user("owner")
    target_owner = _user("target-owner")
    third_owner = _user("third-owner")
    viewer_character = _character(
        "viewer-character",
        owner.id,
        name="사용자 앵무",
        handle="owner_bird",
    )
    target_character = _character(
        "target-character",
        target_owner.id,
        name="친구 앵무",
        handle="friend_bird",
    )
    third_character = _character(
        "third-character",
        third_owner.id,
        name="세 번째 앵무",
        handle="third_bird",
    )
    world_a = _world("world-a", owner.id)
    world_b = _world("world-b", owner.id)

    memberships = [
        models.WorldMembership(
            id=f"membership-{world_id}-{who}",
            world_id=world_id,
            user_id=user_id,
            role="owner" if who == "viewer" else "member",
            status="active",
            joined_at=now,
        )
        for world_id in (world_a.id, world_b.id)
        for who, user_id in (
            ("viewer", owner.id),
            ("target", target_owner.id),
            ("third", third_owner.id),
        )
    ]
    world_characters = [
        models.WorldCharacter(
            id=f"wc-{world_id[-1]}-{who}",
            world_id=world_id,
            character_id=character_id,
            membership_id=f"membership-{world_id}-{who}",
            role_key="student",
            status="active",
            control_mode="owner_controlled" if who == "viewer" else "autonomous",
            owner_user_id=owner.id if who == "viewer" else None,
            autonomous_enabled=who != "viewer",
            local_profile={"avatar_url": f"/media/{world_id}-{who}.png"},
            version=1,
        )
        for world_id in (world_a.id, world_b.id)
        for who, character_id in (
            ("viewer", viewer_character.id),
            ("target", target_character.id),
            ("third", third_character.id),
        )
    ]

    a_root_old = _post(
        "a-root-old",
        world_id="world-a",
        author_character_id=target_character.id,
        author_world_character_id="wc-a-target",
        author_name="친구 앵무",
        body="World A 오래된 지저귐",
        created_at=now - timedelta(minutes=8),
    )
    a_root_new = _post(
        "a-root-new",
        world_id="world-a",
        author_character_id=target_character.id,
        author_world_character_id="wc-a-target",
        author_name="친구 앵무",
        body="World A 최신 지저귐 @owner_bird",
        created_at=now - timedelta(minutes=2),
    )
    a_reply = _post(
        "a-reply",
        world_id="world-a",
        author_character_id=target_character.id,
        author_world_character_id="wc-a-target",
        author_name="친구 앵무",
        body="World A 대꾸",
        reply_to_post_id=a_root_old.id,
        created_at=now - timedelta(minutes=1),
    )
    a_viewer_post = _post(
        "a-viewer-post",
        world_id="world-a",
        author_character_id=viewer_character.id,
        author_world_character_id="wc-a-viewer",
        author_name="사용자 앵무",
        body="World A 좋아요 대상 하나",
        created_at=now - timedelta(minutes=7),
    )
    a_third_post = _post(
        "a-third-post",
        world_id="world-a",
        author_character_id=third_character.id,
        author_world_character_id="wc-a-third",
        author_name="세 번째 앵무",
        body="World A 좋아요 대상 둘",
        created_at=now - timedelta(minutes=6),
    )
    a_hidden = _post(
        "a-hidden",
        world_id="world-a",
        author_character_id=target_character.id,
        author_world_character_id="wc-a-target",
        author_name="친구 앵무",
        body="HIDDEN WORLD A",
        created_at=now - timedelta(minutes=5),
        report_hidden_at=now,
    )
    a_deleted = _post(
        "a-deleted",
        world_id="world-a",
        author_character_id=target_character.id,
        author_world_character_id="wc-a-target",
        author_name="친구 앵무",
        body="DELETED WORLD A",
        created_at=now - timedelta(minutes=4),
        deleted_at=now,
    )
    b_root = _post(
        "b-root",
        world_id="world-b",
        author_character_id=target_character.id,
        author_world_character_id="wc-b-target",
        author_name="친구 앵무",
        body="WORLD B SECRET ACTIVITY",
        created_at=now,
    )
    posts = [
        a_root_old,
        a_root_new,
        a_reply,
        a_viewer_post,
        a_third_post,
        a_hidden,
        a_deleted,
        b_root,
    ]
    likes = [
        _like(
            post=a_viewer_post,
            actor_character_id=target_character.id,
            actor_world_character_id="wc-a-target",
            user_id=target_owner.id,
            created_at=now - timedelta(minutes=4),
        ),
        _like(
            post=a_third_post,
            actor_character_id=target_character.id,
            actor_world_character_id="wc-a-target",
            user_id=target_owner.id,
            created_at=now - timedelta(minutes=3),
        ),
        _like(
            post=a_root_old,
            actor_character_id=viewer_character.id,
            actor_world_character_id="wc-a-viewer",
            user_id=owner.id,
            created_at=now - timedelta(minutes=3),
        ),
        _like(
            post=a_root_old,
            actor_character_id=third_character.id,
            actor_world_character_id="wc-a-third",
            user_id=third_owner.id,
            created_at=now - timedelta(minutes=2),
        ),
        _like(
            post=a_reply,
            actor_character_id=viewer_character.id,
            actor_world_character_id="wc-a-viewer",
            user_id=owner.id,
            created_at=now - timedelta(minutes=1),
        ),
        _like(
            post=b_root,
            actor_character_id=viewer_character.id,
            actor_world_character_id="wc-b-viewer",
            user_id=owner.id,
            created_at=now,
        ),
    ]

    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, target_owner, third_owner])
        db.flush()
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="p8-l-e-social-profile-fixture",
                owner_user_id=owner.id,
                bootstrap_state="claimed",
                local_label="P8-L-E social profile fixture",
                claimed_at=now,
            )
        )
        db.add_all([viewer_character, target_character, third_character])
        db.add_all([world_a, world_b])
        db.flush()
        db.add_all(memberships)
        db.flush()
        db.add_all(world_characters)
        db.flush()
        db.add_all(posts)
        db.flush()
        db.add_all(likes)
        db.add(
            models.PostMedia(
                post_id=a_root_new.id,
                media_type="image",
                url="/media/world-a-profile.png",
                alt_text="World A 이미지",
                model="fixture",
                prompt_hash="a" * 64,
                byte_size=100,
                width=640,
                height=480,
                key_source="user",
                created_at=now,
            )
        )
        db.commit()
    principal["user"] = owner


def _read(
    client: TestClient,
    *,
    tab: str = "posts",
    limit: int = 10,
    cursor: str | None = None,
):
    params: dict[str, str | int] = {"tab": tab, "limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    return client.get(
        "/api/v1/worlds/world-a/world-characters/wc-a-target/social-profile",
        params=params,
    )


def test_world_social_profile_counts_and_tabs_are_exact_world_only() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    posts = _read(client)
    assert posts.status_code == 200
    assert posts.json()["schema_version"] == "world-character-social-profile-v1"
    assert posts.json()["world_id"] == "world-a"
    assert posts.json()["world_character_id"] == "wc-a-target"
    assert posts.json()["character_id"] == "target-character"
    assert posts.json()["counts"] == {
        "post_count": 2,
        "reply_count": 1,
        "liked_post_count": 2,
        "received_like_count": 3,
    }
    assert [item["id"] for item in posts.json()["items"]] == [
        "a-root-new",
        "a-root-old",
    ]
    assert all(item["world_id"] == "world-a" for item in posts.json()["items"])
    assert "WORLD B SECRET" not in posts.text
    assert "HIDDEN WORLD A" not in posts.text
    assert "DELETED WORLD A" not in posts.text
    newest = posts.json()["items"][0]
    assert newest["media"][0]["url"] == "/media/world-a-profile.png"
    assert newest["mentioned_characters"] == [
        {
            "handle": "owner_bird",
            "character_id": "viewer-character",
            "name": "사용자 앵무",
        }
    ]

    replies = _read(client, tab="replies")
    assert replies.status_code == 200
    assert [item["id"] for item in replies.json()["items"]] == ["a-reply"]

    liked = _read(client, tab="likes")
    assert liked.status_code == 200
    assert [item["id"] for item in liked.json()["items"]] == [
        "a-third-post",
        "a-viewer-post",
    ]
    assert "WORLD B SECRET" not in liked.text


def test_world_social_profile_cursor_is_opaque_and_scope_bound() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    first = _read(client, limit=1)
    assert first.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == ["a-root-new"]
    cursor = first.json()["next_cursor"]
    assert isinstance(cursor, str)
    assert "a-root-new" not in cursor
    decoded_cursor = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    assert b"world-a" not in decoded_cursor
    assert b"wc-a-target" not in decoded_cursor
    assert b"a-root-new" not in decoded_cursor

    second = _read(client, limit=1, cursor=cursor)
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == ["a-root-old"]
    assert second.json()["next_cursor"] is None

    assert _read(client, tab="replies", cursor=cursor).status_code == 422
    replacement = "A" if cursor[-1] != "A" else "B"
    assert _read(client, cursor=f"{cursor[:-1]}{replacement}").status_code == 422
    wrong_world = client.get(
        "/api/v1/worlds/world-b/world-characters/wc-b-target/social-profile",
        params={"tab": "posts", "cursor": cursor},
    )
    assert wrong_world.status_code == 422
    assert _read(client, tab="unknown").status_code == 422
    assert _read(client, limit=21).status_code == 422


def test_world_social_profile_inactive_cross_world_and_block_fail_closed() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    cross_world = client.get(
        "/api/v1/worlds/world-a/world-characters/wc-b-target/social-profile"
    )
    assert cross_world.status_code == 404

    with Session(engine) as db:
        db.add(
            models.WorldCharacterBlock(
                id="block-profile",
                world_id="world-a",
                blocker_world_character_id="wc-a-viewer",
                blocked_world_character_id="wc-a-target",
            )
        )
        db.commit()
    assert _read(client).status_code == 403

    with Session(engine) as db:
        db.query(models.WorldCharacterBlock).delete()
        target = db.get(models.WorldCharacter, "wc-a-target")
        assert target is not None
        target.status = "left"
        db.commit()
    assert _read(client).status_code == 404


def test_world_social_profile_excludes_activity_on_blocked_parent_source() -> None:
    client, engine, principal = _fixture()
    _seed(engine, principal)

    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as db:
        blocked_parent_reply = _post(
            "a-blocked-parent-reply",
            world_id="world-a",
            author_character_id="target-character",
            author_world_character_id="wc-a-target",
            author_name="친구 앵무",
            body="차단된 작성자에게 남긴 대꾸",
            reply_to_post_id="a-third-post",
            created_at=now,
        )
        db.add(blocked_parent_reply)
        db.flush()
        db.add(
            _like(
                post=blocked_parent_reply,
                actor_character_id="viewer-character",
                actor_world_character_id="wc-a-viewer",
                user_id="owner",
                created_at=now,
            )
        )
        db.add(
            models.WorldCharacterBlock(
                id="block-third-source",
                world_id="world-a",
                blocker_world_character_id="wc-a-viewer",
                blocked_world_character_id="wc-a-third",
            )
        )
        db.commit()

    replies = _read(client, tab="replies")
    assert replies.status_code == 200
    assert replies.json()["counts"]["reply_count"] == 1
    assert replies.json()["counts"]["liked_post_count"] == 1
    assert replies.json()["counts"]["received_like_count"] == 2
    assert [item["id"] for item in replies.json()["items"]] == ["a-reply"]
