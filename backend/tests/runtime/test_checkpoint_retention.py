import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines.models import AgentPublicActionExecution, AgentSlot
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import RETENTION_KEY, business_result
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.domains.world_characters.service.checkpoint_retention import eligible
from app.runtime.autonomous_activity.binding import ActivityRuntimeBinding, register, unregister
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer
from app.runtime.autonomous_activity.checkpoint_maintenance import CheckpointMaintenance, protection_reason
from app.runtime.autonomous_activity.execution import run_personalized_activity
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.planner_contract import parse_action
from retention_support import NOW, checkpoint, completed, database
from social.test_feed_reaction_intent import _engine, _seed

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("seconds,expected", [(86399, False), (86400, True), (86401, True), (-1, False)])
def test_utc_retention_boundary(tmp_path, seconds, expected):
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            row = completed(db, ids, age=timedelta(seconds=seconds))
            assert eligible(row, now=NOW) is expected
    finally:
        engine.dispose()


@pytest.mark.parametrize("state", ["failed", "aborted", "running", "waiting", "interrupted", "outcome_unknown"])
def test_incomplete_or_failed_is_preserved(tmp_path, state):
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            assert not eligible(completed(db, ids, status=state), now=NOW)
    finally:
        engine.dispose()


@pytest.mark.parametrize("damage", ["legacy", "timestamp_missing", "policy_unknown", "unconfirmed", "result_missing", "bad_paths"])
def test_ambiguous_or_legacy_is_preserved(tmp_path, damage):
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            row = completed(db, ids, marked=damage != "legacy", confirmed=damage != "unconfirmed")
            if damage == "timestamp_missing":
                row.finished_at = None
            elif damage == "policy_unknown":
                row.result = {**row.result, RETENTION_KEY: {"policy": "unknown"}}
            elif damage == "result_missing":
                row.result = {RETENTION_KEY: row.result[RETENTION_KEY]}
            elif damage == "bad_paths":
                row.result = {**row.result, "paths": {}}
            db.commit()
            assert not eligible(row, now=NOW)
    finally:
        engine.dispose()


def test_creation_marks_once_and_setting_changes_never_backfill(tmp_path, monkeypatch):
    from app.config import settings
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            actor = db.get(WorldCharacter, ids[2])
            monkeypatch.setattr(settings, "SNS_CHECKPOINT_POLICY_ENABLED", False)
            legacy = bind_run(db, actor=actor, activity_id="unmarked")
            db.commit()
            assert RETENTION_KEY not in legacy.result
            monkeypatch.setattr(settings, "SNS_CHECKPOINT_POLICY_ENABLED", True)
            assert RETENTION_KEY not in bind_run(db, actor=actor, activity_id="unmarked").result
            assert RETENTION_KEY in bind_run(db, actor=actor, activity_id="new").result
    finally:
        engine.dispose()


def test_sdk_deletes_all_namespaces_and_writes_but_preserves_legacy(tmp_path):
    async def scenario():
        engine, factory, ids = database(tmp_path)
        try:
            with factory() as db:
                completed(db, ids, identifier="expired")
                completed(db, ids, identifier="legacy", age=timedelta(days=60), marked=False)
            async with activity_checkpointer(tmp_path) as saver:
                for identifier in ("expired", "legacy"):
                    for ns in ("", "feed:child", "routine:child"):
                        await checkpoint(saver, identifier, namespace=ns)
            task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory, clock=lambda: NOW)
            assert (await task.cycle())["pruned"] == 1
            async with activity_checkpointer(tmp_path) as saver:
                assert [item async for item in saver.alist({"configurable": {"thread_id": "activity:expired"}})] == []
                kept = [item async for item in saver.alist({"configurable": {"thread_id": "activity:legacy"}})]
                assert len(kept) == 3 and all(item.pending_writes for item in kept)
            with factory() as db:
                assert RETENTION_KEY not in db.get(ActivityGraphRun, "legacy").result
                assert db.get(ActivityGraphRun, "expired").result[RETENTION_KEY]["state"] == "pruned"
        finally:
            engine.dispose()
    asyncio.run(scenario())


def test_mark_failure_is_idempotent_and_never_reexecutes_business(tmp_path, monkeypatch):
    async def scenario():
        engine, factory, ids = database(tmp_path)
        try:
            with factory() as db:
                original = business_result(completed(db, ids).result)
            async with activity_checkpointer(tmp_path) as saver:
                await checkpoint(saver, "old")
            task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory, clock=lambda: NOW)
            mark = task._mark
            monkeypatch.setattr(task, "_mark", lambda *args: (_ for _ in ()).throw(OSError("injected mark")))
            assert (await task.cycle())["deferred"] == 1
            with factory() as db:
                row = db.get(ActivityGraphRun, "old")
                assert row.result[RETENTION_KEY]["state"] == "claimed"
                assert business_result(row.result) == original
            monkeypatch.setattr(task, "_mark", mark)
            assert (await task.cycle())["pruned"] == 1
            with factory() as db:
                assert business_result(db.get(ActivityGraphRun, "old").result) == original
        finally:
            engine.dispose()
    asyncio.run(scenario())


