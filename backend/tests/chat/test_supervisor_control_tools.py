"""Native selection controls preserve the existing guard and execution boundary."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.contracts.supervisor_selection import SelectionToolCall, SEMANTIC_FIELDS, parse_control_selection
from app.integrations.llm.supervisor_selection import control_selection_tools
from app.providers.contracts import ProviderRequest
from app.providers import gemini
from app.runtime.chat.retrieval_tools import RetrievalToolExecution
from chat.test_p8_l_p_evidence_response_streaming import _intent, _resolved, response_session


def native(route):
    intent = _intent(route)
    args = {key: intent.payload()[key] for key in SEMANTIC_FIELDS}
    name = {RetrievalRoute.CURRENT_CONTEXT: "USE_CONTEXT", RetrievalRoute.CLARIFICATION: "REQUEST_CLARIFICATION"}.get(route, route.value)
    if route is RetrievalRoute.CLARIFICATION:
        args["clarification_slot"] = intent.clarification_slot
        args["intent"] = "clarification_required"
    elif route is RetrievalRoute.CURRENT_CONTEXT:
        args["intent"] = "current_context"
    return SelectionToolCall("control-test", name, json.dumps(args))


@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CLARIFICATION, RetrievalRoute.CANONICAL, RetrievalRoute.GRAPH])
def test_native_control_and_retrieval_parse(route):
    assert parse_control_selection("", (native(route),)).route is route


@pytest.mark.parametrize("mutation", ["text", "none", "mixed", "duplicate", "missing", "unknown", "invalid_slot"])
def test_invalid_control_never_executes(mutation):
    text, calls = "", (native(RetrievalRoute.CURRENT_CONTEXT),)
    if mutation == "text": text = '{"control":"CANONICAL"}'
    elif mutation == "none": calls = ()
    elif mutation == "mixed": calls += (replace(native(RetrievalRoute.GRAPH), call_id="other"),)
    elif mutation == "duplicate": calls += (replace(calls[0], call_id="other"),)
    elif mutation == "missing": calls = (replace(calls[0], arguments_json="{}"),)
    elif mutation == "unknown": calls = (replace(calls[0], name="BOTH"),)
    else:
        call = native(RetrievalRoute.CLARIFICATION)
        calls = (replace(call, arguments_json=json.dumps({**call.arguments(), "clarification_slot":"private-secret"})),)
    with pytest.raises(ValueError): parse_control_selection(text, calls)


def test_required_mode_is_request_scoped(monkeypatch):
    from google.genai import types
    captured = []
    def generate_content(**kwargs):
        captured.append(kwargs["config"])
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=[types.Part(text="test")]), finish_reason="STOP")])
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    def config(request):
        gemini._generate_content_sync(request)
        return captured[-1]
    request = ProviderRequest(api_key="synthetic", model="gemini-3.1-flash-lite", system_prompt="test", user_prompt="test", max_output_tokens=3072, timeout_seconds=30, tools=control_selection_tools(), require_tool_call=True)
    required = config(request)
    assert required.tool_config.function_calling_config.mode.value == "ANY"
    assert required.automatic_function_calling.disable is True
    assert [tool.name for tool in required.tools[0].function_declarations] == ["CANONICAL", "GRAPH", "USE_CONTEXT", "REQUEST_CLARIFICATION"]
    assert config(replace(request, require_tool_call=False)).tool_config.function_calling_config.mode.value == "VALIDATED"
    assert config(replace(request, tools=(), require_tool_call=False)).tool_config is None
    with pytest.raises(ValueError, match="declarations_missing"):
        config(replace(request, tools=()))


@pytest.mark.parametrize("enabled", [False, True])
def test_selector_experiment_is_opt_in_and_preserves_default(monkeypatch, enabled):
    from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider
    from app.domains.identity.contracts import CredentialPurpose
    from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
    from app.providers.contracts import ProviderToolCall
    import json
    material = SimpleNamespace(purpose=CredentialPurpose.MESSAGE_LLM, model="gemini-3.1-flash-lite", thinking_level="high", credential_id="synthetic", provider="google", fingerprint="synthetic", reveal=lambda: "synthetic")
    captured = []
    control = native(RetrievalRoute.CURRENT_CONTEXT)
    async def response(**kwargs):
        captured.append(kwargs)
        if enabled:
            return SimpleNamespace(text="", finish_reason="STOP", tool_calls=(ProviderToolCall(control.name, control.arguments(), control.call_id),))
        return SimpleNamespace(text=json.dumps({**control.arguments(), "control":"CURRENT_CONTEXT", "clarification_slot":None}), finish_reason="STOP", tool_calls=())
    monkeypatch.setattr("app.integrations.direct_llm.generate_text", response)
    provider = DirectLlmSupervisorSelectionProvider(material, native_controls=True) if enabled else DirectLlmSupervisorSelectionProvider(material)
    result = asyncio.run(provider.route(RetrievalRouterRequest(user_message="hello")))
    assert result.intent.route is RetrievalRoute.CURRENT_CONTEXT
    assert result.selection_mode == ("native_control" if enabled else "native")
    assert captured[0]["require_tool_call"] is enabled
    assert len(captured[0]["tools"]) == (4 if enabled else 2)


@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CLARIFICATION])
def test_control_receipt_requires_actual_preparation_and_has_no_retrieval(route):
    intent = _intent(route)
    execution = RetrievalToolExecution()
    execution.bind(SimpleNamespace(intent=intent, resolved=_resolved(intent, "control-request"), proposed_tool_calls=(native(route),)), SimpleNamespace(assert_active=lambda state: None), {})
    assert not execution.receipts
    with pytest.raises(RetrievalContractError, match="control_result_missing"): execution.assert_complete()
    execution.complete_control(route.value)
    execution.assert_complete()
    assert len(execution.control_messages) == 1
    assert execution.control_messages[0].tool_call_id == "control-test"
    assert execution.control_messages[0].artifact["retrieval_executed"] is False
    with pytest.raises(RetrievalContractError, match="duplicate"): execution.complete_control(route.value)


def test_guard_promoted_context_is_not_counted_as_model_search():
    intent = _intent(RetrievalRoute.CANONICAL)
    execution = RetrievalToolExecution()
    execution.bind(SimpleNamespace(intent=intent, resolved=_resolved(intent, "guard-request"), proposed_tool_calls=(native(RetrievalRoute.CURRENT_CONTEXT),)), SimpleNamespace(assert_active=lambda state: None), {})
    assert execution.control_receipts["USE_CONTEXT"].status == "suppressed"
    assert execution.receipts["CANONICAL"].call.origin == "code_guard"
    assert not execution.control_messages
    with pytest.raises(RetrievalContractError, match="tool_result_missing"): execution.assert_complete()


@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT, RetrievalRoute.CLARIFICATION])
def test_control_graph_prepares_then_crg_once_without_planner(response_session, route, monkeypatch):
    from chat.test_p8_l_p_evidence_response_streaming import _Router, _workflow, _request, _command, _Generator, _collect
    from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
    from app.runtime.chat import response_graph
    ledgers = []
    class Ledger(RetrievalToolExecution):
        def __init__(self):
            super().__init__()
            ledgers.append(self)
    monkeypatch.setattr(response_graph, "RetrievalToolExecution", Ledger)
    class Selector(_Router):
        async def route(self, *args, **kwargs):
            result = await super().route(*args, **kwargs)
            return replace(result, selection_mode="native_control", proposed_tool_calls=(native(route),))
    record = _request(response_session, route)
    response_session.commit()
    generator = _Generator()
    selector = Selector(route)
    workflow = _workflow(response_session, route, generator, router=selector)
    class NoLookup:
        async def plan_and_execute(self, *args, **kwargs): pytest.fail("control performed retrieval")
    workflow._canonical = workflow._graph = NoLookup()
    events = asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    assert selector.calls == len(generator.requests) == 1
    assert workflow._lifecycle.get_request(record.request_id).call_tracker["logical_total"] == 2
    assert len(ledgers[0].control_messages) == 1
    ledgers[0].assert_complete()
