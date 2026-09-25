import asyncio
from dataclasses import replace

import pytest

from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
from app.runtime.autonomous_activity.graph import build_autonomous_graph
from runtime.test_autonomous_activity_graph import lane_ports


@pytest.mark.parametrize("interrupt", [False, True])
def test_combined_order_uses_frozen_selection_and_fresh_later_context(tmp_path, interrupt):
    async def scenario():
        calls, contexts = [], {}
        fail = [interrupt]
        async def load(_): return {"shared_context": {"completed": []}}
        async def refresh(state):
            return {"shared_context": {"completed": [p for p in ("inbox", "feed") if f"{p}_result" in state]}}
        async def prepare(state):
            calls.append("prepare")
            return {"prepared_lanes": {lane: {"candidates": [{"target_id": lane + "-1", "text": "hello", "allowed_actions": ["comment"]}]}
                for lane in ("inbox", "feed")}}
        async def mode(_): return {"selection_mode": "combined"}
        async def select(state):
            calls.append("combined:select")
            return {"prepared_lanes": {k: {**v, "selections": [{"target_id": k + "-1"}]} for k, v in state["prepared_lanes"].items()}}
        async def use_prepared(_): return {}
        async def finish(state): return {"result": {"paths": {p: state[p + "_result"] for p in ("inbox", "feed", "routine")}}}
        def graph(saver):
            lanes = {}
            for name in ("inbox", "feed", "routine"):
                p = lane_ports(name, calls, fail=fail if name == "feed" else None)
                async def context(state, lane=name, original=p.build_context):
                    contexts[lane] = state["shared_context"]["completed"]
                    return await original(state)
                p = replace(p, build_context=context)
                if name != "routine": p = replace(p, load_candidates=use_prepared)
                lanes[name] = p
            return build_autonomous_graph(lanes=lanes, load_context=load, refresh=refresh, finalize=finish,
                checkpointer=saver, prepare=prepare, choose_selection_mode=mode, combined_select=select)
        config = checkpoint_config(activity_id="combined")
        async with activity_checkpointer(tmp_path) as saver:
            if interrupt:
                with pytest.raises(RuntimeError, match="simulated_process_exit"):
                    await graph(saver).ainvoke({"identity": {"world_id": "world", "contract_version": 2}}, config)
                result = await graph(saver).ainvoke(None, config)
            else:
                result = await graph(saver).ainvoke({"identity": {"world_id": "world", "contract_version": 2}}, config)
        assert contexts == {"inbox": [], "feed": ["inbox"], "routine": ["inbox", "feed"]}
        assert calls.count("combined:select") == 1 and calls.count("prepare") == 1
        assert not any(c in calls for c in ("inbox:select", "feed:select", "routine:select"))
        assert [c for c in calls if c.endswith(":execute")] == ["inbox:execute", "feed:execute", "routine:execute"]
        assert calls.count("feed:plan") == 1
        assert len(result["result"]["paths"]) == 3
    asyncio.run(scenario())
