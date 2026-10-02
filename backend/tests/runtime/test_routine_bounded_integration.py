"""Real Routine graph, JSON validation, durable budgets and publication; fake SDK only."""
import asyncio
from datetime import UTC, datetime
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.routines.models import AgentPublicActionExecution
from app.domains.social.models.posts import Post
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.social_io import new_policies
from app.domains.world_characters.service.activity_engines import bind_run
from app.integrations import direct_llm
from app.runtime.autonomous_activity import provider as transport
from app.runtime.autonomous_activity.combined_lanes import CombinedRoutineLane
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.character_activity_state import initialize_from_last_success
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("path,expected_caps,success", [
    ("healthy", [8192, 4096], True),
    ("recover", [8192, 16384, 4096], True),
    ("retry_truncated", [8192, 16384], False),
    ("stop_invalid", [8192], False),
    ("valid_max_tokens", [8192, 4096], True),
    ("lost_autonomy", [8192], False),
])
def test_actual_split_routine_recovers_once_then_publishes_at_most_once(monkeypatch, path, expected_caps, success):
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
    calls = []
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            fixture = _seed(db)
            ctx = _resident_context(db, fixture, run_id="bounded-routine", now=_utc(datetime(2026, 8, 10, 10, 5)))
            actor = fixture.world_character
            initialize_from_last_success(db, actor=actor)
            run = bind_run(db, actor=actor, activity_id=ctx.run_id)
            db.commit()
            shared = shared_input(ctx, actor, fixture.world)
            shared["now"] = ctx.run_started_at.isoformat()
            shared["retained_required_context"] = "x" * 40001
            async def guard(state):
                if not actor.autonomous_enabled:
                    raise ValueError("activity_scope_changed")
                return {}
            lane = CombinedRoutineLane(ctx, actor=actor, tracker=direct_llm.RunLlmTracker(max_calls=15),
                hybrid_service=None, guard=guard, ledger=RecoveryLedger(db, run.activity_id), policies=new_policies())
            async def sdk(**kwargs):
                calls.append(kwargs)
                node = kwargs["context"].node
                if node == "RoutineActionPlanner":
                    ordinal = sum(call["context"].node == node for call in calls)
                    if path in {"recover", "retry_truncated", "lost_autonomy"} and ordinal == 1:
                        if path == "lost_autonomy":
                            actor.autonomous_enabled = False
                            db.commit()
                        return direct_llm.DirectLlmResponse('{"scene_brief":', None, {}, "MAX_TOKENS")
                    if path == "retry_truncated":
                        return direct_llm.DirectLlmResponse('{"scene_brief":', None, {}, "MAX_TOKENS")
                    if path == "stop_invalid":
                        return direct_llm.DirectLlmResponse('{"scene_brief":', None, {}, "STOP")
                if node == "RoutineActionPlanner":
                    payload = {"scene_kind": "start", "scene_brief": "Begin the approved morning activity.",
                        "continuity_facts": [], "used_source_event_ids": [], "used_detail_keys": [],
                        "source_event_effects": [], "state_update": None, "state_source_refs": []}
                else:
                    payload = {"title": "Morning activity scene", "body": "The academy morning activity begins.",
                        "topic_signature": "morning-scene-1", "novelty_basis": "The approved activity starts today.",
                        "thought": "차근차근 진행한다."}
                return direct_llm.DirectLlmResponse(json.dumps(payload, ensure_ascii=False), None, {},
                    "MAX_TOKENS" if path == "valid_max_tokens" and node == "RoutineActionPlanner" else "STOP")
            monkeypatch.setattr(direct_llm, "generate_text", sdk)
            graph = build_lane("routine", lane.ports(), combined=True)
            initial = {"identity": {"activity_id": ctx.run_id, "contract_version": 2, **new_policies()}, "shared_context": shared}
            if success:
                result = await graph.ainvoke(initial)
                assert result["generation_mode"] == "split"
                assert result["result"]["public_action_count"] == 1
                assert db.scalar(select(func.count(Post.id))) == 1
                assert db.scalar(select(func.count(AgentPublicActionExecution.id)).where(
                    AgentPublicActionExecution.status == "succeeded")) == 1
                replay = await lane.execute(result)
                assert replay["executions"][0]["publish_result"]["public_action_count"] == 0
            else:
                with pytest.raises((direct_llm.DirectLlmError, ValueError)):
                    await graph.ainvoke(initial)
                assert db.scalar(select(func.count(Post.id))) == 0
                assert db.scalar(select(func.count(AgentPublicActionExecution.id))) == 0
            db.expire_all()
            metadata = db.get(ActivityGraphRun, ctx.run_id).result
            assert len(metadata.get("recovery_reservations", [])) == (1 if len(calls) > 1 and path.startswith(("recover", "retry")) else 0)
            assert len(metadata.get("normal_reservations", [])) == (2 if success else 1)
    asyncio.run(scenario())
    assert [call["max_output_tokens"] for call in calls] == expected_caps
    planner_calls = [call for call in calls if call["context"].node == "RoutineActionPlanner"]
    if len(planner_calls) == 2:
        assert planner_calls[0]["response_schema"] == planner_calls[1]["response_schema"]
        assert planner_calls[0]["system_prompt"] == planner_calls[1]["system_prompt"]
        assert planner_calls[1]["user_prompt"].startswith(planner_calls[0]["user_prompt"])
