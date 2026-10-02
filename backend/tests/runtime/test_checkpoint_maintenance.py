import asyncio
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from time import monotonic

import pytest
from sqlalchemy import select

from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.routines.models import AgentPublicActionExecution, AgentRun, AgentSlot
from app.domains.social.models.posts import PostLike
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import RETENTION_KEY, CheckpointRetention
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.runtime.autonomous_activity.checkpoint_maintenance import CheckpointMaintenance, MaintenanceLimits, protection_reason
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, backup_checkpoint
from app.runtime.migrations.generation import EmbeddedUpgradeLock
from retention_support import NOW, checkpoint, completed, database, result

pytestmark = pytest.mark.usefixtures("deny_external_network")


def test_startup_idle_periodic_and_two_root_isolation(tmp_path):
    async def scenario():
        stores = [database(tmp_path / name) for name in ("one", "two")]
        tasks = []
        try:
            for name, (engine, factory, ids) in zip(("one", "two"), stores):
                with factory() as db:
                    completed(db, ids, identifier="same-id")
                async with activity_checkpointer(tmp_path / name) as saver:
                    await checkpoint(saver, "same-id")
                tasks.append(CheckpointMaintenance(data_root=tmp_path / name,
                    session_factory=factory, clock=lambda: NOW, limits=MaintenanceLimits(interval_seconds=.03)))
            await tasks[0].start()
            assert tasks[0].last_cycle["pruned"] == 1
            with stores[1][1]() as db:
                assert db.get(ActivityGraphRun, "same-id").result[RETENTION_KEY]["state"] == "retained"
            await tasks[1].start()
            assert tasks[1].last_cycle["pruned"] == 1
            with stores[0][1]() as db:
                completed(db, stores[0][2], identifier="after-start")
            for _ in range(100):
                with stores[0][1]() as db:
                    done = db.get(ActivityGraphRun, "after-start").result[RETENTION_KEY]["state"] == "pruned"
                if done:
                    break
                await asyncio.sleep(.01)
            assert done
        finally:
            for task in tasks:
                await task.stop()
                assert task._task is None
            for engine, _, _ in stores:
                engine.dispose()
    asyncio.run(scenario())


def test_protected_candidate_cursor_advances_past_full_batch(tmp_path):
    async def scenario():
        engine, factory, ids = database(tmp_path)
        try:
            with factory() as db:
                for index in range(65):
                    completed(db, ids, identifier=f"protected-{index:03}", confirmed=False)
                completed(db, ids, identifier="zz-eligible")
            task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory,
                clock=lambda: NOW, limits=MaintenanceLimits(maximum_candidates=30, start_budget_seconds=30))
            outcomes = [await task.cycle() for _ in range(3)]
            assert sum(item.get("pruned", 0) for item in outcomes) == 1
            with factory() as db:
                assert all(row.result[RETENTION_KEY]["state"] == "retained" for row in db.scalars(
                    select(ActivityGraphRun).where(ActivityGraphRun.activity_id.like("protected-%"))))
        finally:
            engine.dispose()
    asyncio.run(scenario())


def test_recovery_lease_different_id_and_pending_effect_protect(tmp_path):
    engine, factory, ids = database(tmp_path)
    try:
        with factory() as db:
            row = completed(db, ids)
            lease = AgentRun(id="new-recovery-lease", user_id=ids[0], character_id=ids[1],
                agent_id="recovery-slot", session_key="recovery", status="running")
            db.add(lease); db.flush()
            slot = AgentSlot(agent_id="recovery-slot", locked_by_run_id=lease.id, status="running",
                assigned_character_id=ids[1], assigned_user_id=ids[0], lease_expires_at=NOW + timedelta(minutes=1))
            db.add(slot); db.commit()
            assert protection_reason(db, row, now=NOW) == "live_actor_lease"
            slot.lease_expires_at = NOW - timedelta(seconds=1)
            db.add(AgentRun(id=row.activity_id, user_id=ids[0], character_id=ids[1],
                agent_id="old-slot", session_key="old", status="completed")); db.flush()
            pending = AgentPublicActionExecution(run_id=row.activity_id, character_id=ids[1],
                signature="pending-effect", scope="writing", action_type="post", status="pending")
            db.add(pending); db.commit()
            assert protection_reason(db, row, now=NOW) == "pending_public_effect"
    finally:
        engine.dispose()


