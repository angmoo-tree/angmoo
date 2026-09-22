"""Raw Feed decisions must preserve the action while discarding only redundant metadata."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts.activity_thought import ActivityThought
from app.domains.social.schemas.feed import FeedReactionDecision, WorldFeedCandidateRead
from app.domains.social.service.feed_reaction_validation import validate_reaction_decision


@pytest.fixture
def candidates():
    return (WorldFeedCandidateRead(
        candidate_index=0, post_id="post-1", author_world_character_id="wc-2",
        author_character_id="character-2", author_name="B", title="A note",
        body_preview="A useful note", topic_signature="note", created_at=datetime.now(UTC),
        world_local_datetime="2026-09-22T12:00:00+09:00", age_seconds=0,
        age_bucket="recent", matched_keywords=[], matched_fields=[], rank_score=1,
        allowed_actions=["like", "repost", "follow", "comment"],
    ),)


def raw_decision(**changes):
    return dict(
        selected_candidate_index=0, selected_action="like",
        interaction_intent="ordinary_comment", comment_purpose="encouragement",
        reason_code=None, brief="Acknowledge the useful note.",
    ) | changes


@pytest.mark.parametrize("action", ["like", "repost", "follow"])
@pytest.mark.parametrize("fields", [
    {}, {"interaction_intent": None}, {"comment_purpose": None},
    {"interaction_intent": None, "comment_purpose": None},
])
def test_non_comment_keeps_action_and_source_without_mutating_input(candidates, action, fields):
    raw = raw_decision(selected_action=action, **fields)
    original = deepcopy(raw)
    result = validate_reaction_decision(raw, candidates=candidates)
    assert raw == original
    assert result.selected_action == action
    assert result.selected_candidate_index == raw["selected_candidate_index"]
    assert result.brief == raw["brief"]
    assert result.interaction_intent is result.comment_purpose is None
    result._activity_thought = ActivityThought(text="A useful note.", status="recorded")
    assert validate_reaction_decision(result, candidates=candidates) is result
    assert result._activity_thought.text == "A useful note."
    assert validate_reaction_decision(result.model_dump(), candidates=candidates).model_dump() == result.model_dump()


def test_missing_comment_fields_remain_optional(candidates):
    raw = raw_decision()
    del raw["interaction_intent"], raw["comment_purpose"]
    assert validate_reaction_decision(raw, candidates=candidates).selected_action == "like"


@pytest.mark.parametrize("changes", [
    {"interaction_intent": "joint_activity_proposal"},
    {"interaction_intent": "proposal_response"},
    {"interaction_intent": []}, {"interaction_intent": {}},
    {"comment_purpose": "unknown"}, {"comment_purpose": ""},
    {"comment_purpose": []}, {"comment_purpose": {}},
    {"selected_action": "LIKE"}, {"selected_action": "ignore"},
    {"selected_action": ["like", "comment"]},
    {"selected_candidate_index": 1}, {"selected_candidate_index": None},
    {"brief": None}, {"brief": "x" * 281},
    {"reason_code": "model_abstained"}, {"unknown_key": True},
    {"selected_action": "comment", "comment_purpose": None},
    {"selected_action": "comment", "interaction_intent": None},
    {"selected_action": None, "reason_code": "model_abstained"},
])
def test_normalization_does_not_hide_other_invalid_fields(candidates, changes):
    with pytest.raises(ValueError):
        validate_reaction_decision(raw_decision(**changes), candidates=candidates)


def test_server_affordance_is_still_required(candidates):
    candidate = candidates[0].model_copy(update={"allowed_actions": ["comment"]})
    with pytest.raises(ValueError, match="not allowed"):
        validate_reaction_decision(raw_decision(), candidates=(candidate,))


def test_comments_proposal_eligibility_and_no_action_keep_their_contract(candidates):
    comment = validate_reaction_decision(raw_decision(selected_action="comment"), candidates=candidates)
    assert comment.comment_purpose == "encouragement"
    proposal = raw_decision(selected_action="comment", interaction_intent="joint_activity_proposal", comment_purpose=None)
    with pytest.raises(ValueError, match="eligibility"):
        validate_reaction_decision(proposal, candidates=candidates)
    assert validate_reaction_decision(proposal, candidates=candidates, proposal_eligible_indices=frozenset({0})).interaction_intent == "joint_activity_proposal"
    assert validate_reaction_decision({"reason_code": "model_abstained"}, candidates=candidates).selected_action is None


def test_canonical_model_remains_strict():
    with pytest.raises(ValidationError, match="non-comment action cannot have intent or purpose"):
        FeedReactionDecision.model_validate(raw_decision())
