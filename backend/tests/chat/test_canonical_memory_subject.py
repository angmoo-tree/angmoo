"""Subject bindings and repair use code-owned identity, not names or model roles."""
import asyncio
import json
from dataclasses import replace

import pytest

from app.contracts.retrieval_observation import Observation, current
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.memory.contracts.planner_provider import (
    CanonicalPlannerEntity, CanonicalPlannerRequest,
)
from app.domains.memory.contracts.retrieval_plan import CanonicalPlanContractError
from app.domains.memory.policies.retrieval_planner import parse_canonical_retrieval_plan_payload
from app.integrations import direct_llm
from app.integrations.llm.canonical_retrieval_planner import DirectLlmCanonicalRetrievalPlannerProvider
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from test_p8_l_l_canonical_retrieval_planner import (
    _resolved, _plan_payload, _router_tracker, _FakeRecall, _FakePlanner,
    NOW, DEADLINE, CanonicalRetrievalPlanningService, CanonicalRetrievalCommand,
    CanonicalRetrievalPlanExecutor, CanonicalRetrievalPlanValidator,
)


def _command(*, self_ref=True, repaired=False):
    intent, resolved = _resolved()
    intent = replace(intent, relationship=None)
    bindings = tuple(
        replace(binding, world_character_id=resolved.responding_world_character_id)
        if self_ref else binding
        for binding in resolved.entity_bindings
    )
    resolved = replace(
        resolved, intent_hash=intent.envelope_hash, entity_bindings=bindings,
        relationship_from_world_character_id=None, relationship_to_world_character_id=None,
    )
    return CanonicalRetrievalCommand(
        user_message="내 기억에서 미세 제어를 찾아줘", thread_id="fixture",
        intent=intent, resolved=resolved, call_tracker=_router_tracker(repaired=repaired),
    )


def _payload(command, *, counterpart="entity-1", operation="search_memory_items"):
    payload = _plan_payload(command.resolved)
    parameters = {"search_text": "미세 제어"}
    if counterpart is not ...:
        parameters["counterpart_ref"] = counterpart
    payload["steps"] = [{
        "id": "step1", "operation": operation, "input_ref": None,
        "parameters": parameters,
    }]
    return payload


def test_self_counterpart_is_rejected_before_any_query():
    command = _command()
    recall = _FakeRecall()
    plan = parse_canonical_retrieval_plan_payload(_payload(command))
    context = CanonicalRetrievalPlanningService._execution_context(command)
    with pytest.raises(CanonicalPlanContractError, match="canonical_plan_memory_subject_as_counterpart"):
        CanonicalRetrievalPlanExecutor(recall).execute(plan, context, now=NOW)
    assert not recall.queries


@pytest.mark.parametrize("operation", ["search_posts", "search_thread_messages"])
def test_self_guard_does_not_redefine_other_operations(operation):
    command = _command()
    plan = parse_canonical_retrieval_plan_payload(_payload(command, operation=operation))
    context = CanonicalRetrievalPlanningService._execution_context(command)
    assert CanonicalRetrievalPlanValidator().validate(plan, context).plan == plan


@pytest.mark.parametrize("counterpart,code", [
    (None, "canonical_plan_counterpart_ref_invalid"),
    ("unknown-entity", "canonical_plan_entity_ref_unresolved"),
])
def test_null_and_unresolved_refs_keep_existing_contract(counterpart, code):
    command = _command()
    with pytest.raises(CanonicalPlanContractError, match=code):
        plan = parse_canonical_retrieval_plan_payload(_payload(command, counterpart=counterpart))
        CanonicalRetrievalPlanValidator().validate(
            plan, CanonicalRetrievalPlanningService._execution_context(command)
        )


