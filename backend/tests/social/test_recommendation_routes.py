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
            assert not db.scalar(select(RecommendationPreparation))
            denied = await client.put(path + "/key", json={"world_character_id": wc.id})
            assert denied.status_code == 403
            user.id = "other-owner"
            denied = await client.post(path + "/regenerate", json={"request_id": "safe-test-request"})
            assert denied.status_code == 403
            assert not db.scalar(select(RecommendationPreparation))
    asyncio.run(run())
