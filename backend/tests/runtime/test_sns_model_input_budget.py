import asyncio
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.orm import Session

from app.contracts.sns_generation import new_generation_policies, read_generation_policies
from app.integrations.gemini_input_budget import GeminiModelTokenCounter
from app.providers.contracts import ProviderRequest
from app.providers.gemini import prepare_generate_request
from app.providers.input_budget import InputBudgetError, ModelTokenProfile
from app.runtime.autonomous_activity.generation_contracts import generation_mode
from app.runtime.autonomous_activity.combined_selection import CombinedSelection
from app.runtime.autonomous_activity.input_budget import SnsInputBudget, omit_optional_unit


def request(**kwargs):
    return replace(ProviderRequest("fake-never-sent", "gemini-3.1-flash-lite", "system", "user", 8192, 10,
        response_schema={"type": "object", "properties": {"body": {"type": "string"}}}, response_mime_type="application/json", thinking_level="medium"), **kwargs)


def profile(**kwargs):
    return replace(ModelTokenProfile("google", request().model, "v1", 100, 16384,
        "gemini-models-countTokens.v1", "https://ai.google.dev/api/models", "2026-10-05"), **kwargs)


@pytest.mark.parametrize("input_tokens,output_tokens,allowed", [(99,8192,True),(100,16384,True),(101,8192,False)])
def test_separate_model_input_output_limits(input_tokens, output_tokens, allowed):
    assert profile().permits(input_tokens, output_tokens) is allowed


@pytest.mark.parametrize("kwargs", [{"input_limit": 0},{"input_limit": True},{"output_limit": None},{"version": ""}])
def test_unknown_profile_never_guesses_limit(kwargs):
    with pytest.raises(InputBudgetError):
        profile(**kwargs)


def test_shared_context_reserves_output_only_when_declared():
    assert not profile(context_limit=100).permits(90,20)
    with pytest.raises(InputBudgetError, match="unsupported"):
        profile().permits(0,16385)


@pytest.mark.parametrize("size", [39999,40000,40001,55999,56000,56001,63999,64000,64001,150000])
def test_new_combined_policy_and_legacy_boundaries(size):
    state={"decision_context":{"text":"x"*size},"identity":new_generation_policies()}
    assert asyncio.run(generation_mode(state))["generation_mode"] == "combined"
    if size>40000:
        assert asyncio.run(generation_mode({**state,"identity":{}}))["generation_mode"] == "split"
    selector=CombinedSelection({}, {})
    state.update(shared_context={"text":"x"*size},prepared_lanes={})
    assert asyncio.run(selector.mode(state))["selection_mode"] == "combined"


def test_incomplete_policy_is_not_silently_upgraded():
    with pytest.raises(ValueError):
        read_generation_policies({"sns_generation_policy":"sns-combined-only.v1"})
    assert read_generation_policies({}).sns_generation_policy is None


@pytest.mark.parametrize("text", ["a"*100,"한"*100,"🙂"*100,'{"x":"'+"a"*92+'"}'])
@pytest.mark.parametrize("tokens,allowed", [(100,True),(101,False)])
def test_equal_codepoint_input_uses_counter_result_not_language_or_character_size(text,tokens,allowed):
    class Exact(Counter):
        async def count(self,req,model):
            _,digest=await super().count(req,model)
            assert req.user_prompt==text
            return tokens,digest
    async def scenario():
        db,row=seeded_db();counter=Exact()
        async def guard(): pass
        _,accepted=await SnsInputBudget(db,row.activity_id,counter=counter).admit(request(user_prompt=text),guard=guard,omissions={})
        assert accepted is allowed and counter.calls==1
        assert not row.result.get("normal_reservations")
        db.close()
    assert len(text)==100
    asyncio.run(scenario())


@pytest.mark.parametrize("change", [{"system_prompt":"different"},{"user_prompt":"user feedback"},{"max_output_tokens":16384}, {"response_schema":{"type":"object","properties":{"changed":{"type":"number"}}}}])
def test_full_prepared_request_includes_system_schema_feedback_and_config(change):
    wire=prepare_generate_request(request()).count_request(request().model)
    assert wire["generateContentRequest"]["systemInstruction"]["parts"][0]["text"]=="system"
    assert wire["generateContentRequest"]["generationConfig"]["responseJsonSchema"]
    assert wire != prepare_generate_request(request(**change)).count_request(request().model)


def test_official_http_adapter_full_count_and_one_attempt(deny_external_network):
    calls=[]
    def http(req):
        calls.append(req)
        if req.method=="GET":
            return httpx.Response(200,json={"name":"models/"+request().model,"version":"001", "inputTokenLimit":100,
                "outputTokenLimit":16384,"supportedGenerationMethods":["generateContent"]})
        assert json.loads(req.content)["generateContentRequest"]["generationConfig"]["responseJsonSchema"]
        return httpx.Response(200,json={"totalTokens":42})
    async def scenario():
        port=GeminiModelTokenCounter(transport=httpx.MockTransport(http))
        p=await port.profile(request())
        assert (await port.count(request(),p))[0]==42
    asyncio.run(scenario())
    assert len(calls)==2


@pytest.mark.parametrize("methods", [None, "generateContent", {"generateContent": True}, ["generateContent", 1], []])
def test_unknown_profile_methods_are_explicitly_unsupported(methods, deny_external_network):
    calls=[]
    def http(req):
        calls.append(req)
        return httpx.Response(200,json={"name":"models/"+request().model,"version":"001",
            "inputTokenLimit":100,"outputTokenLimit":16384,"supportedGenerationMethods":methods})
    async def scenario():
        port=GeminiModelTokenCounter(transport=httpx.MockTransport(http))
        with pytest.raises(InputBudgetError, match="model_budget_unsupported"):
            await port.profile(request())
    asyncio.run(scenario())
    assert len(calls)==1


