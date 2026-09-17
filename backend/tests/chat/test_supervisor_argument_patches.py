"""Independent argument patches retain scope, direction and real ToolNode execution."""
import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.contracts.retrieval_router import parse_retrieval_intent_payload
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest, RetrievalRouterOutputError
from app.domains.chat.contracts.supervisor_selection import (
    SEMANTIC_FIELDS, SelectionArgumentOptions, SelectionToolCall, SelectionValidationTrace,
    model_arguments_schema, execution_arguments_schema, parse_control_selection, effective_calls,
)
from app.domains.chat.contracts.workflow_recipe import select_workflow_recipe
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from app.domains.identity.contracts import CredentialPurpose
from app.integrations.llm.supervisor_selection import (
    DirectLlmSupervisorSelectionProvider, control_selection_system_prompt, control_selection_tools,
)
from app.providers.contracts import ProviderToolCall
from app.runtime.chat.retrieval_tools import (
    RetrievalToolExecution, ToolBothCoordinator, ToolPlanningService, active_tool_execution, parallel_tools,
)
from chat import test_p8_l_k_retrieval_router as routing
from chat import test_p8_l_n_both_workflow_coordinator as both
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_p8_l_k_retrieval_router import retrieval_session


OPTIONS = [SelectionArgumentOptions(a, b) for a, b in ((False, False), (True, False), (False, True), (True, True))]


def wire(payload, options):
    args = {key: deepcopy(payload[key]) for key in SEMANTIC_FIELDS}
    if args["relationship"] is not None:
        args["relationship"]["perspective"] = "responding_character"
    if options.code_coordination:
        del args["coordination_hint"]
    if options.positional_entity_refs:
        refs = {"responding_character": "SELF", "requester_character": "USER"}
        for index, entity in enumerate(args["entities"], 1):
            refs[entity.pop("ref")] = f"E{index}"
        if args["relationship"]:
            for key in ("from", "to"):
                args["relationship"][key] = refs[args["relationship"][key]]
    if payload["route"] == "CLARIFICATION":
        args["clarification_slot"] = payload["clarification_slot"]
    return args


def calls_for(payload, options):
    route = payload["route"]
    names = ("CANONICAL", "GRAPH") if route == "BOTH" else ({"CURRENT_CONTEXT": "USE_CONTEXT", "CLARIFICATION": "REQUEST_CLARIFICATION"}.get(route, route),)
    return tuple(SelectionToolCall(f"call-{i}", name, json.dumps(wire(payload, options))) for i, name in enumerate(names))


def material():
    return SimpleNamespace(purpose=CredentialPurpose.MESSAGE_LLM, model="gemini-3.1-flash-lite", thinking_level="high", credential_id="test", provider="google", fingerprint="test", reveal=lambda: "synthetic")


@pytest.mark.parametrize("options", OPTIONS)
def test_model_and_execution_schemas_have_separate_ownership(options):
    tools = control_selection_tools(options)
    assert [t.name for t in tools] == ["CANONICAL", "GRAPH", "USE_CONTEXT", "REQUEST_CLARIFICATION"]
    for tool in tools:
        schema = tool.parameters
        assert ("coordination_hint" in schema["required"]) is not options.code_coordination
        entity = schema["properties"]["entities"]["items"]
        assert ("ref" in entity["required"]) is not options.positional_entity_refs
        assert schema["additionalProperties"] is False
    internal = execution_arguments_schema()
    assert "coordination_hint" in internal["required"]
    assert "ref" in internal["properties"]["entities"]["items"]["required"]
    prompt = control_selection_system_prompt(options)
    assert ("coordination_hint" in prompt) is not options.code_coordination
    assert ("Entity-list refs use lowercase" in prompt) is not options.positional_entity_refs
    assert "Both retrieval calls must carry identical whole-request semantic arguments" in prompt


