import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.social.repository.topic_history import recent_own_root_posts
from app.domains.social.service import topic_metadata
from app.runtime.social.feed_history import RuntimeFeedHistoryReferences
from app.runtime.social.topic_metadata import RuntimeTopicHistoryReferences
from relationships.test_social_event_runtime import _engine, _seed, _post


def test_topic_history_preserves_attached_rows_column_precedence_and_rollback():
    engine = _engine()
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(
            db,
            post_id="topic-history-owned",
            author=fixture.actor,
            author_world_character=fixture.actor_world_character,
            body="A public reading note.",
        )
        post.created_at = now
        post.topic_signature = None
        post.novelty_basis = None
        foreign = _post(
            db,
            post_id="topic-history-foreign",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="Another person's note.",
        )
        foreign.created_at = now
        log = models.AgentActivityLog(
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            action_type="post_created",
            target_post_id=post.id,
            reason="fixture",
            result=json.dumps({"topic_signature": "persisted log topic"}),
            created_at=now,
        )
        db.add(log)
        db.commit()
        calls = []
        event.listen(engine, "before_cursor_execute", lambda *args: calls.append("sql"))
        event.listen(db, "before_commit", lambda *args: calls.append("commit"))
        history = RuntimeFeedHistoryReferences()
        references = RuntimeTopicHistoryReferences()
        assert calls == []
        rows = recent_own_root_posts(
            db,
            character_id=fixture.actor.id,
            cutoff=now - timedelta(hours=48),
            limit=20,
        )
        assert rows == [post]
        assert rows[0] is post
        assert history.get_post(db, post.id) is post
        assert (
            references.latest_creation_log(
                db, character_id=fixture.actor.id, post_id=post.id
            )
            is log
        )
        assert (
            topic_metadata.post_topic_signature_for_prompt(
                db, post, references=references
            )
            == "persisted log topic"
        )
        calls.clear()
        post.topic_signature = "pending column topic"
        assert (
            topic_metadata.post_topic_signature_for_prompt(
                db, post, references=references
            )
            == "pending column topic"
        )
        assert calls == []
        db.flush()
        db.rollback()
        assert post.topic_signature is None
        assert (
            topic_metadata.post_topic_signature_for_prompt(
                db, post, references=references
            )
            == "persisted log topic"
        )
        assert "commit" not in calls
