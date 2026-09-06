import asyncio
import json

from sqlalchemy.orm import Session

from app.domains.social.schemas.feed import FeedReactionDecision, FeedCommentDraft
from app.runtime.social import feed_reaction_provider as provider_module
from app.runtime.social.world_feed_search import (
    load_ready_search_profile,
    search_world_feed_candidates,
)
from test_feed_reaction_intent import _engine, _seed


def test_direct_reaction_provider_keeps_context_schema_and_call_limits(monkeypatch):
    engine = _engine()
    with Session(engine) as db:
        context, target = _seed(db, with_candidate=True)
        profile = load_ready_search_profile(
            db, world_character_id="world-character-actor"
        )
        candidates = search_world_feed_candidates(
            db,
            profile=profile,
            keywords=profile.keywords[:2],
            allowed_policy_actions=context.activity_policy.allowed_actions,
            now=context.run_started_at,
            search_index=context.social_search_index,
            search_state=context.social_search_state,
        ).candidates
        candidate = candidates[0]
        calls = []
        credential_contexts = []

        def credential(ctx):
            credential_contexts.append(ctx)
            return "fixture"

        async def generate_json(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return FeedReactionDecision(reason_code="model_abstained")
            return FeedCommentDraft(
                text="How did you learn this?",
                source_post_id=candidate.post_id,
                interaction_intent="ordinary_comment",
                comment_purpose="question",
            )

        monkeypatch.setattr(provider_module, "_api_key", credential)
        monkeypatch.setattr(provider_module, "generate_json", generate_json)
        provider = provider_module.DirectFeedReactionProvider()
        tracker = provider_module.RunLlmTracker(max_calls=3)
        result = asyncio.run(
            provider.plan(
                resident_context=context,
                profile=profile,
                candidates=candidates,
                tracker=tracker,
                proposal_eligible_indices=frozenset({0}),
            )
        )
        decision = FeedReactionDecision(
            selected_candidate_index=0,
            selected_action="comment",
            interaction_intent="ordinary_comment",
            comment_purpose="question",
            reason_code=None,
            brief="Ask about the source of this note.",
        )
        draft = asyncio.run(
            provider.write_comment(
                resident_context=context,
                profile=profile,
                candidate=candidate,
                decision=decision,
                tracker=tracker,
            )
        )

        assert result.selected_action is None
        assert draft.source_post_id == target.id
        assert len(calls) == 2
        assert credential_contexts == [context, context]
        assert all(call["tracker"] is tracker for call in calls)
        assert [call["max_output_tokens"] for call in calls] == [900, 1000]
        assert [call["thinking_level"] for call in calls] == ["medium", "medium"]
        assert calls[0]["context"].node == "FeedReactionPlanner"
        assert calls[0]["context"].lane == "world_keyword_feed"
        assert calls[1]["context"].node == "ReplyWriter"
        assert calls[1]["context"].lane == "world_keyword_feed_comment"
        assert (
            calls[0]["response_schema"]
            is provider_module.GEMINI_FEED_REACTION_RESPONSE_SCHEMA
        )
        assert (
            calls[1]["response_schema"]
            is provider_module.GEMINI_FEED_COMMENT_RESPONSE_SCHEMA
        )
        assert calls[0]["should_retry_json_error"](None) is False
        assert "should_retry_json_error" not in calls[1]
        prompt = json.loads(calls[0]["user_prompt"])
        assert prompt["candidates"] == [
            item.model_dump(mode="json") for item in candidates
        ]
        assert prompt["rules"]["max_public_action"] == 1
        assert prompt["rules"]["no_public_ignore"] is True
        assert prompt["rules"]["comment_intent"][
            "proposal_eligible_candidate_indices"
        ] == [0]
        writer_prompt = json.loads(calls[1]["user_prompt"])
        assert writer_prompt["requirements"]["source_post_id"] == target.id
        assert writer_prompt["requirements"]["proposal_schedule"] is None
        assert writer_prompt["validated_decision"] == decision.model_dump(mode="json")
