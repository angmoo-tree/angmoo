import pytest
from pydantic import ValidationError

from app import schemas
from app.services import agent_runs, community


@pytest.mark.parametrize("schema_cls", [schemas.FollowCreate, schemas.BotFollowCreate])
def test_follow_requests_reject_user_targets(schema_cls):
    with pytest.raises(ValidationError):
        schema_cls(target_type="user", target_id="user-1")


@pytest.mark.parametrize("schema_cls", [schemas.FollowCreate, schemas.BotFollowCreate])
def test_follow_requests_accept_character_targets(schema_cls):
    request = schema_cls(target_type="character", target_id="char-1")

    assert request.target_type == "character"
    assert request.target_id == "char-1"


def test_complete_tick_follow_action_rejects_user_target():
    with pytest.raises(ValidationError):
        schemas.AgentCompleteTickAction(
            action_type="follow",
            target_type="user",
            target_id="user-1",
        )


def test_follow_candidate_target_parts_ignore_user_profiles():
    assert agent_runs._profile_target_parts(user_id="user-1") == (None, None)
    assert community._candidate_target_parts(user_id="user-1", character_id=None) == (
        None,
        None,
    )


def test_follow_candidate_target_parts_keep_character_profiles():
    assert agent_runs._profile_target_parts(character_id="char-1") == (
        "character",
        "char-1",
    )
    assert community._candidate_target_parts(
        user_id=None, character_id="char-1"
    ) == ("character", "char-1")
