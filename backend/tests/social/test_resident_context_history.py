from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.social.models import posts as models
from app.domains.social.repository import resident_context as queries
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine, _post


def test_resident_notification_queries_keep_limits_and_pending_read_state(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        now = datetime.now(UTC)
        rows = [models.Notification(
            recipient_character_id=actor, notification_type="reply", created_at=now,
        ) for _ in range(35)]
        other_type = models.Notification(
            recipient_character_id=actor, notification_type="like", created_at=now,
        )
        other_owner = models.Notification(
            recipient_user_id=fixture.user.id, notification_type="reply", created_at=now,
        )
        db.add_all([*rows, other_type, other_owner])
        db.commit()
        expected = sorted((row.id for row in rows), reverse=True)
        assert [row.id for row in queries.list_unread_reply_notifications(db, character_id=actor, limit=30)] == expected[:30]
        assert [row.id for row in queries.list_unread_reply_notifications(db, character_id=actor, limit=20)] == expected[:20]
        rows[-1].read_at = now
        assert rows[-1].id not in [row.id for row in queries.list_unread_reply_notifications(db, character_id=actor, limit=30)]
        # Review lookup intentionally permits an already-read reply; unread filtering
        # belongs only to the two list consumers in the original implementation.
        assert queries.find_review_notification(db, notification_id=rows[-1].id, character_id=actor) is rows[-1]
        assert queries.find_review_notification(db, notification_id=other_type.id, character_id=actor) is None
        assert queries.find_review_notification(db, notification_id=other_owner.id, character_id=actor) is None
        with Session(engine) as observer:
            assert queries.list_unread_reply_notifications(observer, character_id=actor, limit=1)[0].id == rows[-1].id
        db.rollback()
        assert queries.list_unread_reply_notifications(db, character_id=actor, limit=1)[0] is rows[-1]
    engine.dispose()


def test_resident_post_history_keeps_filters_order_limits_and_root_cycle(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = fixture.character.id
        now = datetime.now(UTC)
        root = _post("root", actor)
        root.created_at = now - timedelta(days=10)
        db.add(root)
        db.flush()
        rows = [_post(f"reply-{index:03}", actor, parent_id=root.id) for index in range(202)]
        for row in rows:
            row.created_at = now
        hidden = _post("hidden", actor, parent_id=root.id, hidden=True)
        deleted = _post("deleted", actor, parent_id=root.id, deleted=True)
        hidden.created_at = deleted.created_at = now
        db.add_all([*rows, hidden, deleted])
        db.commit()
        assert [row.id for row in queries.list_recent_own_posts(db, character_id=actor)] == [row.id for row in rows[:8]]
        assert [row.id for row in queries.list_recent_followed_posts(db, target_id=actor, since=now - timedelta(days=3))] == [row.id for row in rows[:5]]
        assert [row.id for row in queries.list_recent_reply_posts(db, since=now - timedelta(days=3))] == [row.id for row in reversed(rows[2:])]
        assert queries.list_recent_own_posts(db, character_id="absent-character") == []
        assert queries._thread_root_post_id_for_prompt(db, rows[0].id) == root.id
        root.reply_to_post_id = rows[0].id
        db.flush()
        assert queries._thread_root_post_id_for_prompt(db, rows[0].id) is None
        with Session(engine) as observer:
            assert queries._thread_root_post_id_for_prompt(observer, rows[0].id) == root.id
        db.rollback()
        assert queries._thread_root_post_id_for_prompt(db, rows[0].id) == root.id
    engine.dispose()