@pytest.mark.parametrize("options", OPTIONS)
@pytest.mark.parametrize("route", ["CURRENT_CONTEXT", "CLARIFICATION", "CANONICAL", "GRAPH", "BOTH"])
def test_all_combinations_preserve_internal_meaning_and_call_identity(options, route):
    payload = routing._payload(route)
    original = parse_retrieval_intent_payload(payload)
    proposed = calls_for(payload, options)
    before = tuple(c.arguments_json for c in proposed)
    parsed = parse_control_selection("", proposed, options=options)
    assert parsed.payload() == original.payload()
    assert parsed.envelope_hash == original.envelope_hash
    assert tuple(c.arguments_json for c in proposed) == before
    for call in effective_calls("request", parsed, proposed):
        assert call.call_id in {c.call_id for c in proposed}
        assert call.arguments() == {key: original.payload()[key] for key in SEMANTIC_FIELDS}
        assert call.origin == "model"
    assert parsed.coordination_source == ("code" if options.code_coordination else "model")


@pytest.mark.parametrize("meaning,recipe", [
    ("mixed_evidence", "INDEPENDENT_PARALLEL"),
    ("relationship_comparison", "INDEPENDENT_PARALLEL"),
    ("relationship_cause", "GRAPH_THEN_CANONICAL"),
    ("relationship_state", "GRAPH_THEN_CANONICAL"),
    ("relationship_path", "GRAPH_THEN_CANONICAL"),
    ("historical_recall", "CANONICAL_THEN_GRAPH"),
    ("event_aggregation", "CANONICAL_THEN_GRAPH"),
])
def test_code_recipe_is_registry_owned_and_is_not_a_model_hint(meaning, recipe):
    options = SelectionArgumentOptions(True)
    payload = both._intent_payload(intent=meaning)
    parsed = parse_control_selection("", calls_for(payload, options), options=options)
    selection = select_workflow_recipe(parsed)
    assert selection.selected.value == recipe
    assert selection.requested is None and selection.hint_accepted is None
    assert selection.coordination_source == "code"
    wrong = "GRAPH_THEN_CANONICAL" if recipe != "GRAPH_THEN_CANONICAL" else "INDEPENDENT_PARALLEL"
    with pytest.raises(ValueError, match="code_recipe_mismatch"):
        select_workflow_recipe(replace(parsed, coordination_hint=wrong))


@pytest.mark.parametrize("mutation", ["old_field", "unregistered", "disagreement", "foreign", "raw_query", "duplicate", "duplicate_id", "control_mix"])
def test_coordination_patch_does_not_guess_or_weaken_batch_validation(mutation):
    options = SelectionArgumentOptions(True)
    calls = calls_for(routing._payload(), options)
    args = calls[0].arguments()
    if mutation == "old_field": args["coordination_hint"] = None
    elif mutation == "unregistered": args["intent"] = "today_activity"
    elif mutation == "foreign": args["owner_id"] = "foreign"
    elif mutation == "raw_query": args["entities"][0]["mention"] = "MATCH (n) RETURN n"
    elif mutation == "disagreement": args["relationship"]["from"] = "requester_character"
    if mutation in {"unregistered", "raw_query"}:
        calls = tuple(replace(c, arguments_json=json.dumps(args)) for c in calls)
    else:
        calls = (replace(calls[0], arguments_json=json.dumps(args)), calls[1])
    if mutation == "duplicate": calls = (calls[0], replace(calls[0], call_id="other"))
    elif mutation == "duplicate_id": calls = (calls[0], replace(calls[1], call_id=calls[0].call_id))
    elif mutation == "control_mix": calls = (replace(calls[0], name="USE_CONTEXT"), calls[1])
    with pytest.raises(ValueError): parse_control_selection("", calls, options=options)


