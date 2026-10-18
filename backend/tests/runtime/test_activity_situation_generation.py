"""Situation output stays in existing calls, after the independently valid base."""
import asyncio
import json
from dataclasses import asdict
from hashlib import sha256
import pytest
from sqlalchemy.orm import Session
from runtime.test_activity_combined_delivery import fixture
from social.test_feed_reaction_intent import _engine
from memory.test_activity_situation_receipt import enabled
from app.runtime.autonomous_activity import provider as transport
from app.domains.memory.policies.situation_output import parse_description
from app.runtime.autonomous_activity.situation_memory import freeze_social_input


@pytest.mark.parametrize("description,order,status", [("안부를 살펴보고 공감했다.",True,"valid"), (None,True,"missing"), (42,True,"invalid"), ("안부를 나눴다.",False,"output_order_invalid")])
def test_combined_existing_call_preserves_base_with_bad_description(monkeypatch, description, order, status):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _, post = fixture(db)
            lane.provider.situation_snapshot = enabled(db, lane)
            state.update(await lane.load(state))
            lane.provider.situation_state = state
            calls = []
            async def generate(**kwargs):
                calls.append(kwargs)
                schema = kwargs["response_schema"]
                assert list(schema["properties"])[-1] == "situations"
                payload = {"decision": {"decisions": [{"target_id": post.id, "action": "like", "brief": "공감"}],
                    "state_update": None, "relationship_metrics": []}, "draft": {"replies": []}}
                situation = [{"target_id": post.id, "description": description}]
                payload = {**payload, "situations": situation} if order else {"situations": situation, **payload}
                return kwargs["validator"](payload)
            monkeypatch.setattr(transport, "generate_json", generate)
            monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
            monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: None)
            result = await lane.provider.plan(lane="feed", context={}, candidates=state["candidates"])
            assert result["decisions"][0]["action"] == "like"
            assert result["_situations"][post.id]["status"] == status
            assert len(calls) == 1 and calls[0]["max_output_tokens"] >= 8192
            assert "Use Korean for this description" in calls[0]["system_prompt"]
            assert lane.provider.situation_snapshot.memory_search_locale == "ko-KR"
            assert result["_situation_manifest"]["payload_digest"] == sha256(calls[0]["user_prompt"].encode()).hexdigest()
            assert [r["source_id"] for r in result["_situation_manifest"]["sources"]] == [post.id]
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["split", "combined"])
def test_separate_or_recovery_writer_owns_final_description_and_manifest(monkeypatch, mode):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _, post = fixture(db)
            snapshot = enabled(db, lane)
            lane.provider.situation_snapshot = snapshot
            state.update(await lane.load(state))
            payload = {"selected_targets": state["candidates"], "context": {}}
            manifest = freeze_social_input(lane.ctx, snapshot, node="FeedDecisionDraft", payload=payload,
                transmitted=json.dumps(payload), state=state)
            state.update(generation_mode=mode, selections=[{"target_id": post.id}], decision_context={}, decision_input_receipt={})
            state["decision"] = {"decisions": [{"target_id": post.id, "action": "comment", "brief": "응원",
                "interaction_intent": "ordinary_comment", "comment_purpose": "empathy"}],
                "provisional_draft": {"replies": [{"target_id": post.id}]},
                "_situation_manifest": manifest.to_dict(),
                "_situations": {post.id: asdict(parse_description("거절된 이전 설명", target_key=post.id))}}
            state.update(await lane.validate(state))
            calls = []
            async def generate(**kwargs):
                calls.append(kwargs)
                assert list(kwargs["response_schema"]["properties"])[-1] == "situations"
                return kwargs["validator"]({"replies": [{"task_id": state["assignments"][0]["task_id"], "body": "오늘도 좋은 하루 보내세요."}],
                    "situations": [{"target_id": post.id, "description": "안부에 답글을 남기며 응원했다."}]})
            monkeypatch.setattr(transport, "generate_json", generate)
            monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
            monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: None)
            output = await lane.write(state)
            final = output["decision"]["_situation_overrides"][post.id]
            assert final["draft"]["status"] == "valid"
            assert final["draft"]["description"] != "거절된 이전 설명"
            assert final["normalized"]["replies"][0]["body"] == output["drafts"][0]["body"]
            assert final["manifest"]["payload_digest"] == sha256(calls[0]["user_prompt"].encode()).hexdigest()
            assert len(calls) == 1
    asyncio.run(scenario())
