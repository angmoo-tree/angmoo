from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app import models
from app.core.unit_of_work import deferred_commits
from app.domains.routines.repository.feed_history import find_thread_viewed_log_id
from app.domains.social.exceptions import AgentRunAuthorizationError
from app.domains.social.repository.inbox import list_unread_reply_notifications
from app.domains.social.schemas.community import AgentCompleteTickCreate
from app.runtime.social.complete_tick import agent_tool_tick
from test_social_event_runtime import _engine, _seed


def test_complete_tick_prevalidates_all_actions_and_shares_caller_rollback():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = models.AgentRun(
            id="tick-contract",
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            agent_id="resident-contract",
            session_key="tick-contract-session",
            status="running",
        )
        post = models.Post(
            id="tick-target",
            author_character_id=fixture.target.id,
            author_name=fixture.target.name,
            title="A shared observation",
            body="A valid visible target",
            world_id=fixture.world.id,
            author_world_character_id=fixture.target_world_character.id,
        )
        db.add_all([run, post])
        db.commit()
        commits = []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))
        payload = {
            "actions": [{"action_type": "like", "post_id": post.id}] * 2,
            "state": {"summary": "Remember this", "memory_note": "A fresh observation"},
            "selection_reason": "The public note is relevant.",
        }
        with deferred_commits():
            with pytest.raises(AgentRunAuthorizationError, match="like is duplicated"):
                agent_tool_tick.complete_agent_tool_tick(
                    db, run.session_key, AgentCompleteTickCreate(**payload)
                )
            assert list(db.scalars(select(models.PostLike))) == []
            assert db.get(models.CharacterState, fixture.actor.id) is None
            assert (
                db.scalar(select(models.AgentActivityLog.action_type))
                == "complete_tick_rejected"
            )
            assert commits == []
        db.rollback()
        payload["actions"] = payload["actions"][:1]
        with deferred_commits():
            result = agent_tool_tick.complete_agent_tool_tick(
                db, run.session_key, AgentCompleteTickCreate(**payload)
            )
            assert result.executed_actions == [f"like:{post.id}"]
            assert result.state.memory_note == "A fresh observation"
            assert db.scalar(select(models.PostLike.character_id)) == fixture.actor.id
            actions = list(db.scalars(select(models.AgentActivityLog.action_type)))
            assert set(actions) == {"liked", "state_saved", "tick_completed"}
            assert commits == []
        db.rollback()
        assert list(db.scalars(select(models.PostLike))) == []
        assert list(db.scalars(select(models.AgentActivityLog))) == []
        assert db.get(models.CharacterState, fixture.actor.id) is None
        assert commits == []
    engine.dispose()


def test_tick_evidence_queries_keep_scope_order_pending_rows_and_rollback():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        cutoff = datetime(2026, 9, 6, 1, 0, tzinfo=UTC)
        post = models.Post(
            id="tick-evidence-root", author_name="Target", title="Root", body="Visible"
        )
        db.add(post)
        db.commit()
        for char_id, action, created in [
            (fixture.actor.id, "thread_viewed", cutoff - timedelta(seconds=1)),
            (fixture.target.id, "thread_viewed", cutoff),
            (fixture.actor.id, "profile_viewed", cutoff),
        ]:
            db.add(
                models.AgentActivityLog(
                    user_id=fixture.actor.owner_id,
                    character_id=char_id,
                    action_type=action,
                    target_post_id=post.id,
                    reason="test",
                    result="bounded",
                    created_at=created,
                )
            )
        db.commit()
        args = dict(
            character_id=fixture.actor.id, root_post_id=post.id, created_at=cutoff
        )
        assert find_thread_viewed_log_id(db, **args) is None
        evidence = models.AgentActivityLog(
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            action_type="thread_viewed",
            target_post_id=post.id,
            reason="test",
            result="bounded",
            created_at=cutoff,
        )
        db.add(evidence)
        assert find_thread_viewed_log_id(db, **args) == evidence.id
        assert db.get(models.AgentActivityLog, evidence.id) is evidence
        notifications = [
            models.Notification(
                recipient_character_id=fixture.actor.id,
                actor_character_id=fixture.target.id,
                notification_type="reply",
                created_at=cutoff + timedelta(seconds=index),
            )
            for index in range(32)
        ]
        db.add_all(notifications)
        found = list_unread_reply_notifications(db, character_id=fixture.actor.id)
        assert found == list(reversed(notifications))[:30]
        found[0].read_at = cutoff
        assert (
            list_unread_reply_notifications(db, character_id=fixture.actor.id)
            == list(reversed(notifications[:-1]))[:30]
        )
        assert list_unread_reply_notifications(db, character_id=fixture.target.id) == []
        db.rollback()
        assert find_thread_viewed_log_id(db, **args) is None
        assert list_unread_reply_notifications(db, character_id=fixture.actor.id) == []
    engine.dispose()
