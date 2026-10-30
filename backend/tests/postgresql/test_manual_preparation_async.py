"""Manual HTTP generation releases dependency reads and keeps all source guards."""
import asyncio
import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from routines import test_daily_preparation as fixture_source
from app.core.async_session import release_request_read
from app.domains.identity.models import User
from app.domains.routines.client import PreparationTracker
from app.domains.routines.router import request_daily_preparation
from app.domains.routines.schemas.daily_generation import DailyPreparationRequest, InitialPreparationOutput
from app.domains.social.recommendation_router import regenerate
from app.domains.social.schemas.recommendation import TopicDefinition, TopicGenerationResult, TopicRegenerateRequest
from app.domains.worlds.models import World
from app.runtime.social import topic_preparation


@pytest.fixture
def manual_scope(store, monkeypatch, deny_external_network):
    engine, _, _ = store
    monkeypatch.setattr(fixture_source, "_engine", lambda: engine)
    fixture = fixture_source.preparation_scope.__wrapped__(monkeypatch, deny_external_network)
    db, world, ready, runtime = next(fixture)
    ids = dict(character_id=ready.character.id, world_id=world.id,
               owner_id=ready.user.id, actor_id=ready.world_character.id)
    db.rollback()
    user = db.scalar(select(User).where(User.id == ids["owner_id"]))
    assert user is not None and db.in_transaction()
    try:
        yield engine, db, user, ids, runtime
    finally:
        fixture.close()


def test_manual_daily_releases_authentication_read_before_provider(manual_scope):
    engine, db, user, ids, runtime = manual_scope
    held = []
    async def generate(**kwargs):
        tracker = PreparationTracker(kwargs["reserve"])
        assert await tracker.reserve_provider_call_order() == 1
        held.append(engine.pool.checkedout())
        await asyncio.sleep(.03)
        return InitialPreparationOutput(daily_plan=fixture_source.output(),
            recommendation_topics=[{"name": "독서", "scope": "common"}]), tracker
    async def ensure(parent, **kwargs):
        assert kwargs["user"].id == ids["owner_id"]
        return await runtime.ensure_preparation(parent, **kwargs, generator=generate,
            now=datetime.now(UTC))
    result = asyncio.run(request_daily_preparation(ids["character_id"], ids["world_id"],
        DailyPreparationRequest(request_id="manual-parent-read", expected_version=None),
        db=db, user=user, runtime=SimpleNamespace(ensure=ensure)))
    assert result.plan_state == "ready", result
    assert held == [0]
    assert not db.in_transaction()


@pytest.mark.parametrize("outcome", ["ready", "source_changed", "provider_failure", "cancelled"])
def test_manual_topic_stages_release_connections_and_preserve_guards(manual_scope, outcome):
    engine, db, user, ids, _ = manual_scope
    held, sql_threads, calls = [], [], []
    main = threading.get_ident()
    def query(*args):
        sql_threads.append(threading.get_ident())
    async def generate(*args):
        calls.append(1)
        held.append(engine.pool.checkedout())
        assert threading.get_ident() == main
        await asyncio.sleep(.03)
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        if outcome == "provider_failure":
            raise TimeoutError("offline provider failure")
        if outcome == "source_changed":
            def edit_source():
                with Session(engine) as writer:
                    world = writer.get(World, ids["world_id"])
                    world.name = "Changed after accepted snapshot"
                    writer.commit()
            await asyncio.to_thread(edit_source)
        return TopicGenerationResult(topics=[TopicDefinition(name="독서", scope="common")])
    async def run(parent, **kwargs):
        assert kwargs["owner_id"] == ids["owner_id"]
        return await topic_preparation.regenerate(parent, **kwargs, generator=generate)
    async def request():
        return await regenerate(ids["world_id"], TopicRegenerateRequest(request_id="manual-topic"),
            ids["actor_id"], db=db, user=user, topics=SimpleNamespace(regenerate=run))
    event.listen(engine, "before_cursor_execute", query)
    try:
        if outcome == "cancelled":
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(request())
        else:
            result = asyncio.run(request())
            assert result["state"] == {"ready": "ready", "source_changed": "stale",
                                      "provider_failure": "failed"}[outcome]
            if outcome == "ready":
                # Idempotent repetition checks owner identity even after rollback
                # expired the authenticated User object.
                again = asyncio.run(request())
                assert again["topics"] == result["topics"] and calls == [1]
        assert held == [0]
        assert sql_threads and main not in sql_threads
        assert not db.in_transaction() and engine.pool.checkedout() == 0
    finally:
        event.remove(engine, "before_cursor_execute", query)


def test_request_read_boundary_refuses_pending_flushed_and_core_writes(manual_scope):
    _, db, user, ids, _ = manual_scope
    for kind in ("pending", "flushed", "core"):
        db.rollback()
        if kind == "core":
            db.execute(update(World).where(World.id == ids["world_id"]).values(name="Keep Core write"))
        else:
            world = db.get(World, ids["world_id"])
            world.name = "Keep ORM write"
            if kind == "flushed":
                db.flush()
        called = []
        def snapshot():
            called.append(1)
            return ids["owner_id"]
        with pytest.raises(RuntimeError, match="request_has_pending_writes"):
            asyncio.run(release_request_read(db, snapshot, error_code="request_has_pending_writes"))
        assert not called and db.in_transaction()
        # The boundary rejected the operation without committing or rolling back.
        assert db.get(World, ids["world_id"]).name.startswith("Keep")
    db.rollback()