@pytest.mark.parametrize("name", ["인물 X", "Alex", "山田", "Мария", "그 사람"])
@pytest.mark.parametrize("endpoint", ["SELF", "USER", "E1", "E4"])
def test_position_refs_preserve_names_roles_and_direction(name, endpoint):
    options = SelectionArgumentOptions(True, True)
    payload = routing._payload("GRAPH")
    args = wire(payload, options)
    args["entities"] = [{"mention": f"{name} {i}", "role": "mentioned_third_party"} for i in range(4)]
    args["relationship"]["from"] = endpoint
    args["relationship"]["to"] = "E2"
    call = SelectionToolCall("direction", "GRAPH", json.dumps(args))
    parsed = parse_control_selection("", (call,), options=options)
    expected = {"SELF": "responding_character", "USER": "requester_character", "E1": "entity-1", "E4": "entity-4"}
    assert parsed.relationship.from_ref == expected[endpoint]
    assert parsed.relationship.to_ref == "entity-2"
    assert [e.mention for e in parsed.entities] == [f"{name} {i}" for i in range(4)]
    assert all(e.role == "mentioned_third_party" for e in parsed.entities)


@pytest.mark.parametrize("mutation", ["absent", "lowercase", "id", "number", "legacy_ref", "five", "not_list", "extra", "role", "empty_name", "same_endpoint", "perspective"])
def test_invalid_position_arguments_remain_invalid(mutation):
    options = SelectionArgumentOptions(False, True)
    args = wire(routing._payload("GRAPH"), options)
    if mutation in {"absent", "lowercase", "id", "number", "legacy_ref"}:
        args["relationship"]["to"] = {"absent":"E2", "lowercase":"e1", "id":"world-character-id", "number":1, "legacy_ref":"entity-1"}[mutation]
    elif mutation == "five": args["entities"] *= 5
    elif mutation == "not_list": args["entities"] = {}
    elif mutation == "extra": args["entities"][0]["ref"] = "E1"
    elif mutation == "role": args["entities"][0]["role"] = "invented"
    elif mutation == "empty_name": args["entities"][0]["mention"] = ""
    elif mutation == "same_endpoint": args["relationship"]["to"] = "SELF"
    elif mutation == "perspective": args["relationship"]["perspective"] = "USER"
    with pytest.raises(ValueError):
        parse_control_selection("", (SelectionToolCall("invalid", "GRAPH", json.dumps(args)),), options=options)


def test_both_different_lists_are_not_silently_sorted_or_merged():
    options = SelectionArgumentOptions(True, True)
    args = wire(routing._payload(), options)
    args["entities"].append({"mention":"another", "role":"target"})
    other = deepcopy(args)
    other["entities"].reverse()
    other["relationship"]["to"] = "E2"
    calls = (SelectionToolCall("one", "CANONICAL", json.dumps(args)), SelectionToolCall("two", "GRAPH", json.dumps(other)))
    with pytest.raises(ValueError, match="coordination_route_mismatch"):
        parse_control_selection("", calls, options=options)


@pytest.mark.parametrize("options", OPTIONS[1:])
def test_options_are_immutable_and_never_enable_on_the_default_path(options):
    with pytest.raises(FrozenInstanceError): options.code_coordination = False
    with pytest.raises(ValueError, match="require_native_controls"):
        DirectLlmSupervisorSelectionProvider(material(), code_coordination=options.code_coordination, positional_entity_refs=options.positional_entity_refs)


