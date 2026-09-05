from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models  # Complete ORM registration before partial fixture DDL.
from app.domains.social.exceptions import CharacterNotFoundError
from app.runtime.social.profile_activity import profile_activity_service


@pytest.fixture
def activity_session():
    engine = create_engine("sqlite://")
    for model in (models.User, models.Character, models.CharacterState, models.Post, models.Comment, models.AgentActivityLog):
        model.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = models.User(id="owner", email="owner@example.invalid", display_name="Owner", display_name_normalized="owner")
        character = models.Character(id="character", owner_id=owner.id, name="Character", handle="character", persona_summary="Public persona", personality="SYNTHETIC-PRIVATE-STATE")
        state = models.CharacterState(character_id=character.id, mood="calm", summary="Public state", memory_note="SYNTHETIC-PRIVATE-STATE")
        post = models.Post(id="post", author_name="Author", title="Title", body="Public post")
        db.add_all([owner, character, state, post])
        db.commit()
        yield db, owner, character, post
    engine.dispose()


def test_profile_activity_keeps_read_order_safe_projection_and_log_dedupe(activity_session):
    db, owner, character, post = activity_session
    at = datetime(2026, 9, 6, tzinfo=UTC)
    comments = [models.Comment(post_id=post.id, author_character_id=character.id, content=f"Comment {i}", created_at=at) for i in range(22)]
    logs = [models.AgentActivityLog(user_id=owner.id, character_id=character.id, action_type=action, reason="SYNTHETIC-PRIVATE-STATE", result="SYNTHETIC-PRIVATE-STATE", created_at=at+timedelta(seconds=i)) for i, action in enumerate(["like", "state_saved", "state_saved", "local_key_issued", "feed_viewed", "unknown_private_action"])]
    db.add_all([*comments, *logs])
    db.commit()
    # Force the original lazy state read instead of an identity-map hit.
    db.expunge(db.get(models.CharacterState, character.id))
    db.expire(character, ["state"])
    statements, commits = [], []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    event.listen(db, "before_commit", lambda *args: commits.append("commit"))
    result = profile_activity_service.get_character_activity(db, character.id)
    assert [item.id for item in result.recent_comments] == [item.id for item in reversed(comments[-20:])]
    assert [item.action_type for item in result.recent_agent_activity] == ["activity_updated", "state_saved", "liked"]
    assert [item.id for item in result.recent_agent_activity] == [logs[5].id, logs[2].id, logs[0].id]
    assert len(statements) == 3
    assert "FROM comments" in statements[0]
    assert "FROM character_states" in statements[1]
    assert "FROM agent_activity_logs" in statements[2]
    payload = result.model_dump(mode="json")
    assert "SYNTHETIC-PRIVATE-STATE" not in str(payload)
    assert "owner_id" not in payload["character"] and "personality" not in payload["character"]
    assert "memory_note" not in payload["state"]
    assert all("reason" not in item and "result" not in item for item in payload["recent_agent_activity"])
    assert commits == []


def test_profile_activity_rejects_missing_or_deleted_before_activity_queries(activity_session):
    db, owner, character, post = activity_session
    character.deleted_at = datetime(2026, 9, 6, tzinfo=UTC)
    db.commit()
    statements = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    for character_id in [character.id, "missing"]:
        with pytest.raises(CharacterNotFoundError):
            profile_activity_service.get_character_activity(db, character_id)
    assert not any("FROM comments" in statement or "FROM character_states" in statement or "FROM agent_activity_logs" in statement for statement in statements)
