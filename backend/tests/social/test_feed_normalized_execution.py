"""Exercise the real JSON validator and C recommendation cycle with a fake transport."""

import asyncio
import json
import logging
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.relationships.models.personalization import RelationshipMetricApplication
from app.domains.relationships.service.policy_activation import activate_policy
from app.domains.social.models.topics import RecommendationDelivery
from app.domains.social.models.activity_thought import SocialActivityThought
from app.domains.social.service import feed_cycle
from app.domains.social.service.recommendation_topics import enroll_native_post
from app.integrations import direct_llm
from app.runtime.relationships.experience_metrics import apply_pending_metrics
from app.runtime.social import feed_reaction_provider as provider_module
from app.runtime.social.feed_cycle import run_world_keyword_feed
from social.test_feed_reaction_intent import _engine
from social.test_recommendation_cycle import _seed
from social.test_feed_decision_normalization import raw_decision


def seed_cycle(db, *, metrics):
    ctx, target = _seed(db, with_candidate=True)
    actor = db.get(models.WorldCharacter, "world-character-actor")
    actor.feed_runtime_mode = "topic_recommendation_v1"
    if metrics:
        activate_policy(db, world_id=actor.world_id, now=target.created_at - timedelta(days=1))
    enroll_native_post(db, target)
    db.commit()
    return ctx, target, actor


@pytest.mark.parametrize("thought", [False, True])
@pytest.mark.parametrize("metrics", [False, True])
def test_raw_normalized_like_executes_once_without_writer_or_recall(monkeypatch, caplog, thought, metrics):
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        ctx, target, actor = seed_cycle(db, metrics=metrics)
        calls = []

        async def transport(**kwargs):
            calls.append(kwargs)
            assert kwargs["context"].node == "FeedReactionPlanner"
            raw = raw_decision()
            if thought:
                raw["thought"] = "A helpful note worth acknowledging."
            if metrics:
                raw["relationship_metrics"] = [dict(
                    target_ref=target.author_world_character_id, affinity="increase",
                    trust="keep", tension="keep", new_evidence_refs=[target.id],
                )]
            return direct_llm.DirectLlmResponse(text=json.dumps(raw), parsed=None, usage={}, finish_reason="STOP")

        monkeypatch.setattr(direct_llm, "generate_text", transport)
        monkeypatch.setattr(provider_module, "_api_key", lambda ctx: "fixture")
        provider = provider_module.DirectFeedReactionProvider(thought_enabled=thought)
        with caplog.at_level(logging.INFO, logger=provider_module.__name__):
            result = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        assert result["feed_outcome"] == "ACTION_SUCCEEDED"
        assert result["delivered_count"] == 1
        assert len(calls) == 1
        assert db.scalar(select(func.count(models.PostLike.id))) == 1
        assert db.scalar(select(func.count(models.Post.id))) == 1
        execution = db.scalar(select(models.AgentPublicActionExecution))
        assert execution.action_type == "like" and execution.status == "succeeded"
        assert execution.interaction_intent is execution.comment_purpose is None
        assert db.scalar(select(RecommendationDelivery)).state == "delivered"
        observation = db.scalar(select(models.WorldCharacterFeedObservation))
        assert observation.status == "observed" and observation.selected_action == "like"
        assert observation.interaction_intent is observation.comment_purpose is None
        saved_thought = db.scalar(select(SocialActivityThought))
        if thought:
            assert saved_thought.thought_text == "A helpful note worth acknowledging."

        # Validate the final provider instructions after thought/schema transforms.
        request = calls[0]
        assert "For like, repost, follow or NO_ACTION, return null for both" in request["system_prompt"]
        examples = json.loads(request["user_prompt"])["rules"]["action_field_examples"]
        assert examples[0] == dict(selected_action="like", interaction_intent=None, comment_purpose=None)
        properties = request["response_schema"]["properties"]
        assert "Must be null for like" in properties["interaction_intent"]["description"]
        assert "null" in properties["comment_purpose"]["type"]
        assert ("thought" in properties) == thought
        assert ("relationship_metrics" in properties) == metrics
        normalization = [r.getMessage() for r in caplog.records if "world_feed_decision_normalized" in r.getMessage()]
        assert len(normalization) == 1
        assert "fields=interaction_intent,comment_purpose" in normalization[0]
        assert "A helpful note" not in normalization[0] and "Acknowledge" not in normalization[0]

        if metrics:
            application = db.scalar(select(RelationshipMetricApplication))
            assert application is not None
            apply_pending_metrics(db, world_id=actor.world_id)
            db.refresh(application)
            assert application.status == "applied"
            assert application.actual_delta["affinity"] == 1
            assert application.actual_delta["trust"] == 0
            version = application.state_version

        again = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        assert again["feed_outcome"] == "duplicate_cycle"
        later = replace(ctx, run_id="next-cycle", run_started_at=ctx.run_started_at + timedelta(hours=1))
        assert asyncio.run(run_world_keyword_feed(later, provider=provider))["feed_outcome"] == "no_candidate"
        assert len(calls) == 1
        assert db.scalar(select(func.count(models.PostLike.id))) == 1
        assert db.scalar(select(func.count(models.AgentPublicActionExecution.id))) == 1
        if metrics:
            apply_pending_metrics(db, world_id=actor.world_id)
            db.refresh(application)
            assert application.state_version == version
            assert db.scalar(select(func.count(RelationshipMetricApplication.id))) == 1
    engine.dispose()


