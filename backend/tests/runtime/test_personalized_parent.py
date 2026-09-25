import asyncio
from datetime import UTC, datetime, timedelta
from sqlalchemy.orm import Session
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.routines.models import AgentSlot
from app.domains.world_characters.service.activity_engines import bind_run, set_engine
from app.runtime.autonomous_activity.binding import ActivityRuntimeBinding, register, unregister
from app.runtime.autonomous_activity.execution import run_personalized_activity
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.planner_contract import parse_action
from social.test_feed_reaction_intent import _engine, _seed


def test_parent_real_adapters_respect_slot_and_commit_single_feed_effect(monkeypatch, tmp_path):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)))
            set_engine(db, engine="personalized_graph_v2", expected_version=0)
            run = bind_run(db, actor=actor, activity_id=ctx.run_id); db.commit()
            async def plan(self, **kwargs):
                kwargs["delivery"].dispatched(); kwargs["delivery"].delivered()
                return {**parse_action({"decisions": [{"target_id": post.id, "action": "like", "brief": "Useful discovery"}]}, kwargs["candidates"]), "judged_at": datetime.now(UTC).isoformat()}
            monkeypatch.setattr(ActivityProvider, "plan", plan)
            binding = ActivityRuntimeBinding(None, tmp_path)
            register(binding)
            try:
                result = await run_personalized_activity(ctx, actor=actor, run=run)
                assert result["publish_result"]["public_action_count"] == 1
                assert result["paths"]["feed"]["status"] == "completed"
                repeated = await run_personalized_activity(ctx, actor=actor, run=run)
                assert repeated == result
            finally:
                unregister(binding)
    asyncio.run(scenario())


def test_parent_preserves_completed_paths_and_resumes_busy_settlement(monkeypatch, tmp_path):
    import sqlite3
    import pytest
    from sqlalchemy.exc import OperationalError
    from app.runtime.autonomous_activity.feed import FeedLane
    from app.domains.world_characters.service.activity_status import activity_status
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)))
            set_engine(db, engine="personalized_graph_v2", expected_version=0)
            run = bind_run(db, actor=actor, activity_id=ctx.run_id); db.commit()
            calls = []
            async def plan(self, **kwargs):
                calls.append("plan")
                kwargs["delivery"].dispatched(); kwargs["delivery"].delivered()
                return {**parse_action({"decisions": [{"target_id": post.id, "action": "like", "brief": "Useful discovery"}]}, kwargs["candidates"]), "judged_at": datetime.now(UTC).isoformat()}
            original = FeedLane.settle
            async def busy_once(self, state):
                calls.append("settle")
                if calls.count("settle") == 1:
                    raise OperationalError("update", {}, sqlite3.OperationalError("database is locked"))
                return await original(self, state)
            monkeypatch.setattr(ActivityProvider, "plan", plan)
            monkeypatch.setattr(FeedLane, "settle", busy_once)
            binding = ActivityRuntimeBinding(None, tmp_path); register(binding)
            try:
                with pytest.raises(OperationalError):
                    await run_personalized_activity(ctx, actor=actor, run=run)
                assert run.status == "waiting"
                assert set(run.result["paths"]) == {"inbox", "routine"}
                result = await run_personalized_activity(ctx, actor=actor, run=run)
                assert result["publish_result"]["public_action_count"] == 1
                assert calls == ["plan", "settle", "settle"]
                assert run.status == "completed"
                assert "state_status" in activity_status(db, actor=actor)["runs"][0]["paths"]["feed"]
            finally:
                unregister(binding)
    asyncio.run(scenario())


def test_inbox_planner_final_failure_preserves_feed_effect_and_pending_notification(monkeypatch, tmp_path):
    from sqlalchemy import func, select
    from app.domains.social.models.posts import Notification, PostLike
    from app.integrations.direct_llm import DirectLlmJsonError

    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            ctx, post = _seed(db, with_candidate=True)
            actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
            notification = Notification(
                id=4401, world_id=actor.world_id, recipient_world_character_id=actor.id,
                recipient_character_id=actor.character_id,
                actor_world_character_id=post.author_world_character_id,
                actor_character_id=post.author_character_id, notification_type="mention",
                post_id=post.id, source_post_id=post.id)
            db.add(notification)
            db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)))
            set_engine(db, engine="personalized_graph_v2", expected_version=0)
            run = bind_run(db, actor=actor, activity_id=ctx.run_id)
            db.commit()
            async def select_target(self, **kwargs):
                return {"selections": [{"target_id": kwargs["candidates"][0]["target_id"],
                                         "memory_query": "relevant experience"}]}
            async def plan(self, **kwargs):
                if kwargs["lane"] == "inbox":
                    raise DirectLlmJsonError(
                        "direct LLM JSON parse failed", failure_class="json_parse_failed",
                        parse_error_type="StructuredOutputValidationError", attempt_count=2,
                        validation_code="action_brief_missing",
                        field_path="decisions.0.brief")
                kwargs["delivery"].dispatched()
                kwargs["delivery"].delivered()
                return {**parse_action({"decisions": [{
                    "target_id": post.id, "action": "like", "brief": "Useful discovery"}]},
                    kwargs["candidates"]), "judged_at": datetime.now(UTC).isoformat()}
            monkeypatch.setattr(ActivityProvider, "select", select_target)
            monkeypatch.setattr(ActivityProvider, "plan", plan)
            binding = ActivityRuntimeBinding(None, tmp_path)
            register(binding)
            try:
                result = await run_personalized_activity(ctx, actor=actor, run=run)
            finally:
                unregister(binding)
            assert result["status"] == "failed"
            assert result["paths"]["inbox"]["status"] == "failed"
            assert result["paths"]["feed"]["status"] == "completed"
            assert result["publish_result"]["public_action_count"] == 1
            assert db.scalar(select(func.count(PostLike.id))) == 1
            db.refresh(notification)
            assert notification.handled_at is None
    asyncio.run(scenario())
