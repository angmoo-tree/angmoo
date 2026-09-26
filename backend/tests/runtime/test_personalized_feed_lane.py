import asyncio
from datetime import UTC, datetime, timedelta
import pytest

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_state import read_state
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.social.models.posts import PostLike
from app.domains.social.models.topics import RecommendationDelivery
from app.domains.social.service.world_feed import claim_cycle_keywords
from app.integrations.direct_llm import RunLlmTracker
from app.integrations import direct_llm
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.planner_contract import parse_action
from app.runtime.autonomous_activity import provider as activity_provider
from social.test_feed_reaction_intent import _engine, _seed


def test_feed_planner_retry_executes_only_valid_second_decision(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            async def guard(_state):
                return {}
            tracker = RunLlmTracker(max_calls=3)
            lane = FeedLane(ctx, actor=actor, lane="feed", tracker=tracker,
                            hybrid_service=None, guard=guard)
            monkeypatch.setattr(lane, "relationship", lambda _: {})
            monkeypatch.setattr(activity_provider, "_api_key", lambda _: "test")
            monkeypatch.setattr(activity_provider, "_llm_context", lambda *_args, **_kwargs:
                direct_llm.DirectLlmCallContext(
                    "cred", actor.id, ctx.run_id, "FeedActionPlanner",
                    "feed_action_planner", "google", "gemini-3.1-flash-lite"))
            calls = []
            async def fake_generate_text(**kwargs):
                calls.append(kwargs)
                order = tracker.next_call_order()
                kwargs["on_request_start"](order)
                tracker.record_call(context=kwargs["context"], call_order=order,
                                    provider_call_order=tracker.next_provider_call_order(),
                                    status="ok", duration_ms=1, usage={},
                                    max_output_tokens=kwargs["max_output_tokens"],
                                    finish_reason="STOP")
                decision = {"target_id": post.id, "action": "like"}
                if len(calls) == 2:
                    decision["brief"] = "Recognize a useful discovery"
                return direct_llm.DirectLlmResponse("", {
                    "decisions": [decision], "state_update": None,
                    "relationship_metrics": []}, {}, "STOP")
            monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)
            result = await build_lane("feed", lane.ports()).ainvoke({
                "identity": {"activity_id": ctx.run_id},
                "shared_context": {"current_state": read_state(
                    db, world_id=actor.world_id, actor_id=actor.id)}})
            assert len(calls) == 2
            assert [call["max_output_tokens"] for call in calls] == [4096, 4096]
            assert result["result"]["public_action_count"] == 1
            assert db.scalar(select(func.count(PostLike.id))) == 1
            assert db.scalar(select(RecommendationDelivery)).state == "delivered"
            assert tracker.summary()["call_count"] == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["guard_change", "invalid_again"])
def test_feed_planner_failed_retry_keeps_delivery_but_has_no_public_effect(monkeypatch, failure):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            async def guard(_state):
                return {}
            tracker = RunLlmTracker(max_calls=3)
            lane = FeedLane(ctx, actor=actor, lane="feed", tracker=tracker,
                            hybrid_service=None, guard=guard)
            monkeypatch.setattr(lane, "relationship", lambda _: {})
            monkeypatch.setattr(activity_provider, "_api_key", lambda _: "test")
            monkeypatch.setattr(activity_provider, "_llm_context", lambda *_args, **_kwargs:
                direct_llm.DirectLlmCallContext(
                    "cred", actor.id, ctx.run_id, "FeedActionPlanner",
                    "feed_action_planner", "google", "gemini-3.1-flash-lite"))
            calls = []
            async def fake_generate_text(**kwargs):
                calls.append(kwargs)
                order = tracker.next_call_order()
                kwargs["on_request_start"](order)
                tracker.record_call(context=kwargs["context"], call_order=order,
                                    provider_call_order=tracker.next_provider_call_order(),
                                    status="ok", duration_ms=1, usage={},
                                    max_output_tokens=kwargs["max_output_tokens"],
                                    finish_reason="STOP")
                if failure == "guard_change" and len(calls) == 1:
                    post.body += " Changed after the first provider response."
                    db.commit()
                return direct_llm.DirectLlmResponse("", {
                    "decisions": [{"target_id": post.id, "action": "like"}],
                    "state_update": None, "relationship_metrics": []}, {}, "STOP")
            monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)
            with pytest.raises((ValueError, direct_llm.DirectLlmJsonError)) as caught:
                await build_lane("feed", lane.ports()).ainvoke({
                    "identity": {"activity_id": ctx.run_id},
                    "shared_context": {"current_state": read_state(
                        db, world_id=actor.world_id, actor_id=actor.id)}})
            if failure == "guard_change":
                assert "activity_source_changed" in str(caught.value)
                assert len(calls) == 1
            else:
                assert isinstance(caught.value, direct_llm.DirectLlmJsonError)
                assert caught.value.attempt_count == 2
                assert len(calls) == 2
            assert db.scalar(select(func.count(PostLike.id))) == 0
            assert db.scalar(select(RecommendationDelivery)).state == "delivered"
    asyncio.run(scenario())


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