@pytest.mark.parametrize("self_ref", [True, False])
def test_subject_hints_and_valid_first_plan_need_no_extra_call(self_ref):
    command = _command(self_ref=self_ref)
    counterpart = ... if self_ref else "entity-1"
    planner = _FakePlanner(parse_canonical_retrieval_plan_payload(_payload(command, counterpart=counterpart)))
    recall = _FakeRecall()
    result = asyncio.run(CanonicalRetrievalPlanningService(
        planner=planner, executor=CanonicalRetrievalPlanExecutor(recall),
    ).plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
    assert planner.requests[0].memory_subject_refs == (("entity-1",) if self_ref else ())
    assert result.metrics.first_pass_valid and not result.metrics.repair_used
    assert result.call_tracker["logical_total"] == result.call_tracker["physical_total"] == 2
    query = recall.queries[0]
    assert query.scope.subject_world_character_id == command.resolved.responding_world_character_id
    assert query.counterpart_world_character_id == (
        None if self_ref else command.resolved.entity_bindings[0].world_character_id
    )


@pytest.mark.parametrize("refs", [("entity-1", "entity-1"), ("unknown",), (None,), "entity-1"])
def test_subject_hint_contract_rejects_invalid_refs(refs):
    command = _command()
    request = CanonicalRetrievalPlanningService._provider_request(command)
    with pytest.raises(CanonicalPlanContractError, match="canonical_planner_memory_subject_refs_invalid"):
        replace(request, memory_subject_refs=refs)


def test_subject_aliases_and_absent_subject_are_derived_from_bindings():
    command = _command()
    first = command.intent.entities[0]
    alias = replace(first, ref="entity-2", mention="별칭")
    intent = replace(command.intent, entities=(first, alias))
    resolved = replace(
        command.resolved, intent_hash=intent.envelope_hash,
        entity_bindings=(
            command.resolved.entity_bindings[0],
            replace(command.resolved.entity_bindings[0], ref="entity-2"),
        ),
    )
    command = replace(command, intent=intent, resolved=resolved)
    request = CanonicalRetrievalPlanningService._provider_request(command)
    assert request.memory_subject_refs == ("entity-1", "entity-2")
    for ref in request.memory_subject_refs:
        plan = parse_canonical_retrieval_plan_payload(_payload(command, counterpart=ref))
        with pytest.raises(CanonicalPlanContractError, match="canonical_plan_memory_subject_as_counterpart"):
            CanonicalRetrievalPlanValidator().validate(
                plan, CanonicalRetrievalPlanningService._execution_context(command),
            )
    intent = replace(intent, entities=())
    command = replace(command, intent=intent, resolved=replace(
        resolved, intent_hash=intent.envelope_hash, entity_bindings=(),
    ))
    assert CanonicalRetrievalPlanningService._provider_request(command).memory_subject_refs == ()


@pytest.mark.parametrize("mode", ["success", "failure", "exhausted"])
@pytest.mark.parametrize("model", ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"])
@pytest.mark.parametrize("thinking", ["high", "medium"])
def test_adapter_self_filter_repair_and_safe_diagnostics(monkeypatch, mode, model, thinking):
    command = _command(repaired=mode == "exhausted")
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        payload = _payload(command, counterpart=(
            ... if len(calls) == 2 and mode == "success" else "entity-1"
        ))
        return direct_llm.DirectLlmResponse(
            text=json.dumps(payload), parsed=None, usage={}, finish_reason="STOP",
        )

    monkeypatch.setattr(direct_llm, "generate_text", generate)
    provider = DirectLlmCanonicalRetrievalPlannerProvider(CredentialMaterial(
        credential_id="fixture", provider="google", model=model, fingerprint="fixture",
        purpose=CredentialPurpose.MESSAGE_LLM, _secret="synthetic-key", thinking_level=thinking,
    ))
    recall = _FakeRecall()
    service = CanonicalRetrievalPlanningService(planner=provider, executor=CanonicalRetrievalPlanExecutor(recall))
    observation = Observation()
    token = current.set(observation)
    try:
        if mode == "success":
            result = asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
            snapshot = result.call_tracker
            assert result.metrics.repair_used and not result.metrics.first_pass_valid
            assert len(recall.queries) == 1 and recall.queries[0].counterpart_world_character_id is None
        else:
            with pytest.raises(RetrievalContractError) as failure:
                asyncio.run(service.plan_and_execute(command, now=NOW, deadline_at=DEADLINE))
            snapshot = failure.value.call_tracker
            assert not recall.queries
    finally:
        current.reset(token)
    assert len(calls) == (1 if mode == "exhausted" else 2)
    assert snapshot["logical_total"] == snapshot["physical_total"] == 3
    assert snapshot["physical_counts"]["character_response_generator"] == 0
    for call in calls:
        payload = json.loads(call["user_prompt"].split("\n", 1)[1])
        assert payload["semantic_intent"]["memory_subject_refs"] == ["entity-1"]
        assert "omit counterpart_ref" in call["system_prompt"]
        assert call["thinking_level"] == thinking and call["max_output_tokens"] == 3072
        assert "actual-" not in call["user_prompt"]
    if len(calls) == 2:
        repair = json.loads(calls[1]["user_prompt"].split("\n", 1)[1])["repair"]
        assert repair["diagnostic"] == "canonical_plan_memory_subject_as_counterpart"
        assert "omit counterpart_ref" in repair["instruction"]
    failures = [row for row in observation.events if row["event"] == "planner_validation"]
    assert len(failures) == (2 if mode == "failure" else 1)
    assert all(row["validation_code"] == "canonical_plan_memory_subject_as_counterpart" for row in failures)
    assert all(row["failure_stage"] == "execution_contract" for row in failures)
    assert "actual-" not in json.dumps(observation.payload())