@pytest.mark.parametrize("options", OPTIONS)
@pytest.mark.parametrize("recipe,meaning", [("INDEPENDENT_PARALLEL","mixed_evidence"), ("GRAPH_THEN_CANONICAL","relationship_cause"), ("CANONICAL_THEN_GRAPH","event_aggregation")])
@pytest.mark.parametrize("empty", [False, True])
def test_patch_combinations_reach_real_tools_and_keep_dependency_contract(options, recipe, meaning, empty):
    async def run():
        original, resolved = both._resolved(intent_name=meaning, hint=recipe)
        proposed = calls_for(original.payload(), options)
        intent = parse_control_selection("", proposed, options=options)
        assert intent.envelope_hash == resolved.intent_hash
        coordinator, canonical, graph = both._coordinator(resolved, canonical_recall=both._CanonicalRecall(empty=empty), graph_recall=both._GraphRecall(empty=empty))
        coordinator._canonical = ToolPlanningService("CANONICAL", coordinator._canonical)
        coordinator._graph = ToolPlanningService("GRAPH", coordinator._graph)
        coordinator._parallel_runner = parallel_tools
        execution = RetrievalToolExecution()
        execution.bind(SimpleNamespace(intent=intent, resolved=resolved, proposed_tool_calls=proposed), SimpleNamespace(assert_active=lambda state: None), {})
        token = active_tool_execution.set(execution)
        try:
            value = await ToolBothCoordinator(coordinator).coordinate(both._command(intent, resolved), now=both.NOW, deadline_at=both.DEADLINE)
            execution.assert_complete()
            assert value.selection.selected.value == recipe
            assert value.metrics.coordinator_llm_calls == 0
            assert len(canonical.requests) <= 1 and len(graph.requests) <= 1
            if not empty or recipe == "INDEPENDENT_PARALLEL":
                assert len(canonical.requests) == len(graph.requests) == 1
            else:
                assert sum(r.status == "skipped_dependency" for r in execution.receipts.values()) == 1
            for receipt in execution.receipts.values():
                assert receipt.call.call_id in {c.call_id for c in proposed}
                assert "coordination_hint" in receipt.call.arguments()
            if options.code_coordination:
                assert value.metrics.requested_recipe is None
                assert value.metrics.router_hint_accepted is None
        finally:
            active_tool_execution.reset(token)
    asyncio.run(run())


@pytest.mark.parametrize("options", OPTIONS)
@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CLARIFICATION, RetrievalRoute.CANONICAL, RetrievalRoute.GRAPH])
def test_patch_combinations_keep_supervisor_freeze_crg_and_call_budget(response_session, options, route):
    from chat.test_p8_l_p_evidence_response_streaming import _Router, _workflow, _request, _command, _Generator, _collect
    from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
    class Selector(_Router):
        async def route(self, *args, **kwargs):
            result = await super().route(*args, **kwargs)
            payload = result.intent.payload()
            if route is RetrievalRoute.CURRENT_CONTEXT: payload["intent"] = "current_context"
            elif route is RetrievalRoute.CLARIFICATION: payload["intent"] = "clarification_required"
            proposed = calls_for(payload, options)
            parsed = parse_control_selection("", proposed, options=options)
            resolved = replace(result.resolved, intent_hash=parsed.envelope_hash)
            return replace(result, intent=parsed, resolved=resolved, selection_mode="native_control", proposed_tool_calls=proposed)
    record = _request(response_session, route)
    response_session.commit()
    generator, selector = _Generator(), Selector(route)
    workflow = _workflow(response_session, route, generator, router=selector)
    workflow._canonical = ToolPlanningService("CANONICAL", workflow._canonical)
    workflow._graph = ToolPlanningService("GRAPH", workflow._graph)
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    assert selector.calls == len(generator.requests) == 1
    expected = 2 if route in {RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CLARIFICATION} else 3
    assert workflow._lifecycle.get_request(record.request_id).call_tracker["logical_total"] == expected


