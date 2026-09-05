from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app import models
from app.core.unit_of_work import deferred_commits
from app.domains.social.schemas.community import PostCreate
from app.runtime.social.agent_tools import agent_tool_actions
from test_social_event_runtime import _engine, _seed


def test_tool_post_topic_and_success_log_share_caller_rollback():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        run = models.AgentRun(
            id="tool-action-contract",
            user_id=fixture.actor.owner_id,
            character_id=fixture.actor.id,
            agent_id="resident-contract",
            session_key="tool-action-contract-session",
            status="running",
        )
        db.add(run)
        db.commit()
        commits = []
        event.listen(db, "before_commit", lambda *args: commits.append("commit"))
        with deferred_commits():
            result = agent_tool_actions.create_agent_tool_post(
                db,
                run.session_key,
                PostCreate(
                    title="Shared transaction",
                    body="A public note prepared by the resident.",
                    author_character_id=fixture.actor.id,
                ),
                topic_signature="A new shared reading note",
                novelty_basis="The character connects two recent observations.",
                world_id=fixture.world.id,
                author_world_character_id=fixture.actor_world_character.id,
            )
            post = db.get(models.Post, result.id)
            assert post is not None
            assert post.author_character_id == fixture.actor.id
            assert post.world_id == fixture.world.id
            assert post.topic_signature == "A new shared reading note"
            logs = list(
                db.scalars(
                    select(models.AgentActivityLog).where(
                        models.AgentActivityLog.target_post_id == result.id
                    )
                )
            )
            assert len(logs) == 1
            assert logs[0].action_type == "post_created"
            assert logs[0].reason == "agent_tool_post"
            assert logs[0].character_id == run.character_id
            assert commits == []
        db.rollback()
        assert db.get(models.Post, result.id) is None
        assert (
            db.scalar(
                select(models.AgentActivityLog.id).where(
                    models.AgentActivityLog.target_post_id == result.id
                )
            )
            is None
        )
        assert db.get(models.AgentRun, run.id) is run
        assert commits == []
    engine.dispose()
