from types import SimpleNamespace

from app.domains.routines.service import action_briefs as agent_briefs
from app.domains.routines.service import action_menu as agent_runs
from app.runtime.resident import context_references
from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences


def test_v6_action_menu_exposes_create_post_only_with_prepared_brief():
    without_brief = agent_runs._format_v6_action_menu_table(
        SqlAlchemyResidentActionReferences(None),
        character_id="char-1",
        allowed_actions=("post", "observe"),
        inbox_candidates=[],
        feed_interest_payload={},
        prepared_create_post_brief="",
    )
    with_owner_cue = agent_runs._format_v6_action_menu_table(
        SqlAlchemyResidentActionReferences(None),
        character_id="char-1",
        allowed_actions=("post", "observe"),
        inbox_candidates=[],
        feed_interest_payload={},
        feed_cue=SimpleNamespace(topic="Say hello."),
        prepared_create_post_brief="source: owner_feed_cue\nprimary_intent: Say hello.",
    )
    with_self_update = agent_runs._format_v6_action_menu_table(
        SqlAlchemyResidentActionReferences(None),
        character_id="char-1",
        allowed_actions=("post", "observe"),
        inbox_candidates=[],
        feed_interest_payload={},
        prepared_create_post_brief=(
            "source: self_update\n"
            "writing_mode: self_update_post\n"
            "basis: current_time_and_persona"
        ),
    )
    with_post_seed_without_interest = agent_runs._format_v6_action_menu_table(
        SqlAlchemyResidentActionReferences(None),
        character_id="char-1",
        allowed_actions=("post", "observe"),
        inbox_candidates=[],
        feed_interest_payload={
            "interests": [],
            "post_seed": "A warm public reaction.",
            "post_seed_intent": "public_reaction",
            "topic_signature": "warm public reaction topic",
            "novelty_basis": "new concrete detail",
        },
        prepared_create_post_brief=(
            "source: feed_scan\n"
            "writing_mode: community_theme_post\n"
            "primary_intent: A warm public reaction.\n"
            "primary_intent_type: public_reaction"
        ),
    )

    assert "angmoo_create_post_from_brief" not in without_brief
    assert "angmoo_create_post_from_brief" in with_owner_cue
    assert "angmoo_create_post_from_brief" in with_self_update
    assert agent_briefs.PREPARED_CREATE_POST_BRIEF_SENTINEL in with_self_update
    assert "source: self_update" in with_self_update
    assert "writing_mode: self_update_post" in with_self_update
    assert "angmoo_create_post_from_brief" not in with_post_seed_without_interest


def test_v6_action_menu_keeps_feed_actions_without_post_seed(monkeypatch):
    post = SimpleNamespace(
        id="post-1",
        author_user_id=None,
        author_character_id="char-2",
        title="quiet agreement",
        body="a post worth liking",
    )
    monkeypatch.setattr(context_references.post_repository, "get_post", lambda *args, **kwargs: post)
    monkeypatch.setattr(
        context_references.visibility,
        "is_post_public_context_visible",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(context_references.social_queries, "_has_character_like", lambda *args, **kwargs: False)
    monkeypatch.setattr(context_references.social_queries, "_has_character_repost", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        context_references.social_queries, "_has_character_replied_to_thread", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(
        context_references.social_queries,
        "_is_direct_reply_to_character_post_for_action_gate",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        agent_runs,
        "_profile_display_name_for_action_menu",
        lambda *args, **kwargs: "other bird",
    )

    menu = agent_runs._format_v6_action_menu_table(
        SqlAlchemyResidentActionReferences(None),
        character_id="char-1",
        allowed_actions=("like", "reply", "repost", "post"),
        inbox_candidates=[],
        feed_interest_payload={
            "interests": [
                {
                    "post_id": "post-1",
                    "summary": "quiet agreement",
                    "reason": "like and reply can fit",
                }
            ],
            "post_seed": "",
            "no_relevant_signal": False,
        },
        prepared_create_post_brief="",
    )

    assert "Feed candidate 1" in menu
    assert "angmoo_like_post" in menu
    assert "angmoo_reply_to_post_from_brief" in menu
    assert "angmoo_create_post_from_brief" not in menu
