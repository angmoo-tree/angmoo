import app.domains.local_bot.schemas as bot_schemas
import app.domains.social.schemas.community as social_schemas
import pytest
from pydantic import ValidationError



from app.domains.routines.service import action_candidates as agent_runs


@pytest.mark.parametrize("schema_cls", [social_schemas.FollowCreate, bot_schemas.BotFollowCreate])
def test_follow_requests_reject_user_targets(schema_cls):
    with pytest.raises(ValidationError):
        schema_cls(target_type="user", target_id="user-1")


@pytest.mark.parametrize("schema_cls", [social_schemas.FollowCreate, bot_schemas.BotFollowCreate])
def test_follow_requests_accept_character_targets(schema_cls):
    request = schema_cls(target_type="character", target_id="char-1")

    assert request.target_type == "character"
    assert request.target_id == "char-1"


def test_complete_tick_follow_action_rejects_user_target():
    with pytest.raises(ValidationError):
        social_schemas.AgentCompleteTickAction(
            action_type="follow",
            target_type="user",
            target_id="user-1",
        )


def test_follow_candidate_target_parts_ignore_user_profiles():
    import app.domains.social.service.resident_affordances as community
    assert agent_runs._profile_target_parts(user_id="user-1") == (None, None)
    assert community._candidate_target_parts(user_id="user-1", character_id=None) == (
        None,
        None,
    )


def test_follow_candidate_target_parts_keep_character_profiles():
    import app.domains.social.service.resident_affordances as community
    assert agent_runs._profile_target_parts(character_id="char-1") == (
        "character",
        "char-1",
    )
    assert community._candidate_target_parts(
        user_id=None, character_id="char-1"
    ) == ("character", "char-1")
