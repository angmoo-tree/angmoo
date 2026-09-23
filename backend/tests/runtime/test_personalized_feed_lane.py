import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_state import read_state
from app.domains.social.models.posts import PostLike
from app.domains.social.models.topics import RecommendationDelivery
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.provider import parse_action
from social.test_feed_reaction_intent import _engine, _seed


def test_one_feed_candidate_skips_selector_and_delivers_before_planning(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            active = db.get(CharacterActiveWorld, ctx.character.id)
            actor = db.get(WorldCharacter, active.world_character_id)
            async def guard(state):
                return {}
            lane = FeedLane(ctx, actor=actor, lane="feed", tracker=RunLlmTracker(max_calls=3), hybrid_service=None, guard=guard)
            monkeypatch.setattr(lane, "relationship", lambda _: {})
            calls = []
            async def plan(**kwargs):
                calls.append("plan")
                delivery = kwargs["delivery"]
                delivery.dispatched()
                delivery.delivered()
                return {**parse_action({"decisions": [{"target_id": post.id, "action": "like", "brief": "Useful discovery"}]}, kwargs["candidates"]),
                    "judged_at": datetime.now(UTC).isoformat()}
            monkeypatch.setattr(lane.provider, "plan", plan)
            result = await build_lane("feed", lane.ports()).ainvoke({"identity": {"activity_id": ctx.run_id},
                "shared_context": {"current_state": read_state(db, world_id=actor.world_id, actor_id=actor.id)}})
            assert calls == ["plan"]
            assert len(result["queries"]) == 1
            assert result["result"]["public_action_count"] == 1
            assert db.scalar(select(func.count(PostLike.id))) == 1
            delivery = db.scalar(select(RecommendationDelivery))
            assert delivery.state == "delivered" and delivery.post_ids == [post.id]
    asyncio.run(scenario())
