from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.unit_of_work import deferred_commits
from app.domains.routines import models
from app.domains.routines.exceptions import AgentRunConflictError
from app.domains.routines.repository import runs as run_queries, feed_cues as cue_queries
from app.domains.routines.repository import public_action_executions as execution_queries
from app.domains.routines.service import runs, feed_cues, public_action_executions
from app.domains.social.models.posts import Post
from routines.test_activity_persistence import _file_engine
from routine_posts.test_runtime import _seed


def _run(db, fixture):
    return runs.create_agent_run(
        db, run_id="persisted-run", user_id=fixture.user.id,
        character_id=fixture.character.id, post_id=None,
        credential_id=fixture.credential.id, agent_id="persisted-agent",
        session_key="agent:resident-manual:test", tool_auth_key="fixture-tool-key",
    )


def test_run_write_preserves_commit_conflict_rollback_and_finished_lookup(tmp_path):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = _run(db, fixture)
        assert run_queries.get_active_run_for_tool_auth_key(db, "fixture-tool-key") is run
        with Session(engine) as observer:
            assert observer.get(models.AgentRun, run.id).status == "running"
        original_name = fixture.character.name
        db.expunge(run)
        fixture.character.name = "not committed after duplicate conflict"
        with pytest.raises(AgentRunConflictError, match="An active agent run already exists") as caught:
            _run(db, fixture)
        assert isinstance(caught.value.__cause__, IntegrityError)
        assert fixture.character.name == original_name
        run = run_queries.get_latest_run_for_session(db, "agent:resident-manual:test")
        runs.mark_agent_run_finished(db, run.id, "succeeded", {"status": "succeeded"})
        assert run_queries.get_active_run_for_session(db, run.session_key) is None
        assert run_queries.get_latest_manual_run_for_user(db, fixture.user.id) is run
        with Session(engine) as observer:
            saved = observer.get(models.AgentRun, run.id)
            assert saved.gateway_result == {"status": "succeeded"}
            assert saved.completed_at is not None
    engine.dispose()


def test_public_execution_deferred_write_and_finish_share_caller_rollback(tmp_path):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = _run(db, fixture)
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        with deferred_commits():
            execution = public_action_executions.create_public_action_execution(
                db, run_id=run.id, character_id=fixture.character.id,
                signature="pending-public-signature", scope="feed", action_type="like",
                world_id=fixture.world.id, actor_world_character_id=fixture.world_character.id,
                interaction_intent="support", brief_hash="fixture-brief",
            )
            returned = public_action_executions.mark_public_action_execution_finished(
                db, execution, status="succeeded", result={"saved": True},
            )
            assert returned is execution
            assert execution_queries.get_public_action_execution_by_signature(
                db, "pending-public-signature",
            ) is execution
            assert execution.completed_at is not None
            assert execution.interaction_intent == "support"
            assert commits == []
            with Session(engine) as observer:
                assert execution_queries.get_public_action_execution_by_signature(
                    observer, "pending-public-signature",
                ) is None
        db.rollback()
        assert execution_queries.get_public_action_execution_by_signature(
            db, "pending-public-signature",
        ) is None
    engine.dispose()


def test_feed_cue_keeps_committed_creation_consumption_and_missing_no_write(tmp_path):
    engine = _file_engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        post = Post(
            id="cue-post", author_character_id=fixture.character.id,
            author_name=fixture.character.name, title="Cue post", body="Saved cue result",
        )
        db.add(post)
        db.commit()
        commits = []

        @event.listens_for(db, "after_commit")
        def committed(_session):
            commits.append(True)

        cue = feed_cues.create_feed_cue(
            db, user=fixture.user, character=fixture.character, topic="  Alchemy class  ",
        )
        assert cue.topic == "Alchemy class"
        assert cue_queries.get_pending_feed_cue(db, fixture.character.id) is cue
        assert commits == [True]
        result = feed_cues.mark_pending_feed_cue_used(
            db, character_id=fixture.character.id, run_id=None, post_id=post.id,
        )
        assert result is cue
        assert commits == [True, True]
        with Session(engine) as observer:
            saved = observer.get(models.AgentFeedCue, cue.id)
            assert saved.status == "used"
            assert saved.consumed_run_id is None
            assert saved.consumed_post_id == post.id
            assert saved.consumed_at is not None
        assert feed_cues.mark_pending_feed_cue_used(
            db, character_id=fixture.character.id, run_id=None, post_id=post.id,
        ) is None
        assert commits == [True, True]
    engine.dispose()
