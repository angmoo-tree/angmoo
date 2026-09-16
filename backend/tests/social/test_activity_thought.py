import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.contracts.activity_thought import parse_activity_thought
from app.domains.social.models.activity_thought import SocialActivityThought
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext
from app.domains.social.schemas.feed import FeedReactionDecision
from app.domains.social.exceptions import SubjectiveContextPersistenceError
from app.runtime.social.subjective_composition import record_activity_thought
from app.runtime.social import feed_reaction_provider as provider_module
from app.runtime.social.world_feed_search import load_ready_search_profile, search_world_feed_candidates
from social.test_feed_reaction_intent import _engine, _seed
from test_p8_l_r_today_sns_activity import NOW, _seed_today_activity, today_session


def test_character_scrub_removes_private_thought_without_deleting_public_original(today_session):
    from app.runtime.world_characters.cleanup import delete_setup_data_for_characters
    from app.domains.social.models.posts import Post
    db, fixture = today_session
    execution, social_event = _seed_today_activity(db, fixture)
    SocialActivityThought.__table__.create(db.get_bind(), checkfirst=True)
    row = record_activity_thought(db, execution=execution, event=social_event,
        source_post_id="subject-root", thought=parse_activity_thought("사적인 생각"), captured_at=NOW)
    db.flush()
    row_id = row.id
    delete_setup_data_for_characters(db, character_ids=[fixture["subject"].character_id])
    db.flush()
    db.expire_all()
    assert db.get(SocialActivityThought, row_id) is None
    assert db.get(Post, "subject-root") is not None


@pytest.mark.parametrize("text_action", [False, True])
def test_social_thought_does_not_commit_and_links_own_source_or_action(today_session, text_action):
    db, fixture = today_session
    execution, social_event = _seed_today_activity(db, fixture)
    SocialActivityThought.__table__.create(db.get_bind(), checkfirst=True)
    legacy = db.scalar(select(SocialActionSubjectiveContext).where(SocialActionSubjectiveContext.social_event_id == social_event.id))
    legacy_digest = legacy.source_digest
    commits = []
    event.listen(db, "after_commit", lambda *_: commits.append(True))
    arguments = dict(execution=execution, event=social_event,
                     source_post_id="subject-root" if text_action else None,
                     thought=parse_activity_thought("친구와 나누고 싶다."), captured_at=NOW)
    row = record_activity_thought(db, **arguments)
    assert row.source_kind == ("post_revision" if text_action else "action_event")
    assert row.source_post_id == arguments["source_post_id"]
    assert record_activity_thought(db, **arguments).id == row.id
    with pytest.raises(SubjectiveContextPersistenceError, match="replay_conflict"):
        record_activity_thought(db, **(arguments | {"thought": parse_activity_thought("다른 초안")}))
    assert legacy.source_digest == legacy_digest
    row_id = row.id
    db.rollback()
    assert db.get(SocialActivityThought, row_id) is None
    assert commits == []


@pytest.mark.parametrize("thought", [None, 12, "생각" * 200])
def test_feed_thought_replaces_old_fields_and_uses_writer_call(monkeypatch, thought):
    engine = _engine()
    with Session(engine) as db:
        ctx, target = _seed(db, with_candidate=True)
        profile = load_ready_search_profile(db, world_character_id="world-character-actor")
        candidates = search_world_feed_candidates(
            db, profile=profile, keywords=profile.keywords[:2],
            allowed_policy_actions=ctx.activity_policy.allowed_actions, now=ctx.run_started_at,
            search_index=ctx.social_search_index, search_state=ctx.social_search_state,
        ).candidates
        calls = []
        async def generate(**kwargs):
            calls.append(kwargs)
            assert "motivation_kind" not in str(kwargs["response_schema"])
            assert "emotion_intensity" not in kwargs["user_prompt"]
            if len(calls) == 1:
                payload = dict(selected_candidate_index=0, selected_action="comment", interaction_intent="ordinary_comment",
                               comment_purpose="question", brief="기술이 궁금하다.", thought="중복 계획 생각")
            else:
                payload = dict(text="어떻게 배웠어?", source_post_id=candidates[0].post_id,
                               interaction_intent="ordinary_comment", comment_purpose="question", thought=thought)
            return kwargs["validator"](payload)
        monkeypatch.setattr(provider_module, "_api_key", lambda _: "fake")
        monkeypatch.setattr(provider_module, "generate_json", generate)
        provider = provider_module.DirectFeedReactionProvider(thought_enabled=True)
        tracker = provider_module.RunLlmTracker(max_calls=3)
        decision = asyncio.run(provider.plan(resident_context=ctx, profile=profile, candidates=candidates, tracker=tracker))
        draft = asyncio.run(provider.write_comment(resident_context=ctx, profile=profile, candidate=candidates[0], decision=decision, tracker=tracker))
        assert decision._activity_thought is None
        assert decision.motivation_kind is None
        assert draft.text == "어떻게 배웠어?"
        assert draft._activity_thought == parse_activity_thought(thought)
        assert len(calls) == 2
        assert "thought" not in draft.model_dump()
    engine.dispose()


def test_today_thought_view_replaces_legacy_and_invalidates_changed_source(today_session, monkeypatch):
    from app.config import settings
    from app.domains.social.models.posts import Post
    from test_p8_l_r_today_sns_activity import _snapshot
    db, fixture = today_session
    execution, social_event = _seed_today_activity(db, fixture)
    SocialActivityThought.__table__.create(db.get_bind(), checkfirst=True)
    monkeypatch.setattr(settings, "ACTIVITY_THOUGHT_POLICY", "thought_v1")
    text = "훈련 계획을 나누며 함께 준비하고 싶다." * 30
    row = record_activity_thought(db, execution=execution, event=social_event,
        source_post_id="subject-root", thought=parse_activity_thought(text), captured_at=NOW)
    db.flush()
    snapshot = _snapshot(db, fixture)
    assert snapshot.version.endswith(".v2")
    entry = next(e for e in snapshot.entries if e.source_id == social_event.id)
    assert entry.subjective_context is None
    assert entry.thought.text == text[:280]
    payload = entry.provider_payload(include_content=False)
    assert payload["thought_truncated"] is True
    assert payload["thought_excerpt_complete"] is False
    assert payload["thought_excerpt"] == text[:180]
    assert not {"motivation_kind", "emotion_label", "motivation_text"}.intersection(payload)
    assert snapshot.router_view()["version"].endswith(".v2")
    old_hash = snapshot.snapshot_hash
    from app.domains.memory.contracts.scope import MemoryScope
    from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
    scope = MemoryScope(fixture["owner"].id, fixture["world"].id, fixture["subject"].id)
    details = RuntimeEpisodeDetailReader(db)
    assert details.read_thoughts(scope=scope, references=(f"social:{row.id}",))[f"social:{row.id}"].text == text[:280]
    post = db.get(Post, "subject-root")
    post.body = "나중에 수정한 다른 내용"
    db.flush()
    updated = _snapshot(db, fixture)
    changed = next(e for e in updated.entries if e.source_id == social_event.id)
    assert updated.snapshot_hash != old_hash
    assert changed.thought.status == "invalid"
    assert changed.thought.text is None
    assert changed.subjective_context is None
    assert details.read_thoughts(scope=scope, references=(f"social:{row.id}",))[f"social:{row.id}"].status == "invalid"
    # Another actor's private record is never promoted to this character's view.
    row.actor_world_character_id = fixture["peer"].id
    db.flush()
    assert all(e.thought is None for e in _snapshot(db, fixture).entries)
