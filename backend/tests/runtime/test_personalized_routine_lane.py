import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.routine_resume import freeze_prepared, restore_prepared
from app.runtime.character_activity_state import initialize_from_last_success
from app.domains.world_characters.service.activity_state import read_state
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc, FakeRoutineProvider


def test_routine_nodes_publish_state_and_restore_only_canonical_references(monkeypatch):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            fixture = _seed(db)
            ctx = _resident_context(db, fixture, run_id="v2-routine", now=_utc(datetime(2026, 8, 10, 10, 5)))
            initialize_from_last_success(db, actor=fixture.world_character)
            db.commit()
            shared = shared_input(ctx, fixture.world_character, fixture.world)
            async def guard(state):
                return {}
            lane = RoutineLane(ctx, actor=fixture.world_character, tracker=RunLlmTracker(max_calls=8), hybrid_service=None, guard=guard)
            calls = []
            fake = FakeRoutineProvider()
            async def call(**kwargs):
                calls.append(kwargs["node"])
                generation = await fake.generate(resident_context=ctx, routine_context=lane.prepared.context,
                    beat=lane.prepared.beat, tracker=RunLlmTracker(max_calls=2))
                if kwargs["node"] == "RoutineActionPlanner":
                    assert kwargs["payload"]["beat_identity"] == {"episode_id": lane.prepared.context.episode.id, "beat_id": lane.prepared.beat.id, "sequence_no": lane.prepared.beat.sequence_no}
                    assert kwargs["schema"]["properties"]["episode_id"]["enum"] == [lane.prepared.context.episode.id]
                    frozen = freeze_prepared(lane.prepared)
                    lane.prepared = restore_prepared(ctx, frozen, lane.tracker)
                    return kwargs["validator"]({**generation.plan.model_dump(),
                        "state_update": {"mood": "hopeful", "mood_intensity": 35, "state_note": "새 시도를 마친 뒤 의욕이 생겼다."},
                        "state_source_refs": []})
                return kwargs["validator"]({**generation.draft.model_dump(), "thought": "차근차근 시도해 보고 싶었다."})
            monkeypatch.setattr(lane.provider, "call", call)
            result = await build_lane("routine", lane.ports()).ainvoke({"identity": {"activity_id": ctx.run_id}, "shared_context": shared})
            assert calls == ["RoutineActionPlanner", "RoutineWriter"]
            assert result["result"]["public_action_count"] == 1
            assert result["result"]["settlement"]["state"] == "updated"
            current = read_state(db, world_id=fixture.world.id, actor_id=fixture.world_character.id)
            assert current["mood"] == "hopeful"
            # A committed execution is authoritative if a checkpoint was missed.
            replay = await lane.execute(result)
            assert replay["executions"][0]["routine_outcome"] == "REUSED_SUCCESS"
            assert replay["executions"][0]["publish_result"]["public_action_count"] == 0
    asyncio.run(scenario())
