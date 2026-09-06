import asyncio

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from tests.model_fixture_support import models
from app.domains.social.schemas.feed import FeedReactionDecision
from app.domains.social.service import feed_cycle
from app.runtime.social.feed_cycle import RuntimeWorldFeedWorkflows
from app.runtime.social import world_feed_actions
from social.test_feed_reaction_intent import FakeFeedProvider, _engine, _seed


def test_failed_public_effect_rolls_back_execution_but_keeps_durable_observation():
    engine = _engine()
    with Session(engine, expire_on_commit=False) as db:
        context, target = _seed(db, with_candidate=True)
        calls = []
        event.listen(engine, "before_cursor_execute", lambda *args: calls.append("sql"))
        event.listen(db, "before_commit", lambda *args: calls.append("commit"))
        workflows = RuntimeWorldFeedWorkflows()
        assert calls == []
        active = workflows.active_world(db, context.character.id)
        assert active is db.get(models.CharacterActiveWorld, context.character.id)
        assert "commit" not in calls
        provider = FakeFeedProvider(
            FeedReactionDecision(
                selected_candidate_index=0,
                selected_action="like",
                reason_code=None,
                brief="Acknowledge the author's useful note.",
            )
        )
        failed_effects = []

        class FailingAction:
            @staticmethod
            def apply_successful_world_feed_action(session, **kwargs):
                assert session is db
                applied = world_feed_actions.apply_successful_world_feed_action(
                    session, **kwargs
                )
                failed_effects.append(applied.event.id)
                raise RuntimeError("fail after the source and event were flushed")

        workflows.social_apply = FailingAction()
        result = asyncio.run(
            feed_cycle.run_world_keyword_feed(
                context, workflows=workflows, provider=provider
            )
        )

        assert result["feed_outcome"] == "public_action_failed"
        assert result["failure_class"] == "RuntimeError"
        assert result["publish_result"] == {"public_action_count": 0}
        assert provider.plan_calls == 1
        assert provider.writer_calls == 0
        assert len(failed_effects) == 1
        assert db.get(models.SocialEvent, failed_effects[0]) is None
        assert db.scalar(select(func.count(models.PostLike.id))) == 0
        assert db.scalar(select(func.count(models.AgentPublicActionExecution.id))) == 0
        assert db.scalar(select(func.count(models.SocialEvent.id))) == 1
        assert db.scalar(select(func.count(models.Post.id))) == 1
        observation = db.scalar(select(models.WorldCharacterFeedObservation))
        assert observation is not None
        assert observation.post_id == target.id
        assert observation.status == "retryable_failed"
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 1
        db.rollback()
        assert db.get(models.WorldCharacterFeedObservation, observation.id) is not None
