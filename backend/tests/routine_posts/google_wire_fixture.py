"""Synthetic final Routine request, assembled through the actual runtime.

No external request is made here. The caller decides whether to use a stub or
the explicitly authorized provider harness. No application database is opened.
"""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.orm import Session
from app.config import settings
from app.contracts.routine_output import COMPACT_EFFECT_WIRE
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.domains.world_characters.service.activity_engines import bind_run
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.combined_lanes import CombinedRoutineLane
from app.runtime.autonomous_activity.combined_provider import RecoveryLedger
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.domains.memory.policies.situation_generation import TARGET_OUTPUT_REVISION
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc


class CapturedRequest(BaseException):
    pass


@contextmanager
def routine_request(count, *, profile=COMPACT_EFFECT_WIRE):
    engine = _engine()
    try:
        with Session(engine, expire_on_commit=False) as db, \
             patch.object(settings, "DAILY_PREPARATION_ENABLED", False), \
             patch.object(settings, "ROUTINE_OUTPUT_POLICY", "enum_preserved_v1"), \
             patch.object(settings, "ACTIVITY_THOUGHT_POLICY", "thought_v1"):
            fixture = _seed(db)
            ctx = _resident_context(db, fixture, run_id="synthetic-wire",
                now=_utc(datetime(2026, 8, 10, 10, 5)))
            bind_run(db, actor=fixture.world_character, activity_id=ctx.run_id)
            db.commit()
            async def guard(_state):
                return {}
            lane = CombinedRoutineLane(ctx, actor=fixture.world_character,
                tracker=RunLlmTracker(max_calls=1), hybrid_service=None,
                guard=guard, ledger=RecoveryLedger(db, ctx.run_id))
            lane.output_policy = replace(lane.output_policy, provider_schema_profile=profile)
            captured = {}
            async def capture(_self, **kwargs):
                captured.update(kwargs)
                raise CapturedRequest()
            async def assemble():
                state = {"identity": {"activity_id": ctx.run_id},
                    "shared_context": {"now": ctx.run_started_at.isoformat()},
                    "generation_mode": "combined"}
                state.update(await lane.load(state))
                events = tuple(RoutineInteractionInput(
                    f"synthetic-event-{i}", fixture.world.id, fixture.world_character.id,
                    "synthetic-friend", "A friend offered encouragement.", ctx.run_started_at)
                    for i in range(count))
                lane.prepared.context = replace(lane.prepared.context, source_events=events,
                    previous_beat=SimpleNamespace(id="synthetic-previous-beat", sequence_no=1),
                    previous_post=SimpleNamespace(id="synthetic-previous-post",
                        title="A quiet morning", body="I checked my walking route.",
                        topic_signature="walk", created_at=ctx.run_started_at))
                lane.provider.situation_snapshot = SimpleNamespace(memory_search_locale="en-US")
                lane.provider.situation_output_revision = TARGET_OUTPUT_REVISION
                lane.provider.situation_validation_locale = "en-US"
                state["decision_context"] = {"source_manifest": [], "image_output_enabled": True}
                with patch.object(ActivityProvider, "call", capture):
                    try:
                        await lane.plan(state)
                    except CapturedRequest:
                        pass
            asyncio.run(assemble())
            assert captured["node"] == "RoutineDecisionDraft"
            yield captured
    finally:
        engine.dispose()


def valid_output(count):
    ids = [f"synthetic-event-{i}" for i in range(count)]
    return {
        "decision": {"scene_kind": "continue", "scene_brief": "Check the walking route.",
            "continuity_facts": ["previous_post_id:synthetic-previous-post"],
            "used_source_event_ids": ids, "used_detail_keys": ["activity.title"],
            "source_event_effects": [{"source_event_id": key, "state_change": {
                "mood": "calm", "mood_intensity_delta": 1, "action_note": "Remember the encouragement."
            }} for key in ids], "state_update": None, "state_source_refs": [],
            "relationship_metrics": []},
        "draft": {"title": "Checking the route", "body": "I am looking over the route for my next walk.",
            "topic_signature": "walk route", "novelty_basis": "Looking at the next part of the route.",
            "thought": "I want to check the route carefully.", "image_prompt": ""},
        "situations": [{"target_id": "routine-post",
            "description": "After checking a walking route, I draft a post about looking over the next part."}],
    }
