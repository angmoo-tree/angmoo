"""Actual runtime -> DirectLlm -> prepared request boundary, with zero outbound IO."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from app.contracts.sns_generation import new_generation_policies
from app.domains.world_characters.contracts.social_io import new_policies
from app.integrations import direct_llm
from app.providers.contracts import ProviderCapabilities, ProviderResponse, ProviderUsage, ProviderImagePart, ProviderToolDefinition
from app.providers.gemini import prepare_generate_request
from app.providers.input_budget import InputBudgetError
from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider, RecoveryLedger
from app.runtime.autonomous_activity.input_budget import SnsInputBudget
from runtime.test_sns_model_input_budget import Counter, profile, request, seeded_db


def test_representative_durable_graph_has_four_prepared_generation_calls(monkeypatch, tmp_path, deny_external_network):
    from app.runtime.autonomous_activity.checkpoints import activity_checkpointer, checkpoint_config
    from app.runtime.autonomous_activity.combined_selection import CombinedSelection
    from app.runtime.autonomous_activity.graph import build_autonomous_graph
    from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft
    from app.domains.routine_posts.schemas import RoutineDecisionOutput
    from app.providers.gemini import build_gemini_developer_response_schema
    from runtime.test_autonomous_activity_graph import lane_ports

    async def scenario():
        selection = {lane:{"selections":[{"target_id":f"{lane}-1"}]} for lane in ("inbox","feed")}
        social = lambda lane: {"decision":{"decisions":[{"target_id":f"{lane}-1","action":"like","brief":"Support"}]},"draft":{"replies":[]}}
        draft={"title":"Canonical scene", "body":"Canonical scene body", "topic_signature":"t"*350,
               "novelty_basis":"n"*800, "thought":"a"*350}
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,responses=[selection,social("inbox"),social("feed"),
            {"decision":{"scene_kind":"start","scene_brief":"A current scene"},"draft":draft}])
        effects=[];contexts={}; stopped=[False]
        async def shared(state):
            return {"shared_context":{"required":"x"*150000,"completed":[lane for lane in ("inbox","feed") if f"{lane}_result" in state]}}
        async def done(state): return {"result":{"status":"completed","paths":{lane:state[lane+"_result"] for lane in ("inbox","feed","routine")}}}
        lanes={}
        for lane in ("inbox","feed","routine"):
            port=lane_ports(lane,effects)
            async def load(state, lane=lane):
                return {} if lane!="routine" else {"candidates":[{"target_id":"routine","text":"Scene","allowed_actions":["post"]}]}
            async def build(state,lane=lane):
                contexts[lane]=state["shared_context"]["completed"]
                return {"decision_context":state["shared_context"]}
            async def plan(state,lane=lane):
                if lane!="routine": value=await p.plan(lane=lane,context=state["decision_context"],candidates=state["candidates"])
                else: value=await p.call(node="RoutineActionPlanner",lane="routine",system="Plan the current scene",
                    payload={"context":state["decision_context"]},schema=build_gemini_developer_response_schema(RoutineDecisionOutput),
                    validator=lambda v:RoutineDecisionOutput.model_validate(v).model_dump(),max_tokens=8192)
                return {"decision":value}
            async def validate(state,lane=lane): return {"assignments":[{"target_id":"routine"}] if lane=="routine" else []}
            async def write(state): return {"drafts":[parse_routine_draft(state["decision"]["provisional_draft"])]}
            async def execute(state,lane=lane):
                if lane=="routine" and not stopped[0]: stopped[0]=True;raise RuntimeError("exit_after_valid_draft")
                effects.append(lane+":execute")
                if lane=="routine":
                    normalized=state["drafts"][0]
                    assert [len(normalized[k]) for k in ("topic_signature","novelty_basis")]==[300,500]
                    assert normalized["_thought"]["truncated"] and len(normalized["_thought"]["text"])==280
                return {"executions":[{"status":"succeeded"}]}
            lanes[lane]=replace(port,load_candidates=load,build_context=build,plan=plan,validate=validate,write=write,execute=execute)
        async def prepare(_): return {"prepared_lanes":{lane:{"candidates":[{"target_id":f"{lane}-{i}","text":"Current source","allowed_actions":["like"],"source_ids":[f"{lane}-{i}"]} for i in range(2)]} for lane in ("inbox","feed")}}
        selectors=CombinedSelection({lane:SimpleNamespace(provider=p,delivery=lambda _:None) for lane in ("inbox","feed")},lanes)
        def graph(saver):return build_autonomous_graph(lanes=lanes,load_context=shared,refresh=shared,finalize=done,
            checkpointer=saver,prepare=prepare,choose_selection_mode=selectors.mode,combined_select=selectors.select)
        config=checkpoint_config(activity_id=row.activity_id)
        async with activity_checkpointer(tmp_path) as saver:
            with pytest.raises(RuntimeError,match="exit_after_valid_draft"):
                await graph(saver).ainvoke({"identity":{"world_id":"world",**new_generation_policies()}},config)
        async with activity_checkpointer(tmp_path) as saver:
            result=await graph(saver).ainvoke(None,config)
        assert result["result"]["status"]=="completed" and contexts=={"inbox":[],"feed":["inbox"],"routine":["inbox","feed"]}
        assert len(adapter.requests)==len(tracker.calls)==counter.calls==4 and counter.profiles==1
        assert [c["node"] for c in tracker.calls]==["CombinedTargetSelector","InboxDecisionDraft","FeedDecisionDraft","RoutineDecisionDraft"]
        assert all(req.prepared_request is not None for req in adapter.requests)
        db.refresh(row);assert len(row.result["normal_reservations"])==4 and not row.result.get("recovery_reservations")
        assert effects.count("routine:execute")==effects.count("feed:execute")==effects.count("inbox:execute")==1
        db.close()
    asyncio.run(scenario())


class SyntheticAdapter:
    capabilities = ProviderCapabilities(text=True, structured_json=True)
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
    async def generate_json(self, req):
        self.requests.append(req)
        assert req.prepared_request is not None
        payload = self.responses.pop(0)
        text, finish = payload if isinstance(payload, tuple) else (json.dumps(payload), "STOP")
        return ProviderResponse(text, None, ProviderUsage(42, 10, total_tokens=52), finish)


def runtime(monkeypatch, *, responses=(), count=None, observer=None):
    from app.runtime.autonomous_activity import provider as transport
    db, row = seeded_db()
    ctx = SimpleNamespace(db=db, run_id=row.activity_id, generation_thinking_level="medium", on_rate_limit_wait=None)
    adapter = SyntheticAdapter(responses)
    monkeypatch.setattr(direct_llm, "get_provider_adapter", lambda *_: adapter)
    async def no_wait(**_): pass
    monkeypatch.setattr(direct_llm._RATE_LIMITER, "wait_if_needed", no_wait)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic-never-sent")
    monkeypatch.setattr(transport, "_llm_context", lambda _, node, lane:
        direct_llm.DirectLlmCallContext("synthetic-credential", "actor", row.activity_id, node, lane, "google", request().model))
    tracker = direct_llm.RunLlmTracker(max_calls=15, observer=observer)
    counter = count or Counter()
    budget = SnsInputBudget(db, row.activity_id, counter=counter, notify=tracker._notify)
    provider = CombinedActivityProvider(ctx, tracker, ledger=RecoveryLedger(db,row.activity_id),
        policies={**new_policies(), **new_generation_policies()}, input_budget=budget)
    return db, row, provider, adapter, counter, tracker


def test_required_input_over_limit_has_no_generation_or_reservation(monkeypatch, deny_external_network):
    class Over(Counter):
        async def count(self, req, model):
            _, digest = await super().count(req,model)
            return 101, digest
    async def scenario():
        db,row,provider,adapter,counter,tracker=runtime(monkeypatch,count=Over())
        with pytest.raises(InputBudgetError,match="activity_input_budget_exceeded"):
            await provider.call(node="CombinedTargetSelector",lane="selector",system="s",payload={"required":"x"*150000},schema={},validator=lambda p:p,max_tokens=8192)
        db.refresh(row)
        assert not adapter.requests and not tracker.calls and not row.result.get("normal_reservations")
        assert counter.calls == 1 and row.result["input_budget_attempts"] == {"models_get":1,"count_tokens":1}
        db.close()
    asyncio.run(scenario())


def test_claim_change_after_completed_counter_is_recorded_but_never_generated(monkeypatch,deny_external_network):
    changed=[False];events=[]
    class Fenced(Counter):
        async def count(self,req,model):
            result=await super().count(req,model);changed[0]=True;return result
    async def scenario():
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,count=Fenced(),observer=lambda kind,value:events.append((kind,value)))
        async def guard(_):
            if changed[0]:raise ValueError("claim_changed")
        with pytest.raises(ValueError):
            await p.call(node="CombinedTargetSelector",lane="selector",system="s",payload={},schema={},validator=lambda v:v,max_tokens=8192,before_provider_request=guard)
        assert not adapter.requests and not tracker.calls and counter.calls==1
        metadata=[value for kind,value in events if kind=="input_budget"]
        assert [e["operation"] for e in metadata]==["models_get","count_tokens"]
        assert metadata[-1]["status"]=="admission_rejected" and not metadata[-1]["cache_hit"]
        db.refresh(row);assert not row.result.get("normal_reservations")
        db.close()
    asyncio.run(scenario())


def test_optional_omission_full_prepared_wire_and_caller_immutability(monkeypatch,deny_external_network):
    class Sized(Counter):
        async def count(self, req, model):
            _,digest=await super().count(req,model)
            source=json.loads(req.user_prompt)
            return (101 if source["context"]["today_activity"]["records"] else 42),digest
    async def scenario():
        events=[]
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,responses=[{"ok":True}],count=Sized(),observer=lambda kind,payload:events.append((kind,payload)))
        original={"context":{"required":"x"*64001,"today_activity":{"records":[{"id":"new"},{"id":"old"}]}}}
        before=deepcopy(original)
        assert await p.call(node="CombinedTargetSelector",lane="selector",system="s",payload=original,schema={},validator=lambda v:v,max_tokens=8192)=={"ok":True}
        sent=adapter.requests[0]; wire=sent.prepared_request.count_request(sent.model)
        digest=sha256(json.dumps(wire,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        db.refresh(row)
        receipt=row.result["input_budget_receipts"][digest]
        assert receipt["omissions"]=={"today_activity":2,"memory_packets":0} and receipt["admitted"]
        assert original==before and len(json.loads(sent.user_prompt)["context"]["required"])==64001
        assert counter.calls==3 and len(adapter.requests)==len(tracker.calls)==len(row.result["normal_reservations"])==1
        assert not row.result.get("recovery_reservations")
        assert "synthetic-never-sent" not in json.dumps(row.result)
        db.close()
    asyncio.run(scenario())


def test_retry_feedback_is_counted_and_does_not_reserve_failed_generation(monkeypatch,deny_external_network):
    class Feedback(Counter):
        async def count(self, req, model):
            _,digest=await super().count(req,model)
            return (42 if self.calls==1 else 101),digest
    async def scenario():
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,responses=[('{"decisions":[',"MAX_TOKENS")],count=Feedback())
        candidates=[{"target_id":"p","allowed_actions":["like"],"source_ids":["p"]}]
        with pytest.raises(InputBudgetError,match="activity_input_budget_exceeded"):
            await p.plan(lane="feed",context={"required":"x"*64001},candidates=candidates)
        db.refresh(row)
        assert len(adapter.requests)==len(tracker.calls)==1 and counter.calls==2
        assert adapter.requests[0].max_output_tokens==8192
        assert len(row.result["normal_reservations"])==1 and not row.result.get("recovery_reservations")
        assert sorted(r["output_tokens"] for r in row.result["input_budget_receipts"].values())==[8192,16384]
        db.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("task_count", [2,3])
def test_long_writer_recovery_is_one_request_for_three_exact_tasks(monkeypatch,deny_external_network,task_count):
    from runtime.test_activity_combined_contracts import assignment
    async def scenario():
        tasks=[{**assignment(f"p{i}"),"scope":"inbox"} for i in range(task_count)]
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,responses=[{"replies":[{"task_id":task["task_id"],"body":"hello","thought":"a"*350} for task in tasks]}])
        p.repairing=True
        result=await p.write(lane="inbox",context={"required":"x"*150000},assignments=tasks)
        db.refresh(row)
        assert [r["task_id"] for r in result["reply_task_results"]]==[t["task_id"] for t in tasks]
        assert all(r["_activity_thought"]["truncated"] and len(r["_activity_thought"]["text"])==280 for r in result["reply_task_results"])
        assert len(adapter.requests)==len(tracker.calls)==len(row.result["recovery_reservations"])==1
        assert not row.result.get("normal_reservations")
        db.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("failure",["count","profile","guard"])
def test_counter_and_guard_failure_do_not_submit_or_mark_delivery_uncertain(monkeypatch,deny_external_network,failure):
    class Failed(Counter):
        async def profile(self,req):
            if failure=="profile": raise InputBudgetError("model_budget_unsupported")
            return await super().profile(req)
        async def count(self,req,model):
            if failure=="count": raise InputBudgetError("activity_input_budget_unavailable")
            return await super().count(req,model)
    async def scenario():
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,count=Failed())
        states=[]
        delivery=SimpleNamespace(dispatched=lambda:states.append("dispatched"),delivered=lambda:states.append("delivered"),uncertain=lambda:states.append("uncertain"))
        async def guard(_):
            if failure=="guard": raise ValueError("scope_changed")
        with pytest.raises(ValueError):
            await p.call(node="CombinedTargetSelector",lane="selector",system="s",payload={},schema={},validator=lambda v:v,max_tokens=8192,delivery=delivery,before_provider_request=guard)
        assert not adapter.requests and not states and not tracker.calls
        db.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("observer_mode",["off","queue_full","write_failed"])
def test_observation_failure_does_not_change_normalization_or_generation(monkeypatch,deny_external_network,observer_mode):
    def noisy(kind,value):
        raise RuntimeError(observer_mode)
    async def scenario():
        payload={"title":"A visible scene","body":"The visible source remains complete.",
            "thought":"한"*350,"topic_signature":"日"*350,"novelty_basis":"새"*800}
        db,row,p,adapter,counter,tracker=runtime(monkeypatch,responses=[payload],
            observer=None if observer_mode=="off" else noisy)
        from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft
        value=await p.call(node="RoutineDecisionDraft",lane="routine",system="s",payload={"required":"x"*64001},
            schema={},validator=parse_routine_draft,max_tokens=8192)
        assert value["body"]==payload["body"] and value["_thought"]["text"]==payload["thought"][:280]
        assert value["topic_signature"]==payload["topic_signature"][:300] and value["novelty_basis"]==payload["novelty_basis"][:500]
        assert value["_auxiliary_normalization"]["thought"]["truncated"]
        db.refresh(row)
        assert len(adapter.requests)==counter.calls==len(tracker.calls)==len(row.result["normal_reservations"])==1
        assert len(row.result["input_budget_receipts"])==1 and not row.result.get("recovery_reservations")
        db.close()
    asyncio.run(scenario())


def test_prepared_count_includes_image_tool_and_exact_config(deny_external_network):
    req=request(image_parts=(ProviderImagePart("image/png",data=b"synthetic-image"),),
        tools=(ProviderToolDefinition("lookup","Find source",{"type":"object","properties":{"id":{"type":"string"}}}),),require_tool_call=True,
        response_schema=None,response_mime_type=None)
    prepared=prepare_generate_request(req)
    wire=prepared.count_request(req.model)["generateContentRequest"]
    assert any("inlineData" in part for content in wire["contents"] for part in content["parts"])
    assert wire["tools"] and wire["toolConfig"] and wire["systemInstruction"] and wire["generationConfig"]