def test_repair_diagnostics_do_not_count_unreached_reference_checks_as_pass(monkeypatch):
    outcomes = []
    payload = routing._payload()
    payload["coordination_hint"] = None
    outcomes.append(calls_for(payload, OPTIONS[0]))
    payload["coordination_hint"] = "GRAPH_THEN_CANONICAL"
    payload["entities"][0]["ref"] = "INVALID_ALIAS"
    outcomes.append(calls_for(payload, OPTIONS[0]))
    async def generate(**kwargs):
        calls = outcomes.pop(0)
        return SimpleNamespace(text="", finish_reason="STOP", tool_calls=tuple(ProviderToolCall(c.name, c.arguments(), c.call_id) for c in calls))
    monkeypatch.setattr("app.integrations.direct_llm.generate_text", generate)
    provider = DirectLlmSupervisorSelectionProvider(material(), native_controls=True)
    errors = []
    async def run():
        for _ in range(2):
            with pytest.raises(RetrievalRouterOutputError) as caught:
                await provider.route(RetrievalRouterRequest(user_message="synthetic"))
            errors.append(caught.value)
    asyncio.run(run())
    assert errors[0].validation_code == "both_coordination_missing"
    assert errors[0].selection_validation["stages"]["entities"] == "pass"
    assert errors[0].selection_validation["stages"]["coordination"] == "fail"
    assert errors[1].validation_code == "entity_ref_invalid"
    assert errors[1].selection_validation["stages"]["entities"] == "fail"
    assert errors[1].selection_validation["stages"]["coordination"] == "not_evaluated"
    assert "INVALID_ALIAS" not in json.dumps(errors[1].selection_validation)


@pytest.mark.parametrize("outcome", ["unique", "missing", "duplicate", "hidden", "blocked"])
def test_position_mapping_still_uses_scoped_resolver_and_clarifies_without_guessing(outcome):
    options = SelectionArgumentOptions(True, True)
    payload = routing._payload("GRAPH")
    intent = parse_control_selection("", calls_for(payload, options), options=options)
    candidates = () if outcome == "missing" else (routing._candidate("safe-id", visible=outcome != "hidden", blocked=outcome == "blocked"),)
    if outcome == "duplicate": candidates += (routing._candidate("second-id"),)
    policy = routing._FakePolicy((routing.RetrievalEntityResolution("entity-1", candidates),))
    now = datetime.now(UTC)
    result = asyncio.run(RetrievalRoutingService(router=routing._FakeRouter(intent), policy=policy).route(routing._command(), now=now, deadline_at=now+timedelta(seconds=20)))
    if outcome == "unique":
        assert result.resolved.relationship_to_world_character_id == "safe-id"
        assert result.resolved.relationship_from_world_character_id == "responding-1"
    else:
        assert result.intent.route is RetrievalRoute.CLARIFICATION
        assert result.resolved.relationship_to_world_character_id is None
    assert result.resolved.world_id == "world-1"
    assert result.intent.coordination_hint is None


@pytest.mark.parametrize("options", OPTIONS)
def test_patches_use_real_sqlite_same_world_resolution_without_hidden_identity(retrieval_session, options):
    from app.runtime.chat.retrieval_policy import SqlAlchemyRetrievalPolicyResolver
    command = routing.RetrievalPreflightCommand(request_id="router-request", owner_id="router-owner",
        world_id="router-world", thread_id="router-thread", requester_world_character_id="router-requester",
        responding_world_character_id="router-responding", user_message="철수와 어제 왜 싸웠지?")
    intent = parse_control_selection("", calls_for(routing._payload("CANONICAL"), options), options=options)
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)
    result = asyncio.run(RetrievalRoutingService(router=routing._FakeRouter(intent),
        policy=SqlAlchemyRetrievalPolicyResolver(retrieval_session)).route(command,now=now,deadline_at=now+timedelta(seconds=30)))
    assert [b.world_character_id for b in result.resolved.entity_bindings] == ["router-cheolsu"]
    assert result.resolved.world_id == "router-world"
    assert result.resolved.relationship_from_world_character_id == "router-responding"
    assert result.resolved.relationship_to_world_character_id == "router-cheolsu"
    assert "router-hidden-cheolsu" not in repr(result.resolved.payload())