def test_v2_feed_reclaims_expired_observation_and_delivers_candidate(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            active = db.get(CharacterActiveWorld, ctx.character.id)
            actor = db.get(WorldCharacter, active.world_character_id)
            previous = WorldCharacterFeedObservation(
                id="feed-observation-previous-run",
                world_id=actor.world_id,
                observer_world_character_id=actor.id,
                post_id=post.id,
                status="claimed",
                claim_token="previous-token",
                lease_expires_at=ctx.run_started_at - timedelta(minutes=1),
                cycle_key="previous-cycle",
                run_id="previous-run",
                matched_keywords=["alchemy"],
                matched_fields=["title"],
                rank_score=1,
                post_created_at=post.created_at,
                claimed_at=ctx.run_started_at - timedelta(minutes=20),
            )
            db.add(previous)
            db.commit()
            db.expire(previous)
            assert previous.lease_expires_at.tzinfo is None

            async def guard(state):
                return {}

            lane = FeedLane(ctx, actor=actor, lane="feed", tracker=RunLlmTracker(max_calls=3), hybrid_service=None, guard=guard)
            monkeypatch.setattr(lane, "relationship", lambda _: {})

            async def plan(**kwargs):
                delivery = kwargs["delivery"]
                delivery.dispatched()
                delivery.delivered()
                return {**parse_action({"decisions": [{"target_id": post.id, "action": "like", "brief": "Useful discovery"}]}, kwargs["candidates"]),
                    "judged_at": datetime.now(UTC).isoformat()}

            monkeypatch.setattr(lane.provider, "plan", plan)
            result = await build_lane("feed", lane.ports()).ainvoke({"identity": {"activity_id": ctx.run_id},
                "shared_context": {"current_state": read_state(db, world_id=actor.world_id, actor_id=actor.id)}})
            db.refresh(previous)
            assert result["result"]["public_action_count"] == 1
            assert result["lane_data"]["_feed"]["observation_ids"] == [previous.id]
            assert previous.claim_token != "previous-token"
            assert previous.run_id == ctx.run_id
            assert db.scalar(select(func.count(PostLike.id))) == 1

    asyncio.run(scenario())


def test_v2_feed_duplicate_cycle_does_not_reenter_candidate_load(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, _post = _seed(db, with_candidate=True)
            active = db.get(CharacterActiveWorld, ctx.character.id)
            actor = db.get(WorldCharacter, active.world_character_id)

            async def guard(state):
                return {}

            lane = FeedLane(ctx, actor=actor, lane="feed", tracker=RunLlmTracker(max_calls=3), hybrid_service=None, guard=guard)
            monkeypatch.setattr(lane, "relationship", lambda _: {})
            profile = lane.profile()
            claim_cycle_keywords(db, profile=profile, cycle_key=f"v2:{ctx.run_id}:feed", run_id=ctx.run_id)
            db.commit()  # Simulate a prior LoadCandidates failure after its cursor commit.
            calls = []

            async def plan(**kwargs):
                calls.append(kwargs)
                raise AssertionError("duplicate cycle must not call the provider")

            monkeypatch.setattr(lane.provider, "plan", plan)
            result = await build_lane("feed", lane.ports()).ainvoke({"identity": {"activity_id": ctx.run_id},
                "shared_context": {"current_state": read_state(db, world_id=actor.world_id, actor_id=actor.id)}})
            assert result["lane_data"]["duplicate_cycle"] is True
            assert result["candidates"] == []
            assert calls == []
            assert db.scalar(select(func.count(WorldCharacterFeedObservation.id))) == 0

    asyncio.run(scenario())
