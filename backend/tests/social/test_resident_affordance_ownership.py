from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.social.service.resident_affordances import (
    resident_feed_action_affordance,
)
from relationships.test_social_event_runtime import _engine, _seed, _post


def test_resident_affordance_sees_pending_like_in_same_session_and_preserves_rollback():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(
            db,
            post_id="resident-affordance-post",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="An invitation.",
        )
        db.commit()
        calls = []
        event.listen(engine, "before_cursor_execute", lambda *args: calls.append("sql"))
        event.listen(db, "before_commit", lambda *args: calls.append("commit"))
        disabled = resident_feed_action_affordance(
            db, post=post, character_id=fixture.actor.id, allowed_actions=()
        )
        assert calls == []
        assert disabled["available_actions"] == []
        assert disabled["blocked_actions"] == dict.fromkeys(
            ("like", "reply", "repost", "follow"), "policy_disabled"
        )
        assert resident_feed_action_affordance(
            db, post=post, character_id=fixture.actor.id, allowed_actions={"like"}
        )["available_actions"] == ["like"]
        like = models.PostLike(
            post_id=post.id,
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
        )
        db.add(like)
        offered = resident_feed_action_affordance(
            db, post=post, character_id=fixture.actor.id, allowed_actions={"like"}
        )
        assert offered["available_actions"] == []
        assert offered["blocked_actions"]["like"] == "already_liked"
        assert like.id is not None
        assert "commit" not in calls
        db.rollback()
        assert db.scalar(select(func.count(models.PostLike.id))) == 0
        assert resident_feed_action_affordance(
            db, post=post, character_id=fixture.actor.id, allowed_actions={"like"}
        )["available_actions"] == ["like"]
    engine.dispose()