@pytest.mark.parametrize("response", [httpx.Response(429),httpx.Response(302,headers={"location":"https://other.example"}), httpx.Response(200,json={"totalTokens":True})])
def test_count_failure_never_zero_or_redirect_or_retry(response,deny_external_network):
    calls=[]
    def http(req):
        calls.append(req)
        return response
    async def scenario():
        port=GeminiModelTokenCounter(transport=httpx.MockTransport(http))
        with pytest.raises(InputBudgetError):
            await port.count(request(),profile())
    asyncio.run(scenario())
    assert len(calls)==1


def seeded_db():
    from social.test_feed_reaction_intent import _engine, _seed
    from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
    from app.domains.world_characters.service.activity_engines import bind_run
    db=Session(_engine(),expire_on_commit=False)
    ctx,_=_seed(db,with_candidate=False)
    actor=db.get(WorldCharacter,db.get(CharacterActiveWorld,ctx.character.id).world_character_id)
    row=bind_run(db,actor=actor,activity_id="budget-run")
    db.commit()
    return db,row


class Counter:
    calls=0
    profiles=0
    async def profile(self, req):
        self.profiles+=1
        return profile()
    async def count(self, req, model):
        self.calls+=1
        body=prepare_generate_request(req).count_request(req.model)
        return 42,sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def test_budget_cache_is_run_scoped_and_durable_receipts_have_no_prompt_or_key():
    async def scenario():
        db,row=seeded_db()
        counter=Counter()
        budget=SnsInputBudget(db,row.activity_id,counter=counter)
        guards=[]
        async def guard(): guards.append(True)
        for req in (request(),request(),request(user_prompt="feedback")):
            checked,allowed=await budget.admit(req,guard=guard,omissions={})
            assert allowed and checked.prepared_request is not None
        assert counter.profiles==1 and counter.calls==2 and len(guards)>=8
        db.refresh(row)
        assert len(row.result["input_budget_receipts"])==2
        assert "fake-never-sent" not in json.dumps(row.result)
        assert "feedback" not in json.dumps(row.result)
        counter2=Counter()
        await SnsInputBudget(db,row.activity_id,counter=counter2).admit(request(),guard=guard,omissions={})
        assert counter2.profiles==counter2.calls==1
        db.close()
    asyncio.run(scenario())


def test_counter_cache_receipts_and_network_attempts_remain_bounded_on_resume():
    async def scenario():
        db,row=seeded_db();counter=Counter();budget=SnsInputBudget(db,row.activity_id,counter=counter)
        async def guard(): pass
        for index in range(36):
            assert (await budget.admit(request(user_prompt=f"required-{index}"),guard=guard,omissions={}))[1]
        db.refresh(row)
        assert len(budget.cache)==len(row.result["input_budget_receipts"])==32
        assert row.result["input_budget_attempts"]=={"models_get":1,"count_tokens":36}
        row.result={**row.result,"input_budget_attempts":{"models_get":1,"count_tokens":255}};db.commit()
        resumed=Counter()
        with pytest.raises(InputBudgetError,match="activity_input_budget_unavailable"):
            await SnsInputBudget(db,row.activity_id,counter=resumed).admit(request(),guard=guard,omissions={})
        assert resumed.profiles==resumed.calls==0
        assert row.result["input_budget_attempts"]=={"models_get":1,"count_tokens":255}
        db.close()
    asyncio.run(scenario())


def test_resumed_model_revision_cannot_silently_replace_saved_limits():
    class Changed(Counter):
        async def profile(self,req):
            await super().profile(req)
            return profile(input_limit=1000,version="v2")
    async def scenario():
        db,row=seeded_db()
        async def guard(): pass
        await SnsInputBudget(db,row.activity_id,counter=Counter()).admit(request(),guard=guard,omissions={})
        original=dict(row.result["model_token_profile"]);counter=Changed()
        with pytest.raises(InputBudgetError,match="activity_model_profile_changed"):
            await SnsInputBudget(db,row.activity_id,counter=counter).admit(request(),guard=guard,omissions={})
        db.refresh(row);assert row.result["model_token_profile"]==original and counter.profiles==1 and counter.calls==0
        db.close()
    asyncio.run(scenario())


def test_lost_claim_after_count_never_admits_or_records_success():
    async def scenario():
        db,row=seeded_db()
        count=0
        async def guard():
            nonlocal count
            count+=1
            if count==4: raise ValueError("claim_lost")
        budget=SnsInputBudget(db,row.activity_id,counter=Counter())
        with pytest.raises(ValueError,match="claim_lost"):
            await budget.admit(request(),guard=guard,omissions={})
        db.refresh(row)
        assert not row.result.get("input_budget_receipts")
        db.close()
    asyncio.run(scenario())


def test_whole_optional_omission_preserves_correction_group_and_required_sources():
    context={"source":{"text":"required"}, "today_activity":{"records":[{"id":"new"},{"id":"old"}]},
        "memories":{"target":{"packets":[{"id":"original"},{"id":"correction"}]}}}
    omissions={"today_activity":0,"memory_packets":0}
    assert omit_optional_unit(context,omissions)
    assert context["today_activity"]["records"]==[{"id":"new"}]
    assert omit_optional_unit(context,omissions)
    assert omit_optional_unit(context,omissions)
    assert context["memories"]["target"]["packets"]==[]
    assert context["source"]["text"]=="required"
    assert not omit_optional_unit(context,omissions)
