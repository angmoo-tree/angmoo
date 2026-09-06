from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.social.exceptions import LangGraphSocialApplyError
from app.domains.social.service import action_notifications, action_sources
from app.runtime.social.action_scope import RuntimeActionScopeReferences
from relationships.test_social_event_runtime import _engine, _seed, _post


def test_no_action_keeps_original_scope_checks_and_caller_rollback():
    engine = _engine()
    now = datetime(2026, 8, 11, 3, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(
            db,
            post_id="notification-owner-post",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="A quiet moment.",
        )
        db.add(
            models.CharacterActiveWorld(
                character_id=fixture.actor.id,
                world_character_id=fixture.actor_world_character.id,
                selected_at=now,
                idempotency_key="notification-owner-active",
                version=1,
            )
        )
        notification = models.Notification(
            recipient_character_id=fixture.actor.id,
            actor_character_id=fixture.target.id,
            notification_type="reply",
            post_id=post.id,
            source_post_id=post.id,
        )
        db.add(notification)
        db.commit()
        db.expunge_all()
        calls = []
        event.listen(engine, "before_cursor_execute", lambda *args: calls.append("sql"))
        event.listen(db, "before_commit", lambda *args: calls.append("commit"))
        references = RuntimeActionScopeReferences(db)
        assert references.db is db
        assert calls == []
        with pytest.raises(
            LangGraphSocialApplyError, match="notification_no_action_outcome_invalid"
        ):
            action_notifications.mark_notification_handled_without_public_action(
                db,
                references=references,
                actor_character_id=fixture.actor.id,
                notification_id=notification.id,
                handling_outcome="failed",
                occurred_at=now,
            )
        assert calls == []
        result = action_notifications.mark_notification_handled_without_public_action(
            db,
            references=references,
            actor_character_id=fixture.actor.id,
            notification_id=notification.id,
            handling_outcome="LLM_DECIDED_NO_ACTION",
            occurred_at=now,
        )
        assert result is db.get(models.Notification, notification.id)
        assert result.handling_outcome == "LLM_DECIDED_NO_ACTION"
        assert result.actor_world_character_id == fixture.target_world_character.id
        assert "commit" not in calls
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        db.rollback()
        assert db.get(models.Notification, notification.id).handled_at is None
    engine.dispose()


def test_action_sources_preserve_pending_reaction_scope_without_committing():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = _post(
            db,
            post_id="reaction-owner-post",
            author=fixture.target,
            author_world_character=fixture.target_world_character,
            body="An observation.",
        )
        like = models.PostLike(
            post_id=post.id,
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
        )
        db.add(like)
        db.commit()
        changes = []
        event.listen(db, "before_flush", lambda *args: changes.append("flush"))
        event.listen(db, "before_commit", lambda *args: changes.append("commit"))
        source = action_sources._source_evidence(
            db,
            references=RuntimeActionScopeReferences(db),
            action_type="like",
            actor=fixture.actor_world_character,
            target=fixture.target_world_character,
            target_post=post,
            action_result={},
            execution=None,
        )
        assert source == (like, "like", "post_like", str(like.id), None)
        assert (
            like.world_id,
            like.actor_world_character_id,
            like.target_world_character_id,
        ) == (
            fixture.world.id,
            fixture.actor_world_character.id,
            fixture.target_world_character.id,
        )
        assert changes == []
        db.flush()
        assert changes == ["flush"]
        db.rollback()
        assert db.get(models.PostLike, like.id).world_id is None
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 0
        assert "commit" not in changes
    engine.dispose()
