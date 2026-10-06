"""Run the actual V2 provider and JSON parser using a deterministic SDK seam."""
import asyncio
from dataclasses import replace
import json

from app.domains.world_characters.contracts.social_io import LANE_IO
from app.integrations import direct_llm
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity import provider as transport


def probe(monkeypatch, ctx, target, *, thinking_level="medium", thought=None):
    calls = []
    ctx.credential.thinking_level = thinking_level
    ctx = replace(ctx)
    source = {"target_id": target.id, "counterpart_id": target.author_world_character_id,
        "source_ids": [target.id], "source_revisions": {target.id: "fixture"}, "allowed_actions": ["comment", "like"],
        "text": target.body, "topic_signature": target.topic_signature,
        "proposal_eligible": False, "activity_proposal": None, "parent_text": "Unused Feed parent"}
    async def sdk(**kwargs):
        calls.append(kwargs)
        raw = ({"decisions": [{"target_id": target.id, "action": "comment", "interaction_intent": "ordinary_comment",
            "comment_purpose": "question", "brief": "Ask about the note"}], "state_update": None}
            if len(calls) == 1 else {"replies": [{"task_id": "server-task", "body": "어떻게 배웠어?", "thought": thought}]})
        return direct_llm.DirectLlmResponse(text=json.dumps(raw), parsed=None, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", sdk)
    monkeypatch.setattr(transport, "_api_key", lambda context: "synthetic")
    tracker = RunLlmTracker(max_calls=3)
    provider = transport.ActivityProvider(ctx, tracker)
    provider.social_io_policy = LANE_IO
    context = {"now": ctx.run_started_at.isoformat()}
    if ctx.social_context is not None:
        context["relationships"] = ctx.social_context.snapshot.prompt_view()
    async def run():
        result = await provider.plan(lane="feed", context=context, candidates=[source])
        task = {"task_id": "server-task", "source": source, "brief": result["decisions"][0]["brief"],
                "writing_form": "reply", "proposal_response": None}
        written = await provider.write(lane="feed", context=context, assignments=[task])
        return result, written
    result, written = asyncio.run(run())
    return calls, tracker, result, written