def test_busy_cancellation_backup_lock_and_reload_release(tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    async def scenario():
        engine, factory, ids = database(tmp_path)
        try:
            with factory() as db:
                completed(db, ids)
            async with activity_checkpointer(tmp_path) as saver:
                await checkpoint(saver, "old")
            task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory, clock=lambda: NOW)
            with EmbeddedUpgradeLock(tmp_path / "runtime" / "activity" / "checkpoint-maintenance.lock"):
                assert (await task.cycle()) == {"locked": 1}
                from app.runtime.migrations.generation import EmbeddedGenerationError
                with pytest.raises(EmbeddedGenerationError):
                    backup_checkpoint(tmp_path, tmp_path / "blocked-backup.sqlite3")
            checkpoint_path = tmp_path / "runtime" / "activity" / "activity-checkpoints.sqlite"
            locked = sqlite3.connect(checkpoint_path)
            locked.execute("BEGIN IMMEDIATE")
            started = monotonic()
            try:
                assert (await task.cycle()).get("deferred", 0) + task.last_cycle.get("cycle_deferred", 0) >= 1
                assert monotonic() - started < 1
            finally:
                locked.rollback(); locked.close()
            entered, release = asyncio.Event(), asyncio.Event()
            original = AsyncSqliteSaver.adelete_thread
            async def delay(self, thread_id):
                entered.set()
                await release.wait()
                await original(self, thread_id)
            monkeypatch.setattr(AsyncSqliteSaver, "adelete_thread", delay)
            running = asyncio.create_task(task.cycle())
            await entered.wait()
            running.cancel()
            await asyncio.sleep(.02)
            assert not running.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await running
            monkeypatch.setattr(AsyncSqliteSaver, "adelete_thread", original)
            # The interrupted claim is recoverable, with all handles released.
            task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory, clock=lambda: NOW)
            assert (await task.cycle())["pruned"] == 1
            assert backup_checkpoint(tmp_path, tmp_path / "completed-backup.sqlite3")
        finally:
            engine.dispose()
    asyncio.run(scenario())


def test_100_activities_over_virtual_days_limits_detail_blobs(tmp_path):
    async def scenario():
        metrics = {}
        for name, marked in (("30-day-baseline", False), ("24-hour", True)):
            root = tmp_path / name
            engine, factory, ids = database(root)
            try:
                with factory() as db:
                    for day in range(10):
                        for index in range(10):
                            completed(db, ids, identifier=f"day-{day}-{index}", age=timedelta(days=10-day), marked=marked)
                    completed(db, ids, identifier="failed-preserved", status="failed")
                async with activity_checkpointer(root) as saver:
                    for day in range(10):
                        for index in range(10):
                            for ns in ("", "feed:child"):
                                await checkpoint(saver, f"day-{day}-{index}", namespace=ns, blob=bytes(range(256))*128)
                    await checkpoint(saver, "failed-preserved", blob=b"failed"*100)
                task = CheckpointMaintenance(data_root=root, session_factory=factory,
                    clock=lambda: NOW, limits=MaintenanceLimits(start_budget_seconds=30))
                outcome = await task.cycle()
                path = root / "runtime" / "activity" / "activity-checkpoints.sqlite"
                with sqlite3.connect(path) as db:
                    checkpoints, checkpoint_bytes = db.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(checkpoint)),0) FROM checkpoints").fetchone()
                    writes, write_bytes = db.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(value)),0) FROM writes").fetchone()
                metrics[name] = {"checkpoint_rows": checkpoints, "write_rows": writes,
                    "detail_blob_bytes": checkpoint_bytes + write_bytes, "cycle": outcome,
                    "physical_bytes": path.stat().st_size}
                with factory() as db:
                    assert db.get(ActivityGraphRun, "failed-preserved").status == "failed"
                    assert len(db.scalars(select(ActivityGraphRun).where(ActivityGraphRun.status == "observed")).all()) == 100
            finally:
                engine.dispose()
        assert metrics["24-hour"]["checkpoint_rows"] == metrics["24-hour"]["write_rows"] == 1
        assert metrics["30-day-baseline"]["checkpoint_rows"] == metrics["30-day-baseline"]["write_rows"] == 201
        assert metrics["24-hour"]["detail_blob_bytes"] < metrics["30-day-baseline"]["detail_blob_bytes"] / 100
        (tmp_path / "checkpoint-workload-metrics.json").write_text(json.dumps(metrics, indent=2))
    asyncio.run(scenario())


