"""PostgreSQL checkpoint recovery after a cancelled pure selector request."""
import asyncio
from datetime import UTC, datetime

import pytest
from psycopg.errors import SerializationFailure
from sqlalchemy import event, select, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.domains.social.models.posts import Post, PostLike
from app.domains.social.models.topics import RecommendationDelivery
from app.runtime.autonomous_activity import binding
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity.execution import run_personalized_activity
from app.runtime.autonomous_activity.planner_contract import parse_action
from app.runtime.autonomous_activity.provider import ActivityProvider
from postgresql.test_activity_transactions import store, seed, execute
from runtime.test_feed_selection_recovery import interrupted


@pytest.fixture
def process_graph(store, monkeypatch):
    """Match the in-process runtime's graph lifetime, using a real isolated DB.

    Opening and collecting a native graph for every query tested a different
    lifecycle and consumed the DB deadline before selector admission. Keep all
    canonical checks; only the projector-owned connection lifetime is shared.
    """
    from app.config import settings
    from app.integrations.ladybug_projection import LadybugRelationshipProjection
    from app.runtime.graph_projection.process_client import register_process_graph_client, unregister_process_graph_client
    monkeypatch.setattr(settings, 'LOCAL_RUNTIME_COMPONENT_MODE', 'in_process')
    monkeypatch.setattr(settings, 'LADYBUG_DATABASE_ROOT', str(store[2] / 'graph'))
    client = LadybugRelationshipProjection(database_root=settings.ladybug_database_root)
    register_process_graph_client(client)
    try:
        yield client
    finally:
        unregister_process_graph_client(client)
        client.close()


def test_cancelled_selector_resumes_from_postgres_checkpoint_without_duplicate_effect(store, monkeypatch, process_graph):
    engine, checkpoint, root = store
    async def scenario():
        with Session(engine, expire_on_commit=False) as db:
            ctx, post, actor, run = seed(db)
            second = Post(**{column.name: getattr(post, column.name)
                             for column in Post.__table__.columns if column.name != "id"}, id="second-post")
            db.add(second)
            db.commit()
            calls = []
            submitted = asyncio.Event()
            async def call(self, **kwargs):
                assert kwargs["node"] == "FeedTargetSelector"
                if kwargs.get("before_admitted_request"):
                    kwargs["before_admitted_request"]()
                delivery = kwargs["delivery"]
                delivery.dispatched()
                calls.append("selection")
                if len(calls) == 1:
                    submitted.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        delivery.uncertain()
                delivery.delivered()
                return kwargs["validator"]({"selections": [
                    {"target_id": kwargs["payload"]["candidates"][0]["target_id"], "memory_query": None}]})
            async def plan(self, **kwargs):
                calls.append("plan")
                kwargs["delivery"].dispatched()
                kwargs["delivery"].delivered()
                return {**parse_action({"decisions": [{"target_id": kwargs["candidates"][0]["target_id"],
                    "action": "like", "brief": "Useful discovery"}]}, kwargs["candidates"]),
                    "judged_at": datetime.now(UTC).isoformat(), "provisional_draft": {"replies": []}}
            monkeypatch.setattr(ActivityProvider, "call", call)
            monkeypatch.setattr(ActivityProvider, "plan", plan)
            runtime = binding.ActivityRuntimeBinding(None, root)
            binding.register(runtime)
            try:
                task = asyncio.create_task(run_personalized_activity(ctx, actor=actor, run=run))
                waiting = asyncio.create_task(submitted.wait())
                done, _ = await asyncio.wait((waiting, task), timeout=20, return_when=asyncio.FIRST_COMPLETED)
                if task in done:
                    waiting.cancel()
                    pytest.fail(f"activity finished before selector admission: {task.result()}")
                assert waiting in done, 'selector did not reach its admission boundary'
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                row = db.scalar(select(RecommendationDelivery))
                assert row.state == "uncertain"
                assert db.scalar(select(func.count(PostLike.id))) == 0
                normal = list(run.result["normal_reservations"])
                result = await run_personalized_activity(ctx, actor=actor, run=run)
                assert result["status"] == "completed", result
                assert result["publish_result"]["public_action_count"] == 1
                assert calls == ["selection", "selection", "plan"]
                db.refresh(run);db.refresh(row)
                assert run.result["normal_reservations"] == normal
                assert len(run.result["recovery_reservations"]) == 1
                assert row.trace["_selection_recovery"]["state"] == "uncertain"
                assert row.trace["_activity_observation"] == "settled"
                assert await run_personalized_activity(ctx, actor=actor, run=run) == result
                assert calls == ["selection", "selection", "plan"]
                assert db.scalar(select(func.count(PostLike.id))) == 1
            finally:
                binding.unregister(runtime)
                await checkpoint.close()
    execute(scenario())


def test_commit_abort_retries_recovery_admission_atomically(store):
    engine, _, _ = store
    async def scenario():
        with Session(engine, expire_on_commit=False) as db:
            lane, state, run, original = await interrupted(db)
            delivery = lane.delivery(state)
            commits = []
            def abort_once(connection):
                commits.append(1)
                if len(commits) == 1:
                    raise OperationalError("COMMIT", {}, SerializationFailure("test abort"))
            event.listen(engine, "commit", abort_once)
            try:
                RecoveryLedger(db, run.activity_id).reserve_delivery_recovery(delivery)
            finally:
                event.remove(engine, "commit", abort_once)
            db.refresh(run);db.refresh(delivery.row)
            assert len(commits) == 2
            assert delivery.attempt == 1 and delivery.row.state == "prepared"
            assert delivery.row.trace["_selection_recovery"]["state"] == "uncertain"
            assert run.result["recovery_reservations"] == [delivery.recovery_key]
            assert run.result["normal_reservations"] == ["original-selector"]
    execute(scenario())
