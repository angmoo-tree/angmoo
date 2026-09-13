import asyncio
import pytest
from app.contracts.retrieval_observation import Observation, current
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.service.planner_diagnostics import observe_canonical_rejection
from app.integrations.direct_llm import DirectLlmJsonError
from test_p8_l_l_canonical_retrieval_planner import (
    _resolved, _router_tracker, _FakePlanner, _FakeRecall, NOW, DEADLINE,
    CanonicalPlannerOutputError, CanonicalPlanContractError,
    CanonicalRetrievalPlanningService, CanonicalRetrievalCommand,
    CanonicalRetrievalPlanExecutor,
)


def test_rejected_repair_retains_exact_codes_and_attempts():
    intent, resolved = _resolved()
    parser = CanonicalPlanContractError("canonical_plan_parameter_forbidden")
    direct = DirectLlmJsonError("private body", failure_class="json_parse_failed",
        parse_error_type="CanonicalPlanContractError", json_error_diagnostics=[{
            "finish_reason": "STOP", "shape_hint": "schema_validation",
            "response_length": 231, "preview_head": "secret preview"}])
    direct.__cause__ = parser
    first = CanonicalPlannerOutputError("CanonicalPlanContractError")
    first.__cause__ = direct
    second = CanonicalPlannerOutputError("JSONDecodeError")
    planner = _FakePlanner(first, second)
    service = CanonicalRetrievalPlanningService(planner=planner,
        executor=CanonicalRetrievalPlanExecutor(_FakeRecall()))
    obs = Observation()
    token = current.set(obs)
    try:
        with pytest.raises(RetrievalContractError) as error:
            asyncio.run(service.plan_and_execute(CanonicalRetrievalCommand(
                user_message="synthetic", thread_id="thread-1", intent=intent,
                resolved=resolved, call_tracker=_router_tracker()), now=NOW, deadline_at=DEADLINE))
    finally:
        current.reset(token)
    events = [e for e in obs.events if e["event"] == "planner_validation"]
    assert [e["phase"] for e in events] == ["first", "repair"]
    assert events[0]["validation_code"] == "canonical_plan_parameter_forbidden"
    assert events[0]["failure_stage"] == "schema_validation"
    assert events[0]["finish_reason"] == "STOP"
    assert events[1]["physical_attempts"] == 2
    assert error.value.call_tracker["logical_total"] == 3
    assert error.value.call_tracker["physical_total"] == 3
    assert error.value.call_tracker["physical_counts"]["character_response_generator"] == 0
    assert "secret" not in str(obs.payload()) and "private" not in str(obs.payload())


def test_unknown_provider_text_is_not_a_basic_error_code():
    from app.domains.chat.contracts.call_tracker import restore_call_tracker_snapshot
    obs = Observation()
    token = current.set(obs)
    try:
        observe_canonical_rejection(CanonicalPlannerOutputError("secret_token_value"),
            phase="first", tracker=restore_call_tracker_snapshot(_router_tracker(), deadline_at=DEADLINE))
    finally:
        current.reset(token)
    assert "secret_token_value" not in str(obs.payload())
    assert obs.events[0]["validation_code"] == "unknown"
