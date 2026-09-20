import asyncio
import pytest
from dataclasses import replace
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from model_fixture_support import models
from social.test_feed_reaction_intent import FakeFeedProvider, _engine, _seed
from app.domains.social.contracts.search_state import SocialSearchState
from app.domains.social.models.topics import RecommendationDelivery
from app.domains.social.schemas.feed import FeedReactionDecision
from app.domains.social.service.recommendation_topics import enroll_native_post
from app.runtime.social.feed_cycle import run_world_keyword_feed


def test_pre_cutover_excluded_without_fts_then_delivery_never_repeats():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        ctx, target = _seed(db, with_candidate=True)
        actor = db.scalar(select(models.WorldCharacter).where(models.WorldCharacter.character_id == ctx.character.id))
        actor.feed_runtime_mode = "topic_recommendation_v1"
        db.commit()
        ctx = replace(ctx, social_search_index=None, social_search_state=SocialSearchState.UNAVAILABLE)
        provider = FakeFeedProvider(FeedReactionDecision(reason_code="model_abstained"))
        first = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        assert first["feed_outcome"] == "no_candidate" and provider.plan_calls == 0
        # Explicitly emulate a native post created by the new source command.
        enroll_native_post(db, target); db.commit()
        ctx = replace(ctx, run_id="second-cycle", run_started_at=ctx.run_started_at+timedelta(hours=1))
        second = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        assert provider.plan_calls == 1
        assert db.scalar(select(models.WorldCharacterFeedObservation)).status == "observed"
        assert db.scalar(select(RecommendationDelivery)).state == "delivered"
        from app.runtime.social.recommendation_history import read_delivery_history
        history = read_delivery_history(db, world_id=actor.world_id, world_character_id=actor.id)
        assert history[0]["posts"][0]["post_id"] == target.id
        assert history[0]["posts"][0]["result_state"] == "no_action"
        ctx = replace(ctx, run_id="third-cycle", run_started_at=ctx.run_started_at+timedelta(hours=1))
        third = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        assert third["feed_outcome"] == "no_candidate" and provider.plan_calls == 1
        assert read_delivery_history(db, world_id=actor.world_id, world_character_id=actor.id) == history
    engine.dispose()


@pytest.mark.parametrize("delivery_state,expected", [("precall", "prepared"), ("timeout", "uncertain"), ("invalid_response", "delivered")])
def test_failed_response_delivery_boundary(delivery_state, expected):
    from app.integrations.direct_llm import DirectLlmError
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        ctx, target = _seed(db, with_candidate=True)
        actor = db.scalar(select(models.WorldCharacter).where(models.WorldCharacter.character_id == ctx.character.id))
        actor.feed_runtime_mode = "topic_recommendation_v1"
        enroll_native_post(db, target); db.commit()
        class FailedProvider:
            async def plan(self, **kwargs):
                if delivery_state != "precall":
                    self.delivery.dispatched()
                if delivery_state == "invalid_response":
                    self.delivery.delivered()
                raise DirectLlmError("synthetic response failure")
        asyncio.run(run_world_keyword_feed(ctx, provider=FailedProvider()))
        db.expire_all()
        assert db.scalar(select(RecommendationDelivery)).state == expected
        observation = db.scalar(select(models.WorldCharacterFeedObservation))
        assert (observation.status == "observed") == (expected == "delivered")
    engine.dispose()