def _real_run(monkeypatch, root):
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    engine, factory, _ = database(root, seed=False)
    db = factory()
    ctx, post = _seed(db, with_candidate=True)
    actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
    db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
        assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
        lease_expires_at=NOW + timedelta(days=500)))
    run = bind_run(db, actor=actor, activity_id=ctx.run_id)
    run.contract_version = 1
    db.commit()
    calls = []
    async def plan(self, **kwargs):
        calls.append("plan")
        kwargs["delivery"].dispatched(); kwargs["delivery"].delivered()
        return {**parse_action({"decisions": [{"target_id": post.id, "action": "like", "brief": "Useful discovery"}]}, kwargs["candidates"]),
            "judged_at": NOW.isoformat(), "provisional_draft": {"replies": []}}
    monkeypatch.setattr(ActivityProvider, "plan", plan)
    binding = ActivityRuntimeBinding(None, root)
    register(binding)
    return db, ctx, actor, run, calls, binding


def test_completed_same_id_ten_reads_need_no_binding_lease_or_provider(tmp_path, monkeypatch):
    async def scenario():
        db, ctx, actor, run, calls, binding = _real_run(monkeypatch, tmp_path)
        try:
            first = await run_personalized_activity(ctx, actor=actor, run=run)
            finished = run.finished_at
            actor.autonomous_enabled = False
            db.delete(db.get(AgentSlot, ctx.agent_id)); db.commit()
            unregister(binding)
            from sqlalchemy.orm import sessionmaker
            task = CheckpointMaintenance(data_root=tmp_path,
                session_factory=sessionmaker(db.get_bind(), expire_on_commit=False),
                clock=lambda: finished.replace(tzinfo=NOW.tzinfo) + timedelta(days=2))
            assert (await task.cycle())["pruned"] == 1
            monkeypatch.setattr(ActivityProvider, "__init__", lambda *a, **k: pytest.fail("provider constructed"))
            for _ in range(10):
                assert await run_personalized_activity(ctx, actor=actor, run=run) == first
            assert run.finished_at == finished and calls == ["plan"]
            assert len(db.scalars(select(AgentPublicActionExecution)).all()) == 1
        finally:
            unregister(binding); db.close(); db.get_bind().dispose()
    asyncio.run(scenario())


def test_finalize_commit_survives_last_checkpoint_failure(tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    async def scenario():
        db, ctx, actor, run, calls, binding = _real_run(monkeypatch, tmp_path)
        original = AsyncSqliteSaver.aput
        async def fail_final(self, config, value, metadata, versions):
            final = value.get("channel_values", {}).get("result", {})
            if isinstance(final, dict) and final.get("engine") == "personalized_graph_v2":
                raise OSError("injected final checkpoint")
            return await original(self, config, value, metadata, versions)
        monkeypatch.setattr(AsyncSqliteSaver, "aput", fail_final)
        try:
            with pytest.raises(OSError, match="injected final"):
                await run_personalized_activity(ctx, actor=actor, run=run)
            db.expire_all()
            assert run.status == "completed" and not run.result[RETENTION_KEY]["graph_complete"]
            final = await run_personalized_activity(ctx, actor=actor, run=run)
            assert final["publish_result"]["public_action_count"] == 1 and calls == ["plan"]
            assert not eligible(run, now=NOW + timedelta(days=600))
        finally:
            unregister(binding); db.close(); db.get_bind().dispose()
    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["owner", "world", "contract", "paths", "receipt"])
def test_terminal_bad_scope_or_result_never_constructs_graph(tmp_path, monkeypatch, damage):
    async def scenario():
        db, ctx, actor, run, calls, binding = _real_run(monkeypatch, tmp_path)
        try:
            await run_personalized_activity(ctx, actor=actor, run=run)
            if damage == "owner":
                from dataclasses import replace
                ctx = replace(ctx, user_id="wrong-owner")
            elif damage == "world":
                from types import SimpleNamespace
                actor = SimpleNamespace(id=actor.id, character_id=actor.character_id,
                    membership_id=actor.membership_id, world_id="wrong-world")
            elif damage == "contract":
                run.contract_version = 2
            elif damage == "paths":
                run.result = {**run.result, "paths": {}}
            else:
                receipt = db.scalar(select(AgentPublicActionExecution))
                receipt.result = None
            db.flush()
            monkeypatch.setattr(ActivityProvider, "__init__", lambda *a, **k: pytest.fail("provider constructed"))
            with pytest.raises(ValueError):
                await run_personalized_activity(ctx, actor=actor, run=run)
            assert calls == ["plan"]
        finally:
            db.rollback(); unregister(binding); db.close(); db.get_bind().dispose()
    asyncio.run(scenario())
