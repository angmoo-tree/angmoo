import asyncio
import json
from dataclasses import replace
import pytest

from sqlalchemy.orm import Session

from app.domains.social.schemas.feed import FeedReactionDecision, FeedCommentDraft
from app.runtime.social.world_feed_search import (
    load_ready_search_profile,
    search_world_feed_candidates,
)
from social.test_feed_reaction_intent import _engine, _seed


@pytest.mark.parametrize("social_context_enabled", [False, True])
@pytest.mark.parametrize("thinking_level", ["medium", "high"])
def test_direct_reaction_provider_keeps_context_schema_and_call_limits(monkeypatch, social_context_enabled, thinking_level):
    from social.v2_provider_probe import probe
    engine = _engine()
    try:
        with Session(engine) as db:
            context, target = _seed(db, with_candidate=True)
            if social_context_enabled:
                from relationships.test_social_context import SCOPE, relationship, result
                from app.domains.relationships.service.social_context import SocialContextService
                from app.domains.relationships.contracts.social_consumption import SocialContextUse
                snapshot = SocialContextService(lambda query: result(query, [relationship()])).prepare(SCOPE, labels={"friend": "친구"})
                context = replace(context, social_context=SocialContextUse(snapshot, lambda: None))
            calls, tracker, result, written = probe(monkeypatch, context, target, thinking_level=thinking_level)
            assert len(calls) == 2
            assert all(call["tracker"] is tracker for call in calls)
            assert [call["max_output_tokens"] for call in calls] == [4096, 4096]
            assert [call["thinking_level"] for call in calls] == [thinking_level, thinking_level]
            assert [call["context"].node for call in calls] == ["FeedActionPlanner", "FeedWriter"]
            assert result["decisions"][0]["target_id"] == target.id
            assert written["reply_task_results"][0]["task_id"] == "server-task"
            assert written["reply_task_results"][0]["body"] == "어떻게 배웠어?"
            selected = json.loads(calls[0]["user_prompt"])["selected_targets"][0]
            assert "parent_text" not in selected and selected["text"] == target.body
            schema = calls[0]["response_schema"]["properties"]["decisions"]["items"]["properties"]
            assert "proposal_response" not in schema
            assert "proposal_decision" not in calls[1]["response_schema"]["properties"]["replies"]["items"]["properties"]
            assert calls[0]["context"].lane == "feed_action_planner" and calls[1]["context"].lane == "feed_writer"
            if social_context_enabled:
                assert all(json.loads(call["user_prompt"])["context"]["relationships"] == snapshot.prompt_view() for call in calls)
            else:
                assert all("relationships" not in json.loads(call["user_prompt"])["context"] for call in calls)
    finally:
        engine.dispose()
