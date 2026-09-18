from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from social.test_world_feed_search import _engine, _user, _world, _add_world_character
from app.domains.social.models.posts import Post
from app.domains.social.models.topics import RecommendationPost, RecommendationPostTopic, RecommendationTopic
from app.domains.social.service.recommendation_topics import (
    TopicMatcher, available_topics, enroll_native_post, match_post, replace_source_topics,
    valid_final_signature,
)


@pytest.fixture
def scope():
    from app.runtime.social.topic_scope import configure
    configure()
    engine = _engine()
    with Session(engine) as db:
        owner = _user("owner")
        db.add(owner)
        db.flush()
        world = _world(owner)
        db.add(world)
        db.flush()
        _, character, wc = _add_world_character(db, world=world, suffix="actor")
        yield db, world, character, wc
    engine.dispose()


def post(db, world, character, wc, identity="new"):
    row = Post(id=identity, author_user_id=character.owner_id,
               author_character_id=character.id, world_id=world.id,
               author_world_character_id=wc.id, author_name="actor",
               title="승부차기", body="마지막 공을 막았다", created_at=datetime.now(UTC))
    db.add(row)
    db.flush()
    return row


def test_full_dictionary_before_six_link_limit():
    matcher = TopicMatcher([(f"id-{i}", f"항목{i:04}") for i in range(5000)] + [("football", "축구")])
    assert matcher.match(["축구전술 항목4999"]) == ["id-4999", "football"]
    assert len(matcher.match([" ".join(f"항목{i:04}" for i in range(100))])) == 6
    assert matcher.match(["축", "구"]) == []  # Never join field boundaries.


def test_world_and_other_character_union_reuse_and_retirement(scope):
    db, world, character, wc = scope
    football = replace_source_topics(db, world_id=world.id, world_character_id=None, topics=[("축구", "common")])[0]
    replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("축구", "common"), ("골키퍼", "common")])
    row = post(db, world, character, wc)
    enroll_native_post(db, row)
    assert match_post(db, row, final_signature="축구 골키퍼의 선방")
    replace_source_topics(db, world_id=world.id, world_character_id=None, topics=[])
    assert football in {t.id for t in available_topics(db, world.id)}
    wc.autonomous_enabled = False
    assert football in {t.id for t in available_topics(db, world.id)}
    replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[])
    assert not available_topics(db, world.id)
    assert db.get(RecommendationTopic, football)
    assert list(db.scalars(select(RecommendationPostTopic).where(RecommendationPostTopic.post_id == row.id)))
    assert replace_source_topics(db, world_id=world.id, world_character_id=None, topics=[("축구", "common")]) == [football]


def test_no_backfill_no_new_topic_and_edit_drops_signature(scope):
    db, world, character, wc = scope
    football = replace_source_topics(db, world_id=world.id, world_character_id=None, topics=[("축구", "common")])[0]
    old = post(db, world, character, wc, "old")
    assert match_post(db, old, final_signature="축구") == []
    assert db.get(RecommendationPost, old.id) is None
    new = post(db, world, character, wc)
    enroll_native_post(db, new)
    assert match_post(db, new, final_signature="축구 외계어") == [football]
    new.body = "오늘은 요리를 했다"
    assert match_post(db, new) == []
    assert db.get(RecommendationPost, new.id).final_signature is None
    assert len(list(db.scalars(select(RecommendationTopic)))) == 1
    assert match_post(db, new, final_signature={"topic": "축구"}) == []


def test_metadata_errors_do_not_become_text():
    from app.domains.routine_posts.schemas import RoutinePostDraft
    for value in [None, [], {}, 123, "x" * 301, " "]:
        assert valid_final_signature(value) is None
        draft = RoutinePostDraft(title="정상 글", body="본문은 보존", novelty_basis="새 관찰", topic_signature=value)
        assert draft.body == "본문은 보존" and draft.topic_signature == ""
    assert valid_final_signature(" 축구 ") == "축구"


def test_membership_and_deleted_character_invalidate_same_transaction_matcher(scope):
    from app.domains.worlds.models import WorldMembership
    db, world, character, wc = scope
    topic = replace_source_topics(db, world_id=world.id, world_character_id=wc.id, topics=[("축구", "world")])[0]
    row = post(db, world, character, wc); row.body = "축구전술"
    enroll_native_post(db, row)
    assert match_post(db, row) == [topic]
    character.deleted_at = datetime.now(UTC); db.flush()
    assert match_post(db, row) == []
    character.deleted_at = None; db.flush()
    assert match_post(db, row) == [topic]
    membership = db.get(WorldMembership, wc.membership_id)
    membership.status = "left"; db.flush()
    assert match_post(db, row) == []
