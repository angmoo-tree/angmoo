import pytest
import asyncio

from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
from app.runtime.autonomous_activity.graph import LanePorts, build_autonomous_graph


def lane_ports(name, calls, *, fail=None):
    async def guard(state):
        assert state["identity"]["world_id"] == "world"
        return {}

    async def load(state):
        return {"candidates": [{"target_id": f"{name}-{i}", "text": "A real new utterance", "allowed_actions": ["comment"]} for i in range(3)]}

    async def select(state):
        calls.append(f"{name}:select")
        return {"selections": [{"target_id": f"{name}-1", "memory_query": "previous relevant experience"}]}

    async def routine_query(state):
        return {"queries": [{"target_id": "routine", "query": "current routine", "origin": "routine"}]}

    async def recall(state):
        calls.append(f"{name}:recall")
        assert len(state["queries"]) == 1
        return {"memories": {"selected": {"text": "already replied"}}}

    async def context(state):
        return {"decision_context": {"memory": state["memories"], "state": state["shared_context"]}}

    async def plan(state):
        calls.append(f"{name}:plan")
        assert state["decision_context"]["memory"]["selected"]["text"] == "already replied"
        return {"decision": {"action": "comment"}}

    async def validate(state):
        return {"assignments": [{"target_id": f"{name}-1"}]}

    async def write(state):
        if fail is not None and fail[0]:
            fail[0] = False
            raise RuntimeError("simulated_process_exit")
        calls.append(f"{name}:write")
        return {"drafts": [{"body": "hello"}]}

    async def execute(state):
        calls.append(f"{name}:execute")
        return {"executions": [{"status": "succeeded"}]}

    async def settle(state):
        calls.append(f"{name}:settle")
        return {"settlement": {"state": "kept"}}

    async def final(state):
        return {"result": {"status": "completed", "public_action_count": 1}}

    return LanePorts(load, select, recall, context, plan, validate, write, execute, settle, final, guard, routine_query)


def test_durable_child_resume_does_not_repeat_completed_ai_or_recall(tmp_path):
    asyncio.run(_resume(tmp_path))


def test_feed_path_result_storage_failure_reuses_completed_actions(tmp_path):
    from dataclasses import replace
    from app.domains.relationships.exceptions import ObservationOutboxIntegrityError

    async def scenario():
        calls = []
        fail = [True]

        async def load(_state):
            return {"shared_context": {"mood": "calm"}}

        async def finish(_state):
            return {"result": {"status": "completed"}}

        def graph(saver):
            lanes = {name: lane_ports(name, calls)
                     for name in ("inbox", "routine", "feed")}
            completed = lanes["feed"].finalize

            async def feed_final(state):
                calls.append("feed:path_result")
                if fail[0]:
                    fail[0] = False
                    raise ObservationOutboxIntegrityError("observation_outbox_identity_mismatch")
                return await completed(state)

            lanes["feed"] = replace(lanes["feed"], finalize=feed_final)
            return build_autonomous_graph(
                lanes=lanes, load_context=load, refresh=load,
                finalize=finish, checkpointer=saver,
            )

        config = checkpoint_config(activity_id="feed-path-result-retry")
        async with activity_checkpointer(tmp_path) as saver:
            with pytest.raises(ObservationOutboxIntegrityError):
                await graph(saver).ainvoke({"identity": {"world_id": "world"}}, config)
        async with activity_checkpointer(tmp_path) as saver:
            result = await graph(saver).ainvoke(None, config)
        assert result["result"]["status"] == "completed"
        assert calls.count("feed:path_result") == 2
        for step in ("plan", "write", "execute", "settle"):
            assert calls.count("feed:" + step) == 1

    asyncio.run(scenario())


async def _resume(tmp_path):
    calls = []
    fail = [True]
    async def load(state): return {"shared_context": {"mood": "calm"}}
    async def refresh(state): return {"shared_context": {"mood": "hopeful"}}
    async def final(state): return {"result": {"status": "completed"}}
    def graph(saver):
        return build_autonomous_graph(lanes={name: lane_ports(name, calls, fail=fail if name == "inbox" else None)
            for name in ("inbox", "routine", "feed")}, load_context=load, refresh=refresh, finalize=final, checkpointer=saver)
    config = checkpoint_config(activity_id="run-1")
    async with activity_checkpointer(tmp_path) as saver:
        with pytest.raises(RuntimeError, match="simulated_process_exit"):
            await graph(saver).ainvoke({"identity": {"world_id": "world"}}, config)
    # Reopen the physical SQLite saver and reconstruct graph/adapters.
    async with activity_checkpointer(tmp_path) as saver:
        result = await graph(saver).ainvoke(None, config)
    assert result["result"]["status"] == "completed"
    for name in ("inbox", "routine", "feed"):
        assert calls.count(f"{name}:recall") == 1
        assert calls.count(f"{name}:plan") == 1
        assert calls.count(f"{name}:execute") == 1
    assert not any(call == "routine:select" for call in calls)


@pytest.mark.parametrize("stop_at", ["ResolveQuery", "BuildDecisionContext", "ValidateDecision", "Settle", "PathResult"])
def test_reopen_after_each_completed_checkpoint_preserves_prior_results(tmp_path, stop_at):
    from dataclasses import replace
    async def scenario():
        calls, stopped = [], [False]
        async def load(state): return {"shared_context": {"mood": "calm"}}
        async def final(state): return {"result": {"status": "completed"}}
        def graph(saver):
            lanes = {name: lane_ports(name, calls) for name in ("inbox", "routine", "feed")}
            original = lanes["inbox"].guard
            async def guard(state):
                if state.get("stage") == stop_at and not stopped[0]:
                    stopped[0] = True
                    raise RuntimeError("checkpoint_boundary_exit")
                return await original(state)
            lanes["inbox"] = replace(lanes["inbox"], guard=guard)
            return build_autonomous_graph(lanes=lanes, load_context=load, refresh=load, finalize=final, checkpointer=saver)
        config = checkpoint_config(activity_id="boundary")
        async with activity_checkpointer(tmp_path) as saver:
            with pytest.raises(RuntimeError, match="checkpoint_boundary_exit"):
                await graph(saver).ainvoke({"identity": {"world_id": "world"}}, config)
        async with activity_checkpointer(tmp_path) as saver:
            result = await graph(saver).ainvoke(None, config)
        assert result["result"]["status"] == "completed"
        for step in ("select", "recall", "plan", "write", "execute", "settle"):
            assert calls.count("inbox:" + step) == 1
    asyncio.run(scenario())


def test_retry_guard_failure_at_writer_does_not_soft_settle_stale_plan():
    from dataclasses import replace
    from app.runtime.autonomous_activity.graph import build_lane
    from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
    async def scenario():
        calls, events = [], []
        ports = lane_ports("inbox", calls)
        async def stale_write(_state):
            raise ActivityRetryGuardError(ValueError("activity_memory_changed"))
        ports = replace(ports, write=stale_write,
            observe=lambda kind, node, **details: events.append((kind, node, details.get("phase"))))
        with pytest.raises(ValueError, match="activity_memory_changed"):
            await build_lane("inbox", ports).ainvoke({"identity": {"world_id": "world"},
                "shared_context": {}})
        assert "inbox:settle" not in calls
        assert ("node_failed", "Writer", "retry_guard") in events
    asyncio.run(scenario())
