"""Actual public/World reads and accepted Social writes on file SQLite only."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.characters.models import Character
from app.domains.identity.dependencies import get_current_user, get_optional_current_user
from app.domains.identity.models import User
from app.domains.routines.models import AgentRun
from app.domains.social.contracts.profile_activity import WorldCharacterSocialProfileQuery
from app.domains.social.models.posts import Post
from app.domains.social.exceptions import PostWorldScopeError
from app.domains.social.router import router, manual_router
from app.domains.social.schemas.community import PostCreate, TimelineReplyCreate
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.service.configuration import effective_configuration
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.runtime.social.agent_tools import agent_tool_actions
from app.runtime.social.agent_tool_reads import agent_tool_reads
from app.runtime.social.composition import configure_social_runtime
from app.runtime.social.profile_composition import world_character_social_profile_service
from app.runtime.social.timeline import timeline_service
from world_configuration_fixture_support import seed_configuration_fixture


pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture(params=("creation", "legacy_transition"))
def fixture(tmp_path, request):
    legacy = request.param == "legacy_transition"
    engine = seed_configuration_fixture(tmp_path / "post-authors.sqlite", legacy=legacy)
    if legacy:
        from app.runtime.migrations.sqlite_versions import world_configuration_v28
        with engine.begin() as connection:
            before = world_configuration_v28.capture_delta(connection)
            world_configuration_v28.upgrade(connection)
            world_configuration_v28.verify_delta(connection, before)
        with Session(engine) as db:
            for suffix in ("a", "b"):
                OwnerControlledIdentityService(db).ensure(world_id=f"config-world-{suffix}", current_user_id="fixture-owner")
    with Session(engine) as db:
        for suffix in ("a", "b"):
            stored = db.get(WorldCharacterConfiguration, f"config-role-{suffix}")
            stored.profile = {**stored.profile, "display_name": f"World {suffix} Bram", "handle": f"world_bram_{suffix}",
                "avatar_url": f"/media/world-{suffix}.png"}
            common = db.get(Character, f"config-actor-{suffix}")
            common.name, common.handle, common.avatar_url = f"Common {suffix} Bram", f"common_bram_{suffix}", "/media/common.png"
        db.commit()
    app = FastAPI()
    configure_social_runtime(app)
    app.include_router(router, prefix="/api/v1")
    app.include_router(manual_router, prefix="/api/v1")

    def session():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    def principal():
        with Session(engine) as db:
            return db.get(User, "fixture-owner")

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = principal
    app.dependency_overrides[get_optional_current_user] = lambda: None
    with TestClient(app, base_url="http://127.0.0.1:3000") as client:
        yield engine, client
    engine.dispose()


def add_post(db, identifier, suffix=None, *, reply_to=None, quote=None):
    post = Post(id=identifier, author_user_id="fixture-owner", author_character_id=f"config-actor-{suffix or 'a'}",
        author_name="Historical accepted name", world_id=f"config-world-{suffix}" if suffix else None,
        author_world_character_id=f"config-role-{suffix}" if suffix else None,
        title="Synthetic title", body="Synthetic body", post_type="reply" if reply_to else "quote" if quote else "post",
        reply_to_post_id=reply_to, quote_post_id=quote)
    db.add(post)
    db.flush()
    return post


def assert_world_author(item, suffix):
    assert item["author_name"] == f"World {suffix} Bram"
    assert item["author_handle"] == f"world_bram_{suffix}"
    assert item["author_avatar_url"] == f"/media/world-{suffix}.png"


def test_actual_public_feed_thread_profiles_and_nested_references_use_world_values(fixture):
    engine, client = fixture
    with Session(engine) as db:
        add_post(db, "author-a", "a")
        add_post(db, "author-a-reply", "a", reply_to="author-a")
        add_post(db, "author-b", "b")
        add_post(db, "author-global")
        add_post(db, "author-global-quote", quote="author-b")
        db.commit()
        before = [(row.id, row.author_name) for row in db.scalars(select(Post).order_by(Post.id))]
        configurations = [(row.world_character_id, row.profile, row.settings) for row in db.scalars(select(WorldCharacterConfiguration))]
    for path in ("/feed?limit=100", "/profiles/characters/config-actor-a/feed", "/profiles/users/fixture-owner/feed"):
        response = client.get(f"/api/v1{path}")
        assert response.status_code == 200, response.text
        rows = {row["id"]: row for row in response.json()["items"]}
        for identifier, row in rows.items():
            if row["world_id"]:
                assert_world_author(row, row["world_id"][-1])
            else:
                assert row["author_name"] == "Common a Bram" and row["author_handle"] == "common_bram_a"
                assert row["author_avatar_url"] == "/media/common.png"
            if identifier == "author-global-quote":
                assert_world_author(row["quoted_post"], "b")
    for path in ("/posts/author-a", "/posts/author-a/thread"):
        response = client.get(f"/api/v1{path}")
        assert response.status_code == 200, response.text
        result = response.json()
        assert_world_author(result["post"] if "post" in result else result, "a")
        if "replies" in result:
            assert [row["id"] for row in result["replies"]] == ["author-a-reply"]
            assert_world_author(result["replies"][0], "a")
    response = client.get("/api/v1/worlds/config-world-a/manual-social/feed")
    assert response.status_code == 200, response.text
    for item in response.json()["items"]:
        assert_world_author(item, "a")
    with Session(engine) as db:
        page = world_character_social_profile_service(db).read(WorldCharacterSocialProfileQuery(
            world_id="config-world-a", world_character_id="config-role-a", current_user_id="fixture-owner"))
        assert [item.id for item in page.items] == ["author-a"]
        assert_world_author(vars_for_profile(page.items[0]), "a")
        assert [(row.id, row.author_name) for row in db.scalars(select(Post).order_by(Post.id))] == before
        assert [(row.world_character_id, row.profile, row.settings) for row in db.scalars(select(WorldCharacterConfiguration))] == configurations
        assert not db.dirty


def vars_for_profile(item):
    return {name: getattr(item, name) for name in ("author_name", "author_handle", "author_avatar_url")}


def test_author_profile_queries_are_batched_and_missing_roles_do_not_borrow_local_profiles(fixture):
    engine, client = fixture
    with Session(engine) as db:
        for suffix in ("a", "b"):
            for number in range(25):
                add_post(db, f"many-{suffix}-{number}", suffix)
        db.commit()
    profile_selects = []

    def record(_connection, _cursor, sql, _parameters, _context, _many):
        if sql.lstrip().upper().startswith("SELECT") and "world_character_configurations.profile" in sql:
            profile_selects.append(sql)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = client.get("/api/v1/feed?limit=100")
        assert result.status_code == 200, result.text
        assert len(result.json()["items"]) == 50
        assert len(profile_selects) == 2
    finally:
        event.remove(engine, "before_cursor_execute", record)
    with Session(engine) as db:
        db.get(WorldCharacter, "config-role-a").status = "inactive"
        db.commit()
    result = client.get("/api/v1/posts/many-a-0")
    assert result.status_code == 200
    item = result.json()
    assert item["author_name"] == "Historical accepted name"
    assert item["author_handle"] is None and item["author_avatar_url"] is None
    assert "Common a Bram" not in result.text


def test_actual_tool_post_and_reply_store_accepted_name_after_world_and_common_edits(fixture):
    engine, _client = fixture
    with Session(engine, expire_on_commit=False) as db:
        role = db.get(WorldCharacter, "config-role-a")
        role.autonomous_enabled = True
        db.commit()
        accepted = effective_configuration(db, world_character_id=role.id)
        run = AgentRun(id="author-accepted-run", user_id="fixture-owner", character_id=role.character_id,
            agent_id="fixture-slot", credential_id="config-credential-a", session_key="agent:fixture:resident-manual:author",
            tool_auth_key="synthetic-author-tool-key", status="running",
            input_snapshot={"_world_configuration": accepted.request_snapshot()})
        db.add(run)
        stored = db.get(WorldCharacterConfiguration, role.id)
        stored.profile = {**stored.profile, "display_name": "Later World Bram"}
        db.get(Character, role.character_id).name = "Later common Bram"
        role.autonomous_enabled = False
        role.version += 1
        db.commit()
        created = agent_tool_actions.create_agent_tool_post(db, run.session_key,
            PostCreate(title="Accepted title", body="Accepted body", author_character_id=role.character_id),
            world_id=role.world_id, author_world_character_id=role.id)
        saved = db.get(Post, created.id)
        assert saved.author_name == "World a Bram"
        assert (saved.world_id, saved.author_world_character_id) == (accepted.world_id, accepted.world_character_id)
        owner = OwnerControlledIdentityService(db).get(world_id=role.world_id, current_user_id="fixture-owner")
        target = Post(id="author-owner-target", author_user_id="fixture-owner", author_character_id=owner.character_id,
            author_name="Owner", world_id=role.world_id, author_world_character_id=owner.world_character_id,
            title="Reply target", body="Synthetic target")
        db.add(target)
        db.commit()
        # Canonical tool authorization requires a viewed thread before reply.
        agent_tool_reads.get_agent_tool_post_thread(db, run.session_key, target.id)
        reply = agent_tool_actions.reply_agent_tool_post(db, run.session_key, target.id,
            TimelineReplyCreate(body="Accepted reply", author_character_id=role.character_id))
        assert db.get(Post, reply.id).author_name == "World a Bram"
        assert db.get(Character, role.character_id).name == "Later common Bram"
        assert db.get(WorldCharacterConfiguration, role.id).profile["display_name"] == "Later World Bram"
        assert run.input_snapshot["_world_configuration"] == accepted.request_snapshot()


def test_manual_world_write_uses_current_profile_and_frozen_foreign_author_rejects_before_post(fixture):
    engine, _client = fixture
    with Session(engine) as db:
        actor = db.get(WorldCharacter, "config-role-a")
        foreign = effective_configuration(db, world_character_id="config-role-b")
        before = len(db.scalars(select(Post)).all())
        with pytest.raises(PostWorldScopeError, match="world_author_snapshot_scope_invalid"):
            from app.domains.social.contracts.post_authors import WorldPostAuthor
            timeline_service.create_post(db, db.get(User, "fixture-owner"), PostCreate(
                title="Foreign", body="Synthetic", author_character_id=actor.character_id),
                world_id=actor.world_id, author_world_character_id=actor.id,
                author_profile=WorldPostAuthor(foreign.world_id, foreign.world_character_id,
                    foreign.character_id, foreign.profile.display_name, foreign.profile.handle, foreign.profile.avatar_url))
        assert len(db.scalars(select(Post)).all()) == before
        created = timeline_service.create_post(db, db.get(User, "fixture-owner"), PostCreate(
            title="Manual", body="Synthetic", author_character_id=actor.character_id),
            world_id=actor.world_id, author_world_character_id=actor.id)
        assert db.get(Post, created.id).author_name == "World a Bram"


def test_historical_tool_run_never_reloads_current_world_configuration(fixture):
    engine, _client = fixture
    with Session(engine, expire_on_commit=False) as db:
        actor = db.get(WorldCharacter, "config-role-a")
        run = AgentRun(id="historical-author-run", user_id="fixture-owner", character_id=actor.character_id,
            agent_id="fixture-slot", credential_id="config-credential-a", session_key="agent:fixture:resident-manual:legacy",
            tool_auth_key="synthetic-historical-author-key", status="running", input_snapshot=None)
        db.add(run)
        db.commit()
        statements = []

        def record(_connection, _cursor, sql, _parameters, _context, _many):
            if "world_character_configurations" in sql:
                statements.append(sql)

        event.listen(engine, "before_cursor_execute", record)
        try:
            created = agent_tool_actions.create_agent_tool_post(db, run.session_key,
                PostCreate(title="Historical title", body="Historical body", author_character_id=actor.character_id),
                world_id=actor.world_id, author_world_character_id=actor.id)
            assert db.get(Post, created.id).author_name == "Common a Bram"
            assert run.input_snapshot is None
            assert statements == []
        finally:
            event.remove(engine, "before_cursor_execute", record)
