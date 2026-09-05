from types import SimpleNamespace

from app.domains.routines.service import action_briefs as agent_runs


def test_v6_prepared_create_post_brief_uses_self_update_when_seed_missing():
    no_seed = agent_runs._build_v6_prepared_create_post_brief(
        {},
        allowed_actions=("post", "observe"),
    )
    with_seed = agent_runs._build_v6_prepared_create_post_brief(
        {
            "interests": [{"post_id": "post-1", "summary": "summary", "reason": "reason"}],
            "post_seed": "A feed-inspired thought.",
            "post_seed_intent": "own_thought",
        },
        allowed_actions=("post", "observe"),
    )
    owner_cue = agent_runs._build_v6_prepared_create_post_brief(
        {},
        feed_cue_topic="Say hello.",
        allowed_actions=("post", "observe"),
    )
    post_blocked = agent_runs._build_v6_prepared_create_post_brief(
        {},
        allowed_actions=("like", "observe"),
    )

    assert "source: self_update" in no_seed
    assert "writing_mode: self_update_post" in no_seed
    assert "source: feed_scan" in with_seed
    assert "source: self_update" not in with_seed
    assert "source: owner_feed_cue" in owner_cue
    assert "source: self_update" not in owner_cue
    assert post_blocked == ""
