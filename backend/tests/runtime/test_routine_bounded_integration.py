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


@pytest.mark.parametrize("interrupt", [False, True])
def test_new_combined_long_auxiliary_publish_and_reopen_are_one_physical_call(monkeypatch, tmp_path, interrupt):
    from app.contracts.sns_generation import new_generation_policies
    from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
    from app.runtime.autonomous_activity.graph import build_autonomous_graph
    from app.runtime.autonomous_activity.input_budget import SnsInputBudget
    from runtime.test_sns_budget_transport import SyntheticAdapter
    from runtime.test_sns_model_input_budget import Counter, request
    from runtime.test_autonomous_activity_graph import lane_ports
    from dataclasses import replace
    from app.config import settings
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic-not-sent")
    monkeypatch.setattr(transport, "_llm_context", lambda ctx,node,lane:direct_llm.DirectLlmCallContext(
        "synthetic", "actor", ctx.run_id, node, lane, "google", request().model))
    async def no_wait(**_): pass
    monkeypatch.setattr(direct_llm._RATE_LIMITER,"wait_if_needed",no_wait)
    adapter=SyntheticAdapter([{"decision":{"scene_kind":"start","scene_brief":"Begin the approved current activity",
        "continuity_facts":[],"used_source_event_ids":[],"used_detail_keys":[],"source_event_effects":[],
        "state_update":None,"state_source_refs":[]},"draft":{"title":"A canonical current scene",
        "body":"The approved activity starts in the academy today.","thought":"한"*350,
        "topic_signature":"일"*350,"novelty_basis":"새"*800}}])
    monkeypatch.setattr(direct_llm,"get_provider_adapter",lambda *_:adapter)
    async def scenario():
        with Session(_engine(),expire_on_commit=False) as db:
            fixture=_seed(db)
            ctx=_resident_context(db,fixture,run_id="new-combined-normalized",now=_utc(datetime(2026,8,10,10,5)))
            initialize_from_last_success(db,actor=fixture.world_character)
            run=bind_run(db,actor=fixture.world_character,activity_id=ctx.run_id);db.commit()
            policies={**new_policies(),**new_generation_policies()}
            tracker=direct_llm.RunLlmTracker(max_calls=15);counter=Counter()
            budget=SnsInputBudget(db,ctx.run_id,counter=counter)
            stopped=[False];shared=shared_input(ctx,fixture.world_character,fixture.world)
            shared.update(now=ctx.run_started_at.isoformat(),retained_required_context="x"*64001)
            async def guard(state):
                if state.get("stage")=="Execute" and interrupt and not stopped[0]:
                    stopped[0]=True;raise RuntimeError("exit_before_canonical_publish")
                return {}
            lane=CombinedRoutineLane(ctx,actor=fixture.world_character,tracker=tracker,hybrid_service=None,
                guard=guard,ledger=RecoveryLedger(db,ctx.run_id),policies=policies,input_budget=budget)
            async def load(_):return {"shared_context":shared}
            async def empty(_):return {"candidates":[]}
            async def prepare(_):return {"prepared_lanes":{key:{"candidates":[],"selections":[]} for key in ("inbox","feed")}}
            async def mode(_):return {"selection_mode":"combined"}
            async def selected(_):return {}
            async def done(state):return {"result":state["routine_result"]}
            def graph(saver):
                others={key:replace(lane_ports(key,[]),guard=guard,load_candidates=empty) for key in ("inbox","feed")}
                return build_autonomous_graph(lanes={**others,"routine":lane.ports()},load_context=load,refresh=load,
                    finalize=done,checkpointer=saver,prepare=prepare,choose_selection_mode=mode,combined_select=selected)
            config=checkpoint_config(activity_id=ctx.run_id)
            identity={"activity_id":ctx.run_id,"world_id":fixture.world.id,"actor_id":fixture.world_character.id,
                      "contract_version":2,**policies}
            async with activity_checkpointer(tmp_path) as saver:
                if interrupt:
                    with pytest.raises(RuntimeError,match="exit_before_canonical_publish"):
                        await graph(saver).ainvoke({"identity":identity},config)
                else:result=await graph(saver).ainvoke({"identity":identity},config)
            if interrupt:
                async with activity_checkpointer(tmp_path) as saver:result=await graph(saver).ainvoke(None,config)
            assert result["result"]["public_action_count"]==1
            assert len(adapter.requests)==len(tracker.calls)==counter.calls==1 and counter.profiles==1
            assert tracker.calls[0]["node"]=="RoutineDecisionDraft" and adapter.requests[0].max_output_tokens==8192
            post=db.scalar(select(Post));assert post.title=="A canonical current scene" and len(post.topic_signature)==300
            execution=db.scalar(select(AgentPublicActionExecution));assert execution.status=="succeeded"
            # Receipts are persisted on the canonical execution, not inferred from UI.
            assert execution.result["auxiliary_normalization"]["thought"]["truncated"]
            assert execution.result["auxiliary_normalization"]["novelty_basis"]["rendered_chars"]==800
            assert len(post.novelty_basis)==500
            assert db.scalar(select(func.count(Post.id)))==1 and db.scalar(select(func.count(AgentPublicActionExecution.id)))==1
            db.refresh(run);assert len(run.result["normal_reservations"])==1 and not run.result.get("recovery_reservations")
            # The exact canonical source is read by all three UI-facing services.
            # Owner identity is synthetic and is created only after publication.
            from model_fixture_support import models
            from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
            from app.domains.social.service.manual_feed import list_owner_world_feed, get_owner_world_post_thread
            from app.domains.social.service.world_profile import WorldSocialProfileService
            from app.domains.social.contracts.profile_activity import WorldCharacterSocialProfileQuery
            from app.domains.social.contracts.writes import OwnerLikeCommand
            from app.runtime.social.manual_feed_references import RuntimeManualFeedReferences
            from app.runtime.social.profile_references import RuntimeProfileReferences
            from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
            db.add(models.InstallationIdentity(singleton_key="local-installation",
                installation_id="synthetic-routine-installation", owner_user_id=fixture.user.id,
                bootstrap_state="claimed", local_label="synthetic", claimed_at=datetime.now(UTC)))
            db.get(models.WorldMembership,fixture.world_character.membership_id).role="owner"
            db.commit()
            owner=OwnerControlledIdentityService(db).ensure(world_id=fixture.world.id,current_user_id=fixture.user.id)
            liked=SqlAlchemySocialWriteUnitOfWork(db).set_owner_like(
                OwnerLikeCommand(fixture.world.id,fixture.user.id,post.id,True))
            assert liked.viewer_like_state=="liked" and liked.owner_world_character_id==owner.world_character_id
            feed=list_owner_world_feed(db,references=RuntimeManualFeedReferences(db),world_id=fixture.world.id,current_user_id=fixture.user.id)
            detail=get_owner_world_post_thread(db,references=RuntimeManualFeedReferences(db),world_id=fixture.world.id,post_id=post.id,current_user_id=fixture.user.id)
            profile=WorldSocialProfileService(db,references=RuntimeProfileReferences(db)).read(
                WorldCharacterSocialProfileQuery(fixture.world.id,fixture.world_character.id,fixture.user.id))
            assert {feed.items[0].id,detail.selected_post.id,profile.items[0].id}=={post.id}
            assert all(value.body==post.body and value.viewer_like_state=="liked" and value.like_count==1
                for value in (feed.items[0],detail.selected_post,profile.items[0]))
            assert db.scalar(select(func.count(Post.id)))==db.scalar(select(func.count(AgentPublicActionExecution.id)))==1
            assert len(adapter.requests)==counter.calls==1
    asyncio.run(scenario())


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
