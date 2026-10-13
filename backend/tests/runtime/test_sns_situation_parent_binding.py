"""Actual final payload capture and pre-provider rejection, including memory OFF."""
import asyncio
import json
from hashlib import sha256
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import Session
from runtime.test_activity_combined_delivery import fixture
from social.test_feed_reaction_intent import _engine
from memory.test_situation_delivery_recovery import durable_stack
from memory.test_situation_parent_binding_recovery import historic
from memory.test_activity_situation_receipt import enabled
from app.runtime.autonomous_activity import provider as transport
from app.runtime.autonomous_activity.situation_memory import freeze_social_input
from app.domains.memory.repository.situation_validation import restore_context


def test_new_capture_uses_parent_id_not_action_target(durable_stack):
    db, scope, setting, memory = durable_stack
    row, parent, child = historic(db, scope)
    context = restore_context(db, row)
    payload = {"context": {"today_activity": {"records": [{
        "source_type": "post", "source_id": child.id, "source_post_id": child.id,
        "target_post_id": "situation-post", "body": child.body, "parent_body": parent.body,
        "parent_post_id": parent.id, "root_post_id": parent.id,
    }]}}}
    transmitted = json.dumps(payload, ensure_ascii=False)
    manifest = freeze_social_input(SimpleNamespace(db=db, run_id="synthetic-parent"), context.snapshot,
        node="FeedDecisionDraft", payload=payload, transmitted=transmitted, state={})
    captured = next(source for source in manifest.sources if source.payload_path.endswith("/parent_body"))
    assert captured.source_id == parent.id and captured.source_id != payload["context"]["today_activity"]["records"][0]["target_post_id"]
    assert captured.delivery_payload_digest == manifest.payload_digest == sha256(transmitted.encode()).hexdigest()
    assert captured.ranges == captured.delivered_ranges == ((0, len(parent.body)),)


@pytest.mark.parametrize("memory_on", [False, True])
def test_missing_parent_id_prevents_provider_dispatch(monkeypatch, memory_on, deny_external_network):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _, post = fixture(db)
            if memory_on: lane.provider.situation_snapshot = enabled(db, lane)
            state.update(await lane.load(state)); lane.provider.situation_state = state
            calls = []
            async def generate(**kwargs): calls.append(kwargs); raise AssertionError("must reject before provider")
            monkeypatch.setattr(transport, "generate_json", generate)
            monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
            monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: None)
            with pytest.raises(ValueError, match="parent_identity_invalid"):
                await lane.provider.plan(lane="feed", context={"today_activity": {"records": [
                    {"source_post_id": post.id, "parent_body": "orphaned parent input"}
                ]}}, candidates=state["candidates"])
            assert calls == []
    asyncio.run(scenario())
