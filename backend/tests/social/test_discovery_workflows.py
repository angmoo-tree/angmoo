from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models  # Complete registration precedes the fixture's partial DDL.
from app.domains.characters.service import search as character_search
from app.domains.social.repository import posts as post_repository
from app.domains.social.service import feed
from app.runtime.social.discovery import discovery_reads, discovery_service


@pytest.fixture
def discovery_session():
    engine = create_engine("sqlite://")
    for model in (models.User, models.Character, models.Post, models.AgentActivityLog, models.Comment, models.PostMedia, models.PostLike, models.PostRepost, models.PostReport):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = models.User(id="owner", email="owner@example.invalid", display_name="Owner", display_name_normalized="owner")
        literal = models.Character(id="literal", owner_id=owner.id, name="Value 100%", handle="value_100", persona_summary="synthetic")
        broad = models.Character(id="broad", owner_id=owner.id, name="Value 100x", handle="broad", persona_summary="synthetic")
        deleted = models.Character(id="deleted", owner_id=owner.id, name="Value 100% deleted", handle="deleted", persona_summary="synthetic", deleted_at=datetime(2026, 9, 5, tzinfo=UTC))
        db.add_all([owner, literal, broad, deleted])
        db.commit()
        yield db, owner, literal, broad, deleted
    engine.dispose()


def test_discovery_keeps_literal_like_escape_join_scope_and_empty_query(discovery_session):
    db, owner, literal, broad, deleted = discovery_session
    at = datetime(2026, 9, 5, 16, tzinfo=UTC)
    posts = [
        models.Post(id="literal-post", author_name=literal.name, author_character_id=literal.id, title="Budget 100%", body="synthetic", visibility="public", created_at=at),
        models.Post(id="broad-post", author_name=broad.name, author_character_id=broad.id, title="Budget 100x", body="synthetic", visibility="public", created_at=at),
        models.Post(id="private-post", author_name=literal.name, author_character_id=literal.id, title="Budget 100%", body="synthetic", visibility="private", created_at=at),
        models.Post(id="hidden-post", author_name=literal.name, author_character_id=literal.id, title="Budget 100%", body="synthetic", visibility="public", report_hidden_at=at, created_at=at),
    ]
    db.add_all(posts)
    db.commit()
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    empty = discovery_service.search_nest(db, query="  ")
    assert empty.query == "" and empty.posts == [] and empty.characters == []
    assert statements == []
    found, cursor = discovery_reads.search_posts(db, "100%", limit=10)
    assert found == [posts[0]] and cursor is None
    assert len(statements) == 1 and "LEFT OUTER JOIN characters" in statements[0]
    characters, next_offset = character_search.search_characters(db, "100%", limit=10)
    assert characters == [literal] and next_offset is None
    handles, _ = character_search.search_characters(db, "@value_100", limit=10)
    assert handles == [literal]
    result = discovery_service.search_nest(db, query=" 100% ")
    assert result.query == "100%"
    assert [item.id for item in result.posts] == [posts[0].id]
    assert [item.id for item in result.characters] == [literal.id]


def test_today_activity_keeps_kst_cutoff_single_query_and_score_tie_order(discovery_session, monkeypatch):
    db, owner, literal, broad, deleted = discovery_session
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 5, 15, 30, tzinfo=UTC).astimezone(tz)
    monkeypatch.setattr(feed, "datetime", FrozenDateTime)
    cutoff = datetime(2026, 9, 5, 15, tzinfo=UTC)
    assert feed._today_start_utc() == cutoff
    literal.name, broad.name = "Alpha", "Beta"
    rows = []
    for character, actions in [(literal, ["post_created", "replied", "liked", "feed_viewed"]), (broad, ["commented", "commented", "liked", "liked"]), (deleted, ["observed"])]:
        rows.extend(models.AgentActivityLog(user_id=owner.id, character_id=character.id, action_type=action, created_at=cutoff, reason="synthetic", result="synthetic") for action in actions)
    rows.append(models.AgentActivityLog(user_id=owner.id, character_id=broad.id, action_type="post_created", created_at=cutoff-timedelta(microseconds=1), reason="synthetic", result="synthetic"))
    db.add_all(rows)
    db.commit()
    statements, commits = [], []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    event.listen(db, "before_commit", lambda *args: commits.append("commit"))
    ranked = discovery_service.list_today_activity(db, limit=50)
    assert [(item.character_id, item.score) for item in ranked] == [(literal.id, 6), (broad.id, 6)]
    assert (ranked[0].post_count, ranked[0].reply_count, ranked[0].like_count) == (1, 1, 1)
    assert (ranked[1].post_count, ranked[1].reply_count, ranked[1].like_count) == (0, 2, 2)
    assert len(statements) == 1 and "JOIN agent_activity_logs" in statements[0]
    assert commits == []
    assert [item.character_id for item in discovery_service.list_today_activity(db, limit=0)] == [literal.id]


def test_today_root_query_keeps_original_cutoff_visibility_and_order(discovery_session):
    db, owner, literal, broad, deleted = discovery_session
    cutoff = datetime(2026, 9, 5, 15, tzinfo=UTC)
    rows = [
        models.Post(id="a", author_name="A", title="A", body="synthetic", created_at=cutoff),
        models.Post(id="b", author_name="B", title="B", body="synthetic", created_at=cutoff),
        models.Post(id="old", author_name="Old", title="Old", body="synthetic", created_at=cutoff-timedelta(microseconds=1)),
        models.Post(id="reply", author_name="Reply", title="Reply", body="synthetic", reply_to_post_id="a", created_at=cutoff),
        models.Post(id="hidden", author_name="Hidden", title="Hidden", body="synthetic", report_hidden_at=cutoff, created_at=cutoff),
        models.Post(id="deleted", author_name="Deleted", title="Deleted", body="synthetic", deleted_at=cutoff, created_at=cutoff),
    ]
    db.add_all(rows)
    db.commit()
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    selected = post_repository.list_today_root_posts(db, day_start=cutoff)
    assert selected == rows[:2]
    assert len(statements) == 1
