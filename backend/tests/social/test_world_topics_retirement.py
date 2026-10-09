"""World retirement keeps catalog/actor topics/history and authorization order."""
import asyncio
from types import SimpleNamespace
import pytest
import httpx
from fastapi import FastAPI
from sqlalchemy import select
from social.test_recommendation_topics import scope, post
from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.social.recommendation_router import router
from app.domains.social.models.topics import RecommendationCatalog, RecommendationPreparation, RecommendationPostTopic, RecommendationTopic
from app.domains.social.service.recommendation_topics import replace_source_topics, available_topics, enroll_native_post, match_post
from app.runtime.social import topic_preparation
from app.runtime.social.composition import configure_social_runtime


def test_catalog_initialization_does_not_dispatch_world_preparation(scope, monkeypatch, deny_external_network):
    db, world, character, actor = scope
    def forbidden(*args, **kwargs): pytest.fail("World must not dispatch provider work")
    monkeypatch.setattr(topic_preparation.direct_llm, "generate_json", forbidden)
    topic_preparation.initialize_world(db, world_id=world.id)
    asyncio.run(topic_preparation.prepare_initial_world(db, world_id=world.id, owner_id=world.owner_user_id))
    assert db.get(RecommendationCatalog, world.id) is not None
    assert db.scalar(select(RecommendationPreparation)) is None
    for state in ("pending", "running", "failed"):
        preparation = RecommendationPreparation(id=f"old-{state}", world_id=world.id, source_key="world", state=state)
        db.add(preparation); db.flush()
        asyncio.run(topic_preparation.prepare_initial_world(db, world_id=world.id, owner_id=world.owner_user_id))
        assert preparation.state == state
        db.delete(preparation); db.flush()


def test_dictionary_uses_actors_including_off_and_preserves_historical_links(scope):
    db, world, character, actor = scope
    world_only = replace_source_topics(db, world_id=world.id, world_character_id=None, topics=[("World only", "world"), ("shared", "common")])
    shared = replace_source_topics(db, world_id=world.id, world_character_id=actor.id, topics=[("shared", "common"), ("actor specific", "world")])
    actor.autonomous_enabled = False
    assert next(identity for identity in world_only if db.get(RecommendationTopic, identity).name == "World only") not in {topic.id for topic in available_topics(db, world.id)}
    assert set(shared) == {topic.id for topic in available_topics(db, world.id)}
    row = post(db, world, character, actor)
    enroll_native_post(db, row)
    assert match_post(db, row, final_signature="shared actor specific")
    original = list(db.scalars(select(RecommendationPostTopic)))
    actor.status = "inactive"; db.flush()
    assert set(shared) == {topic.id for topic in available_topics(db, world.id)}
    character.deleted_at = __import__('datetime').datetime.now(__import__('datetime').UTC); db.flush()
    assert not available_topics(db, world.id)
    assert list(db.scalars(select(RecommendationPostTopic))) == original


def test_all_world_routes_are_retired_after_access_checks(scope, deny_external_network):
    db, world, character, actor = scope
    app = FastAPI(); configure_social_runtime(app); app.include_router(router, prefix="/api/v1")
    user = SimpleNamespace(id=world.owner_user_id)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/v1/worlds/{world.id}/recommendation-topics"
            for method, suffix, body in [("GET", "", None), ("PUT", "/key", {"world_character_id": actor.id}), ("POST", "/regenerate", {"request_id": "retired-test-request"})]:
                response = await client.request(method, path + suffix, json=body)
                assert response.status_code == 410
                assert response.json()["detail"] == "world_recommendation_topics_retired"
            user.id = "foreign-user"
            assert (await client.get(path)).status_code == 403
            assert (await client.get("/api/v1/worlds/missing/recommendation-topics")).status_code == 404
    asyncio.run(run())
