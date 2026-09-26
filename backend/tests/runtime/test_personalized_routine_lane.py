import asyncio
from copy import deepcopy
from datetime import datetime
import pytest

from sqlalchemy.orm import Session

from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.routine_resume import freeze_prepared, restore_prepared
from app.runtime.character_activity_state import initialize_from_last_success
from app.domains.world_characters.service.activity_state import read_state
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc, FakeRoutineProvider


def test_routine_nodes_publish_state_and_restore_only_canonical_references(monkeypatch, combined=False):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            fixture = _seed(db)
            ctx = _resident_context(db, fixture, run_id="v2-routine", now=_utc(datetime(2026, 8, 10, 10, 5)))
            initialize_from_last_success(db, actor=fixture.world_character)
            db.commit()
            shared = shared_input(ctx, fixture.world_character, fixture.world)
            shared["now"] = ctx.run_started_at.isoformat()
            async def guard(state):
                return {}
            from app.runtime.autonomous_activity.combined_lanes import CombinedRoutineLane
            from app.runtime.autonomous_activity.provider import ActivityProvider
            from types import SimpleNamespace
            lane_type = CombinedRoutineLane if combined else RoutineLane
            lane = lane_type(ctx, actor=fixture.world_character, tracker=RunLlmTracker(max_calls=8), hybrid_service=None, guard=guard,
                **({"ledger": SimpleNamespace(reserve=lambda key: pytest.fail("normal generation must not repair"))} if combined else {}))
            calls = []
            fake = FakeRoutineProvider()
            async def call(_provider, **kwargs):
                calls.append(kwargs["node"])
                if kwargs["node"] in {"RoutineActionPlanner", "RoutineDecisionDraft", "RoutineWriter"}:
                    prompt_context = kwargs["payload"].get("context", kwargs["payload"])
                    temporal = prompt_context["routine"].get("temporal_context")
                    if temporal is not None:
                        assert temporal["local_datetime"] == "2026-08-10T10:05:00+09:00"
                        assert temporal["activity_window"]["contains_reference_time"] is True
                    else:
                        assert kwargs["node"] == "RoutineWriter"  # An older saved decision has no time block.
                    assert "conclude" in kwargs["system"]
                generation = await fake.generate(resident_context=ctx, routine_context=lane.prepared.context,
                    beat=lane.prepared.beat, tracker=RunLlmTracker(max_calls=2))
                if kwargs["node"] in {"RoutineActionPlanner", "RoutineDecisionDraft"}:
                    assert kwargs["payload"]["beat_identity"] == {"episode_id": lane.prepared.context.episode.id, "beat_id": lane.prepared.beat.id, "sequence_no": lane.prepared.beat.sequence_no}
                    schema = kwargs["schema"]["properties"]["decision"] if combined else kwargs["schema"]
                    assert schema["properties"]["episode_id"]["enum"] == [lane.prepared.context.episode.id]
                    frozen = freeze_prepared(lane.prepared)
                    lane.prepared = restore_prepared(ctx, frozen, lane.tracker)
                    decision = {**generation.plan.model_dump(),
                        "state_update": {"mood": "hopeful", "mood_intensity": 35, "state_note": "새 시도를 마친 뒤 의욕이 생겼다."},
                        "state_source_refs": []}
                    if kwargs.get("on_input_receipt"):
                        kwargs["on_input_receipt"]({"node": kwargs["node"]})
                    return kwargs["validator"]({"decision": decision,
                        "draft": {**generation.draft.model_dump(), "thought": "차근차근 시도해 보고 싶었다."}} if combined else decision)
                return kwargs["validator"]({**generation.draft.model_dump(), "thought": "차근차근 시도해 보고 싶었다."})
            monkeypatch.setattr(ActivityProvider, "call", call)
            result = await build_lane("routine", lane.ports(), combined=combined).ainvoke({"identity": {"activity_id": ctx.run_id}, "shared_context": shared})
            assert calls == (["RoutineDecisionDraft"] if combined else ["RoutineActionPlanner", "RoutineWriter"])
            assert result["decision_context"]["routine"]["temporal_context"]["as_of_utc"] == ctx.run_started_at.isoformat()
            assert result["result"]["public_action_count"] == 1
            assert result["result"]["settlement"]["state"] == "updated"
            current = read_state(db, world_id=fixture.world.id, actor_id=fixture.world_character.id)
            assert current["mood"] == "hopeful"
            # A committed execution is authoritative if a checkpoint was missed.
            replay = await lane.execute(result)
            assert replay["executions"][0]["routine_outcome"] == "REUSED_SUCCESS"
            assert replay["executions"][0]["publish_result"]["public_action_count"] == 0
            advanced = deepcopy(result)
            advanced["shared_context"]["now"] = _utc(datetime(2026, 8, 10, 12, 5)).isoformat()
            if combined:
                # A valid draft in an old checkpoint is reused without another request.
                old = deepcopy(advanced)
                old["decision_context"]["routine"].pop("temporal_context")
                assert (await lane.write(old))["drafts"]
                assert calls == ["RoutineDecisionDraft"]

                # An invalid provisional draft follows the existing Writer recovery path.
                reservations = []
                lane.provider.ledger = SimpleNamespace(reserve=reservations.append)
                advanced["decision"]["provisional_draft"] = None
                assert (await lane.write(advanced))["drafts"]
                assert calls == ["RoutineDecisionDraft", "RoutineWriter"]
                assert len(reservations) == 1
            else:
                # Retried Writer receives the saved decision time, not the advanced clock.
                assert (await lane.write(advanced))["drafts"]
                old = deepcopy(advanced)
                old["decision_context"]["routine"].pop("temporal_context")
                assert (await lane.write(old))["drafts"]
                assert calls == ["RoutineActionPlanner", "RoutineWriter", "RoutineWriter", "RoutineWriter"]
    asyncio.run(scenario())


def test_combined_routine_publishes_and_reuses_canonical_result(monkeypatch):
    test_routine_nodes_publish_state_and_restore_only_canonical_references(monkeypatch, combined=True)
