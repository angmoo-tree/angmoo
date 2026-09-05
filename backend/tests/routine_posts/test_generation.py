from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.domains.routine_posts.service import generation as generation_service
from app.domains.routine_posts.service.context import assemble_routine_post_context
from app.integrations.direct_llm import DirectLlmError
from app.runtime.routine_posts.context_references import SqlAlchemyRoutineContextReferences
from routine_posts.test_runtime import _engine, _resident_context, _seed, _utc


@pytest.mark.parametrize("outcome", ("success", "invalid_plan", "writer_error"))
def test_generation_keeps_two_calls_validation_fence_and_error_identity(
    monkeypatch, outcome: str,
) -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 10, 10, 5))
    calls = []
    sequence = []
    transport_error = DirectLlmError("synthetic writer failure")
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        resident = _resident_context(db, fixture, run_id="generation-run", now=now)
        context = assemble_routine_post_context(
            db, references=SqlAlchemyRoutineContextReferences(db),
            world_character=fixture.world_character, character=fixture.character,
            now=now,
        )
        beat = SimpleNamespace(id="generation-beat", sequence_no=1)
        tracker = object()

        def resolve_key(credential):
            assert credential is resident.credential
            sequence.append("credential")
            return "synthetic-routine-key"

        async def transport(**kwargs):
            calls.append(kwargs)
            node = kwargs["context"].node
            sequence.append(node)
            if node == "RoutineBeatPlanner":
                return kwargs["validator"]({
                    "episode_id": context.episode.id,
                    "beat_id": "wrong-beat" if outcome == "invalid_plan" else beat.id,
                    "sequence_no": 1, "scene_kind": "start", "scene_brief": "Begin the activity.",
                })
            if outcome == "writer_error":
                raise transport_error
            return kwargs["validator"]({
                "title": "A morning scene", "body": "The activity begins.",
                "topic_signature": "morning-scene", "novelty_basis": "The current scene.",
            })

        monkeypatch.setattr(generation_service, "_api_key", resolve_key)
        monkeypatch.setattr(generation_service, "generate_json", transport)
        operation = generation_service.DirectRoutinePostProvider().generate(
            resident_context=resident, routine_context=context, beat=beat, tracker=tracker,
        )
        if outcome == "success":
            result = asyncio.run(operation)
            assert result.plan.beat_id == beat.id
            assert result.draft.body == "The activity begins."
            writer_input = json.loads(calls[1]["user_prompt"])
            assert writer_input["validated_scene_plan"] == result.plan.model_dump()
            assert writer_input["state_after"] == result.state_after
        elif outcome == "invalid_plan":
            with pytest.raises(ValueError, match="routine beat identity mismatch") as raised:
                asyncio.run(operation)
            assert raised.value.node == "RoutineBeatPlanner"
            assert raised.value.lane == "routine_beat_planner"
        else:
            with pytest.raises(DirectLlmError) as raised:
                asyncio.run(operation)
            assert raised.value is transport_error
            assert raised.value.node == "PostWriter"
            assert raised.value.lane == "routine_post_writer"

        expected_nodes = ["RoutineBeatPlanner"] if outcome == "invalid_plan" else ["RoutineBeatPlanner", "PostWriter"]
        assert sequence == ["credential", *expected_nodes]
        assert len(calls) == len(expected_nodes)
        for call, node in zip(calls, expected_nodes, strict=True):
            assert call["tracker"] is tracker
            assert call["on_rate_limit_wait"] is resident.on_rate_limit_wait
            assert call["context"].node == node
            assert call["context"].credential_id == resident.credential.id
            assert call["context"].character_id == resident.character.id
            assert call["context"].agent_run_id == resident.run_id
            assert call["max_output_tokens"] == 2400
            assert call["thinking_level"] == "medium"
            assert "synthetic-routine-key" not in call["system_prompt"]
            assert "synthetic-routine-key" not in call["user_prompt"]
        assert json.loads(calls[0]["user_prompt"])["beat_identity"] == {
            "episode_id": context.episode.id, "beat_id": beat.id, "sequence_no": 1,
        }
        assert db.get(type(fixture.morning_episode), fixture.morning_episode.id).last_successful_beat_id is None
    engine.dispose()
