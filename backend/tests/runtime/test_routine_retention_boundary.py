"""Actual V2 parent + split Routine + final checkpoint failure, with a fake SDK."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import func, select

from app.domains.routines.models import AgentPublicActionExecution, AgentSlot
from app.domains.social.models.posts import Post
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import RETENTION_KEY
from app.domains.world_characters.service.activity_engines import bind_run
from app.domains.world_characters.service.checkpoint_retention import eligible
from app.integrations import direct_llm
from app.runtime.autonomous_activity import execution, provider
from app.runtime.autonomous_activity.binding import ActivityRuntimeBinding, register, unregister
from app.runtime.autonomous_activity.checkpoint_maintenance import CheckpointMaintenance
from retention_support import database
from routine_posts.test_runtime import _seed, _resident_context, _utc

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("failure", ["sdk_write", "confirmation"])
def test_split_routine_completion_is_not_reexecuted_after_final_storage_failure(tmp_path, monkeypatch, failure):
    from app.config import settings
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from app.domains.world_characters.service import checkpoint_retention
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    monkeypatch.setattr(provider, "_api_key", lambda _: "synthetic")
    original_input = execution.shared_input
    # A persisted legacy run below retains the old mode threshold. New runs
    # always use combined; no mode, graph, guard or publication is replaced.
    monkeypatch.setattr(execution, "shared_input", lambda *args, **kwargs: {
        **original_input(*args, **kwargs), "retained_required_context": "x" * 40001})
    calls = []
    async def sdk(**kwargs):
        calls.append(kwargs)
        node = kwargs["context"].node
        if node == "RoutineActionPlanner":
            if sum(call["context"].node == node for call in calls) == 1:
                return direct_llm.DirectLlmResponse('{"scene_brief":', None, {}, "MAX_TOKENS")
            payload = {"scene_kind": "start", "scene_brief": "Begin the approved morning activity.",
                "continuity_facts": [], "used_source_event_ids": [], "used_detail_keys": [],
                "source_event_effects": [], "state_update": None, "state_source_refs": []}
        elif node == "RoutineWriter":
            payload = {"title": "Morning activity", "body": "The academy morning activity begins.",
                "topic_signature": "morning-scene-1", "novelty_basis": "The approved activity starts today.",
                "thought": "차근차근 진행한다."}
        else:
            pytest.fail("unexpected request: " + node)
        return direct_llm.DirectLlmResponse(json.dumps(payload, ensure_ascii=False), None, {}, "STOP")
    monkeypatch.setattr(direct_llm, "generate_text", sdk)
    if failure == "sdk_write":
        original_write = AsyncSqliteSaver.aput
        async def write(self, config, value, metadata, versions):
            final = value.get("channel_values", {}).get("result", {})
            if isinstance(final, dict) and final.get("engine") == "personalized_graph_v2":
                raise OSError("synthetic final SDK write")
            return await original_write(self, config, value, metadata, versions)
        monkeypatch.setattr(AsyncSqliteSaver, "aput", write)
    else:
        monkeypatch.setattr(checkpoint_retention, "confirm_graph",
            lambda *a: (_ for _ in ()).throw(OSError("synthetic confirmation")))
    async def scenario():
        engine, factory, _ = database(tmp_path, seed=False)
        binding = ActivityRuntimeBinding(None, tmp_path)
        register(binding)
        try:
            with factory() as db:
                fixture = _seed(db)
                ctx = _resident_context(db, fixture, run_id="routine-final-boundary",
                    now=_utc(datetime(2026, 8, 10, 10, 5)))
                from app.domains.social.contracts.search_state import SocialSearchState
                from app.runtime.search import CallbackSearchIndexAdapter
                ctx = replace(ctx, social_search_state=SocialSearchState.READY,
                    social_search_index=CallbackSearchIndexAdapter(
                        upsert=lambda *a, **k: None, remove=lambda *a, **k: None,
                        search=lambda *a, **k: []))
                actor = fixture.world_character
                # The original Routine-only seed intentionally has no Feed
                # runtime. This whole-parent fixture enables its existing,
                # approved keyword path without creating any Feed candidate.
                actor.feed_runtime_mode = "keyword_search_v1"
                from app.domains.world_characters.models import WorldCommunityProfile
                from social.test_feed_reaction_intent import _action_profile
                profile = db.scalar(select(WorldCommunityProfile).where(WorldCommunityProfile.world_character_id == actor.id))
                profile.search_keywords = ["alchemy", "library", "runes", "potions", "academy", "garden", "research", "friendship"]
                profile.core_interests = ["alchemy", "runes", "potions"]
                profile.adjacent_interests = ["library", "garden"]
                profile.action_profile = _action_profile()
                db.add(AgentSlot(agent_id=ctx.agent_id, status="running", locked_by_run_id=ctx.run_id,
                    assigned_character_id=ctx.character.id, assigned_user_id=ctx.user_id,
                    lease_expires_at=datetime.now(UTC) + timedelta(minutes=10)))
                run = bind_run(db, actor=actor, activity_id=ctx.run_id)
                # Reconstruct the saved pre-upgrade result: only the new
                # generation-policy keys were absent in those existing runs.
                from app.contracts.sns_generation import POLICY_KEYS, read_generation_policies
                run.result = {key: value for key, value in run.result.items() if key not in POLICY_KEYS}
                db.commit()
                assert bind_run(db, actor=actor, activity_id=ctx.run_id) is run
                assert read_generation_policies(run.result).sns_generation_policy is None
                if failure == "sdk_write":
                    with pytest.raises(OSError, match="final SDK"):
                        await execution.run_personalized_activity(ctx, actor=actor, run=run)
                else:
                    await execution.run_personalized_activity(ctx, actor=actor, run=run)
                db.expire_all()
                assert run.status == "completed" and run.result["paths"]["routine"]["public_action_count"] == 1, run.result["paths"]
                assert run.result[RETENTION_KEY]["graph_complete"] is False
                assert len(run.result["recovery_reservations"]) == 1
                assert len(run.result["normal_reservations"]) == 2
                assert not eligible(run, now=datetime.now(UTC) + timedelta(days=2))
                original_result, finished = dict(run.result), run.finished_at
                actor.autonomous_enabled = False
                db.delete(db.get(AgentSlot, ctx.agent_id)); db.commit()
                unregister(binding)
                task = CheckpointMaintenance(data_root=tmp_path, session_factory=factory,
                    clock=lambda: datetime.now(UTC) + timedelta(days=2))
                assert (await task.cycle()).get("pruned", 0) == 0
                from app.runtime.autonomous_activity.checkpoints import activity_checkpointer
                async with activity_checkpointer(tmp_path) as saver:
                    assert [item async for item in saver.alist({"configurable": {"thread_id": "activity:" + ctx.run_id}})]
                monkeypatch.setattr(provider.ActivityProvider, "__init__",
                    lambda *a, **k: pytest.fail("provider recreated"))
                first = await execution.run_personalized_activity(ctx, actor=actor, run=run)
                second = await execution.run_personalized_activity(ctx, actor=actor, run=run)
                assert first == second and first["publish_result"]["public_action_count"] == 1
                assert run.result == original_result and run.finished_at == finished
                assert db.scalar(select(func.count(Post.id))) == 1
                assert db.scalar(select(func.count(AgentPublicActionExecution.id)).where(
                    AgentPublicActionExecution.status == "succeeded")) == 1
        finally:
            unregister(binding); engine.dispose()
    asyncio.run(scenario())
    assert [call["max_output_tokens"] for call in calls] == [8192, 16384, 4096]