def test_start_budget_finishes_active_delete_and_defers_next_target(tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    async def scenario():
        engine, factory, ids = database(tmp_path)
        elapsed = [0.0]
        try:
            with factory() as db:
                completed(db, ids, identifier="one")
                completed(db, ids, identifier="two")
            async with activity_checkpointer(tmp_path) as saver:
                await checkpoint(saver, "one"); await checkpoint(saver, "two")
            original = AsyncSqliteSaver.adelete_thread
            async def slow(self, identifier):
                await original(self, identifier)
                elapsed[0] += 6
            monkeypatch.setattr(AsyncSqliteSaver, "adelete_thread", slow)
            task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory,
                clock=lambda: NOW, monotonic_clock=lambda: elapsed[0])
            outcome = await task.cycle()
            assert outcome["pruned"] == 1 and outcome["max_delete_ms"] == 6000
            with factory() as db:
                assert db.get(ActivityGraphRun, "one").result[RETENTION_KEY]["state"] == "pruned"
                assert db.get(ActivityGraphRun, "two").result[RETENTION_KEY]["state"] == "retained"
            assert (await task.cycle())["pruned"] == 1
        finally:
            engine.dispose()
    asyncio.run(scenario())


async def _overlap_workload(root, *, cleanup):
    from langgraph.graph import StateGraph, START, END
    from app.domains.identity.models import User
    from social.test_feed_reaction_intent import _character
    engine, factory, ids = database(root)
    lanes = []
    progress, provider_calls, intervals, waits = {}, {}, {}, {}
    try:
        with factory() as db:
            owner = db.get(User, ids[0])
            initial_actor = db.get(WorldCharacter, ids[2])
            for name in ("A", "B", "C", "cleanup"):
                character = _character(owner, "overlap-" + name)
                db.add(character); db.flush()
                actor = WorldCharacter(id="actor-" + name, world_id=ids[3], character_id=character.id,
                    membership_id=initial_actor.membership_id, role_key="student", status="active", autonomous_enabled=True,
                    local_profile={}, character_contract_hash=initial_actor.character_contract_hash,
                    world_contract_hash=initial_actor.world_contract_hash)
                db.add(actor); db.flush()
                if name == "cleanup":
                    cleanup_ids = (*ids[:2], actor.id, *ids[3:])
                    continue
                run = bind_run(db, actor=actor, activity_id="activity-" + name)
                db.add(AgentRun(id=run.activity_id, user_id=ids[0], character_id=character.id,
                    agent_id="slot-" + name, session_key="overlap", status="running"))
                db.add(AgentSlot(agent_id="slot-" + name, locked_by_run_id=run.activity_id,
                    assigned_user_id=ids[0], assigned_character_id=character.id, status="running",
                    lease_expires_at=NOW + timedelta(minutes=10)))
                lanes.append((name, character.id, actor.id, run.activity_id))
            db.commit()
            for index in range(20):
                completed(db, cleanup_ids, identifier=f"expired-{index:02}")
            completed(db, cleanup_ids, identifier="large-thread")
        async with activity_checkpointer(root) as saver:
            for index in range(20):
                await checkpoint(saver, f"expired-{index:02}", blob=b"normal"*1024)
            await checkpoint(saver, "large-thread", blob=b"large"*(1024*1024))
            for name, *_ in lanes:
                progress[name], provider_calls[name], intervals[name], waits[name] = [], 0, [], []
            async def activity(lane):
                name, character_id, actor_id, activity_id = lane
                previous = monotonic()
                async def tick(state):
                    nonlocal previous
                    step = state.get("step", 0) + 1
                    if step == 1:
                        provider_calls[name] += 1  # a deterministic fake model invocation
                    await asyncio.sleep(.01)
                    begin = monotonic()
                    def write():
                        with factory() as db:
                            def transaction():
                                slot = db.get(AgentSlot, "slot-" + name)
                                assert slot.locked_by_run_id == activity_id
                                assert slot.lease_expires_at.replace(tzinfo=NOW.tzinfo) > NOW
                                slot.lease_expires_at = NOW + timedelta(minutes=10)
                                if step == 8:
                                    from app.domains.social.models.posts import Post
                                    target = db.get(Post, ids[4])
                                    db.add(PostLike(post_id=ids[4], user_id=ids[0], character_id=character_id,
                                        world_id=ids[3], actor_world_character_id=actor_id,
                                        target_world_character_id=target.author_world_character_id))
                                    db.add(AgentPublicActionExecution(run_id=activity_id, character_id=character_id,
                                        signature="overlap-effect-" + name, scope="world_keyword_feed", action_type="like",
                                        world_id=ids[3], actor_world_character_id=actor_id, target_post_id=ids[4],
                                        status="succeeded", completed_at=NOW, result={"post_id": ids[4]}))
                                    row = db.get(ActivityGraphRun, activity_id)
                                    row.status, row.stage, row.finished_at = "completed", "Finalize", NOW
                                    row.result = {**row.result, **result(count=1), RETENTION_KEY: CheckpointRetention(graph_complete=True).model_dump()}
                                    db.get(AgentRun, activity_id).status = "completed"
                            run_sqlite_session_immediate(db, transaction, require_clean=True)
                    await asyncio.to_thread(write)
                    ended = monotonic()
                    waits[name].append(ended - begin); intervals[name].append(ended - previous)
                    previous = ended; progress[name].append(step)
                    return {"step": step}
                builder = StateGraph(dict)
                for index in range(8):
                    builder.add_node(str(index), tick)
                    builder.add_edge(START if index == 0 else str(index - 1), str(index))
                builder.add_edge("7", END)
                graph = builder.compile(checkpointer=saver)
                value = await graph.ainvoke({"step": 0}, {"configurable": {"thread_id": "activity:" + activity_id}})
                assert value["step"] == 8
            task = CheckpointMaintenance(data_root=root, session_factory=factory,
                clock=lambda: NOW, limits=MaintenanceLimits(start_budget_seconds=30))
            started = monotonic()
            results = await asyncio.gather(*(activity(lane) for lane in lanes), task.cycle() if cleanup else asyncio.sleep(0))
            duration = monotonic() - started
            assert all(value == list(range(1, 9)) for value in progress.values())
            assert provider_calls == {"A": 1, "B": 1, "C": 1}
            if cleanup:
                assert results[-1]["pruned"] == 21
            with factory() as db:
                assert len(db.scalars(select(PostLike)).all()) == 3
                assert len(db.scalars(select(AgentPublicActionExecution)).all()) == 3
                assert all(db.get(ActivityGraphRun, lane[3]).status == "completed" for lane in lanes)
        flat = sorted(wait for values in waits.values() for wait in values)
        return {"duration_seconds": duration, "max_write_seconds": max(flat),
            "p95_write_seconds": flat[int((len(flat)-1)*.95)],
            "max_tick_gap_seconds": max(gap for values in intervals.values() for gap in values),
            "progress": progress, "provider_calls": provider_calls, "cleanup": task.last_cycle}
    finally:
        engine.dispose()


def test_three_characters_progress_with_normal_and_large_cleanup(tmp_path):
    async def scenario():
        baseline = await _overlap_workload(tmp_path / "off", cleanup=False)
        enabled = await _overlap_workload(tmp_path / "on", cleanup=True)
        # The canonical writer is bounded at 250 ms, with 250 ms allowance for
        # thread scheduling. A lease renews at each node (actual lease: 10 min).
        assert enabled["max_write_seconds"] < max(.5, baseline["max_write_seconds"] * 3)
        assert enabled["p95_write_seconds"] < baseline["p95_write_seconds"] * 3 + .05
        assert enabled["max_tick_gap_seconds"] < max(1, baseline["max_tick_gap_seconds"] * 3)
        assert enabled["duration_seconds"] < baseline["duration_seconds"] * 3 + 1.5
        (tmp_path / "concurrent-workload-metrics.json").write_text(json.dumps({"off": baseline, "on": enabled}, indent=2))
    asyncio.run(scenario())