def test_concurrent_requests_and_partial_rollback_do_not_share_mapping(monkeypatch):
    options = SelectionArgumentOptions(True, True)
    async def generate(**kwargs):
        name = json.loads(kwargs["user_prompt"])["user_message"]
        payload = routing._payload("GRAPH")
        payload["entities"][0]["mention"] = name
        calls = calls_for(payload, options)
        await asyncio.sleep(0)
        return SimpleNamespace(text="", finish_reason="STOP", tool_calls=tuple(ProviderToolCall(c.name, c.arguments(), c.call_id) for c in calls))
    monkeypatch.setattr("app.integrations.direct_llm.generate_text", generate)
    provider = DirectLlmSupervisorSelectionProvider(material(), native_controls=True, code_coordination=True, positional_entity_refs=True)
    async def run():
        return await asyncio.gather(*(provider.route(RetrievalRouterRequest(user_message=name)) for name in ("Alpha", "Beta")))
    first, second = asyncio.run(run())
    assert first.intent.entities[0].ref == second.intent.entities[0].ref == "entity-1"
    assert (first.intent.entities[0].mention, second.intent.entities[0].mention) == ("Alpha", "Beta")
    for keep in (OPTIONS[1], OPTIONS[2], OPTIONS[0]):
        payload = routing._payload()
        parsed = parse_control_selection("", calls_for(payload, keep), options=keep)
        assert parsed.payload() == parse_retrieval_intent_payload(payload).payload()


def test_diagnostic_summary_separates_unknown_unreached_and_nonapplicable(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from evaluate_chat_supervisor_arguments import summarize
    attempts = [
        {"status":"failed", "code":"provider_failure", "validation":None},
        {"status":"failed", "code":"wire_failure", "validation":{
            "applicable":{"entities":True}, "stages":{"entities":"not_evaluated"}}},
        {"status":"ok", "validation":{"applicable":{"entities":False}, "stages":{"entities":"pass"}}},
        {"status":"ok", "validation":{"applicable":{"entities":True}, "stages":{"entities":"pass"}}},
    ]
    rows = [{"variant":"NA", "case":f"synthetic-{i}", "status":a["status"], "correct":False,
        "attempts":[a], "usage_attempts":[]} for i,a in enumerate(attempts)]
    counts = summarize(rows)["NA"]["stages_all_attempts"]["entities"]
    assert counts["applicable"] == 2
    assert counts["reached"] == counts["pass"] == counts["not_evaluated"] == 1
    assert counts["applicability_unknown"] == counts["not_applicable"] == 1


@pytest.mark.parametrize("maximum,started,planned,allowed", [
    (312, 260, 96, False), (356, 260, 96, True), (356, 261, 96, False),
])
def test_heldout_budget_cannot_be_silently_expanded(monkeypatch, maximum, started, planned, allowed):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from evaluate_chat_supervisor_arguments import validate_ledger
    ledger = {"maximum":maximum, "started":started}
    before = dict(ledger)
    if allowed:
        validate_ledger(ledger, planned, maximum)
    else:
        with pytest.raises(ValueError, match="evaluation_global_budget_invalid"):
            validate_ledger(ledger, planned, maximum)
    assert ledger == before
    with pytest.raises(ValueError, match="evaluation_global_budget_invalid"):
        validate_ledger(ledger, planned, maximum + 44)


@pytest.mark.parametrize("failure", ["core", "terminal", "first_pass", "unneeded_lookup", "incomplete"])
def test_heldout_cannot_bypass_development_gates(monkeypatch, failure):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from evaluate_chat_supervisor_arguments import development_entry_gate
    rows = [{"variant":"NA", "case":f"case-{i:02}", "status":"ok", "first_pass_valid":True,
             "correct":True, "expected":"CANONICAL", "effective":"CANONICAL"}
            for i in range(1, 9) for _ in range(3)]
    assert development_entry_gate(rows, "NA")
    if failure == "core": rows[6]["correct"] = False
    if failure == "terminal": rows[20]["status"] = "failed"
    if failure == "first_pass":
        rows[20]["first_pass_valid"] = rows[21]["first_pass_valid"] = False
    if failure == "unneeded_lookup": rows[20]["expected"] = "CURRENT_CONTEXT"
    if failure == "incomplete": rows.pop()
    assert not development_entry_gate(rows, "NA")