@pytest.mark.parametrize("mode,expected", [
    ("normal_like", "ACTION_SUCCEEDED"),
    ("comment", "ACTION_SUCCEEDED"),
    ("no_action", "model_abstained"),
    ("invalid", "planner_failed"),
    ("invalid_candidate", "planner_failed"),
    ("stale", "target_stale"),
    ("deleted_while_planning", "observation_failed"),
])
def test_other_raw_decisions_and_stale_target_keep_boundaries(monkeypatch, caplog, mode, expected):
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        ctx, target, _actor = seed_cycle(db, metrics=False)
        nodes = []

        async def transport(**kwargs):
            nodes.append(kwargs["context"].node)
            if len(nodes) == 2:
                assert mode == "comment"
                raw = dict(text="Thanks for sharing the note.", source_post_id=target.id,
                           interaction_intent="ordinary_comment", comment_purpose="encouragement")
            elif mode == "no_action":
                raw = {"reason_code": "model_abstained"}
            elif mode == "comment":
                raw = raw_decision(selected_action="comment")
            elif mode == "invalid":
                raw = raw_decision(interaction_intent="joint_activity_proposal")
            elif mode == "invalid_candidate":
                raw = raw_decision(selected_candidate_index=19)
            elif mode == "normal_like":
                raw = raw_decision(interaction_intent=None, comment_purpose=None)
            else:
                raw = raw_decision()
            if mode == "deleted_while_planning":
                # Simulate a real source change while the provider was responding.
                target.deleted_at = ctx.run_started_at
                db.commit()
            return direct_llm.DirectLlmResponse(text=json.dumps(raw), parsed=None, usage={}, finish_reason="STOP")

        monkeypatch.setattr(direct_llm, "generate_text", transport)
        monkeypatch.setattr(provider_module, "_api_key", lambda ctx: "fixture")
        if mode == "stale":
            revalidate = feed_cycle.revalidate_candidate_actions

            def revoke_before_execution(*args, **kwargs):
                target.deleted_at = ctx.run_started_at
                db.flush()
                return revalidate(*args, **kwargs)

            monkeypatch.setattr(feed_cycle, "revalidate_candidate_actions", revoke_before_execution)
        provider = provider_module.DirectFeedReactionProvider(thought_enabled=False)
        with caplog.at_level(logging.INFO, logger=provider_module.__name__):
            result = asyncio.run(run_world_keyword_feed(ctx, provider=provider))
        assert result["feed_outcome"] == expected
        assert nodes == (["FeedReactionPlanner", "ReplyWriter"] if mode == "comment" else ["FeedReactionPlanner"])
        assert db.scalar(select(RecommendationDelivery)).state == "delivered"
        if mode not in {"stale", "deleted_while_planning"}:
            assert not any("world_feed_decision_normalized" in r.getMessage() for r in caplog.records)
        if expected != "ACTION_SUCCEEDED":
            assert db.scalar(select(func.count(models.AgentPublicActionExecution.id))) == 0
            assert db.scalar(select(func.count(models.PostLike.id))) == 0
        elif mode == "comment":
            assert db.scalar(select(func.count(models.Post.id)).where(models.Post.reply_to_post_id == target.id)) == 1
    engine.dispose()
