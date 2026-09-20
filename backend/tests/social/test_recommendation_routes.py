"""Actual recommendation transport with a synthetic owner and no provider calls."""
import asyncio
from types import SimpleNamespace
import httpx
from fastapi import FastAPI
from sqlalchemy import select
from social.test_recommendation_topics import scope
from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.social.recommendation_router import router
from app.domains.social.models.topics import RecommendationPreparation
from app.runtime.social.composition import configure_social_runtime


def test_read_is_side_effect_free_and_mutations_reject_foreign_owner(scope):
    db, world, character, wc = scope
    app = FastAPI(); configure_social_runtime(app)
    app.include_router(router, prefix="/api/v1")
    user = SimpleNamespace(id=world.owner_user_id)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/v1/worlds/{world.id}/recommendation-topics"
            response = await client.get(path)
            assert response.status_code == 200 and response.json()["state"] == "pending"
            assert response.json()["recent_deliveries"] == []
            assert not db.scalar(select(RecommendationPreparation))
            denied = await client.put(path + "/key", json={"world_character_id": wc.id})
            assert denied.status_code == 403
            user.id = "other-owner"
            denied = await client.post(path + "/regenerate", json={"request_id": "safe-test-request"})
            assert denied.status_code == 403
            assert not db.scalar(select(RecommendationPreparation))
    asyncio.run(run())


def test_character_get_history_has_no_write_or_provider_side_effects(scope, monkeypatch):
    from sqlalchemy import event
    from social.test_recommendation_topics import post
    from social.test_recommendation_history import observation, delivery
    from app.runtime.social import topic_preparation
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    observation(db, world, wc, row, decision_outcome="no_action", reason_code="model_abstained")
    delivery(db, world, wc, [row.id]); db.commit()
    def forbidden(*args, **kwargs):
        pytest.fail("GET must not write or call AI")
    import pytest
    monkeypatch.setattr(topic_preparation.direct_llm, "generate_json", forbidden)
    monkeypatch.setattr(db, "commit", forbidden)
    statements = []
    def collect(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    app = FastAPI(); configure_social_runtime(app); app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=character.owner_id)
    event.listen(db.bind, "before_cursor_execute", collect)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            path = f"/api/v1/worlds/{world.id}/recommendation-topics?world_character_id={wc.id}"
            one = await client.get(path); two = await client.get(path)
            assert one.status_code == 200 and one.json() == two.json()
            assert one.json()["recent_deliveries"][0]["posts"][0]["result_state"] == "no_action"
    try:
        asyncio.run(run())
    finally:
        event.remove(db.bind, "before_cursor_execute", collect)
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
