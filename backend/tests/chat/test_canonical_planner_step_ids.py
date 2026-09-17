"""Exercise the real JSON parser/adapter boundary with synthetic provider text."""
import asyncio
import json

import pytest

from app.integrations import direct_llm
from app.integrations.llm.canonical_retrieval_planner import DirectLlmCanonicalRetrievalPlannerProvider
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.contracts.planner_provider import CanonicalPlannerOutputError
from app.domains.memory.contracts.retrieval_plan import CanonicalPlanContractError
from app.domains.memory.policies.retrieval_planner import parse_canonical_retrieval_plan_payload
from test_p8_l_l_canonical_retrieval_planner import (
    _resolved, _plan_payload, _router_tracker, _FakeRecall, NOW, DEADLINE,
    CanonicalRetrievalPlanningService, CanonicalRetrievalCommand,
    CanonicalRetrievalPlanExecutor,
)


@pytest.mark.parametrize("step_id", ["step1", "step_1", "search_memory", "a" * 48])
def test_existing_valid_step_ids_remain_accepted(step_id):
    _, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["steps"][0]["id"] = step_id
    payload["steps"][1]["input_ref"] = step_id + ".source_refs"
    assert parse_canonical_retrieval_plan_payload(payload).steps[0].id == step_id


@pytest.mark.parametrize("step_id", ["", "a" * 49, "Step1", "1step", "step-1", "step 1", "단계"])
def test_invalid_step_ids_are_rejected(step_id):
    _, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["steps"][0]["id"] = step_id
    with pytest.raises(CanonicalPlanContractError):
        parse_canonical_retrieval_plan_payload(payload)


@pytest.mark.parametrize("reference", ["missing.source_refs", "details.source_refs", "events.rows", "events-source_refs"])
def test_invalid_dependencies_are_rejected(reference):
    _, resolved = _resolved()
    payload = _plan_payload(resolved)
    payload["steps"][1]["input_ref"] = reference
    with pytest.raises(CanonicalPlanContractError, match="canonical_plan_reference_invalid"):
        parse_canonical_retrieval_plan_payload(payload)


@pytest.mark.parametrize("model", ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"])
@pytest.mark.parametrize("thinking", ["high", "medium"])
@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_real_adapter_repairs_exact_id_error_without_hidden_calls(monkeypatch, model, thinking, repair_succeeds):
    intent, resolved = _resolved()
    calls = []

    async def fake_generate_text(**kwargs):
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        payload = _plan_payload(resolved)
        payload["steps"][0]["id"] = "step1" if len(calls) == 2 and repair_succeeds else "step-1"
        payload["steps"][1]["id"] = "step2"
        payload["steps"][1]["input_ref"] = "step1.source_refs"
        return direct_llm.DirectLlmResponse(text=json.dumps(payload), parsed=None, usage={}, finish_reason="STOP")

    monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)
    provider = DirectLlmCanonicalRetrievalPlannerProvider(CredentialMaterial(
        credential_id="fixture", provider="google", model=model,
        fingerprint="fixture", purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="synthetic-key", thinking_level=thinking,
    ))
    recall = _FakeRecall()
    service = CanonicalRetrievalPlanningService(planner=provider, executor=CanonicalRetrievalPlanExecutor(recall))
    command = CanonicalRetrievalCommand(user_message="synthetic", thread_id="fixture", intent=intent, resolved=resolved, call_tracker=_router_tracker())
    if repair_succeeds:
        result = asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
        assert len(recall.queries) == 2
        assert result.execution.records
        snapshot = result.call_tracker
    else:
        from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
        with pytest.raises(RetrievalContractError) as error:
            asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
        assert not recall.queries
        snapshot = error.value.call_tracker
    assert len(calls) == 2
    assert snapshot["logical_total"] == snapshot["physical_total"] == 3
    assert snapshot["physical_counts"]["character_response_generator"] == 0
    repaired = json.loads(calls[1]["user_prompt"].split("\n", 1)[1])["repair"]
    assert repaired["diagnostic"] == "canonical_plan_step_id_invalid"
    assert "input_ref" in repaired["instruction"]
    for call in calls:
        assert call["thinking_level"] == thinking
        assert call["max_output_tokens"] == 3072
        assert "step1" in call["system_prompt"] and "step-1" in call["system_prompt"]
        assert call["response_schema"]["properties"]["steps"]["items"]["properties"]["id"]["enum"] == [f"step{i}" for i in range(1, 7)]
        from app.providers.gemini import build_generate_content_config
        config = build_generate_content_config(
            model=model, system_prompt=call["system_prompt"], max_output_tokens=3072,
            response_mime_type="application/json", response_schema=call["response_schema"],
            thinking_level=thinking,
        ).model_dump(mode="json", by_alias=True, exclude_none=True)
        assert config["responseJsonSchema"] == call["response_schema"]
        assert config["thinkingConfig"]["thinkingLevel"].lower() == thinking


def test_feedback_does_not_disclose_unknown_text():
    from app.domains.memory.contracts.planner_provider import canonical_planner_diagnostic
    error = CanonicalPlannerOutputError("canonical_plan_secret_user_body")
    error.__cause__ = ValueError("synthetic-key private response")
    assert canonical_planner_diagnostic(error) == "schema_validation_failed"
    error.__cause__ = CanonicalPlanContractError("canonical_plan_step_id_invalid")
    assert canonical_planner_diagnostic(error) == "canonical_plan_step_id_invalid"


@pytest.mark.parametrize("case", ["duplicate", "future", "required", "forbidden"])
def test_step_dependency_contracts_remain_enforced(case):
    _, resolved = _resolved()
    payload = _plan_payload(resolved)
    if case == "duplicate":
        payload["steps"][1]["id"] = "events"
        expected = "canonical_plan_step_id_duplicate"
    elif case == "future":
        payload["steps"].reverse()
        expected = "canonical_plan_reference_invalid"
    elif case == "required":
        payload["steps"][1]["input_ref"] = None
        expected = "canonical_plan_input_ref_required"
    else:
        payload["steps"][0]["input_ref"] = "events.source_refs"
        expected = "canonical_plan_input_ref_forbidden"
    with pytest.raises(CanonicalPlanContractError, match=expected):
        parse_canonical_retrieval_plan_payload(payload)
