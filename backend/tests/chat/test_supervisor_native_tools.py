"""Native transport and real ToolNode tests, without external calls or user data."""
import asyncio
from dataclasses import replace
import json
import sqlite3
from types import SimpleNamespace

import pytest
from google.genai import types

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.contracts.supervisor_selection import SelectionToolCall, parse_selection, SEMANTIC_FIELDS
from app.integrations.llm.supervisor_selection import selection_tools
from app.providers.contracts import ProviderRequest
from app.providers import gemini
from app.runtime.chat.retrieval_tools import RetrievalToolExecution, active_tool_execution, RetryingRead, validate_result
from chat.test_p8_l_p_evidence_response_streaming import _intent, _resolved, _Canonical, _Graph, NOW, response_session
from app.domains.chat.contracts.call_tracker import RouteAwareCallTracker, LlmNode
from datetime import timedelta


def call(name="CANONICAL", *, route=RetrievalRoute.CANONICAL, call_id="native-1"):
    intent = _intent(route)
    args = {key: intent.payload()[key] for key in SEMANTIC_FIELDS}
    return SelectionToolCall(call_id, name, json.dumps(args))


@pytest.mark.parametrize("names", [(), ("CANONICAL",), ("CANONICAL", "GRAPH")])
def test_gemini_native_wire_and_no_automatic_execution(monkeypatch, names):
    captured = []
    def generate_content(**kwargs):
        captured.append(kwargs)
        parts = [types.Part(function_call=types.FunctionCall(name=name, args={"intent": "historical_recall"}, id=f"native-{i}"), thought_signature=b"opaque") for i, name in enumerate(names)]
        if not parts:
            parts = [types.Part(text='{"route":"CURRENT_CONTEXT"}')]
        return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(parts=parts), finish_reason="STOP")])
    monkeypatch.setattr(gemini.genai, "Client", lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    result = gemini._generate_content_sync(ProviderRequest(
        api_key="synthetic", model="gemini-3.1-flash-lite", system_prompt="synthetic", user_prompt="synthetic",
        max_output_tokens=100, timeout_seconds=1, sdk_attempts=1, tools=selection_tools(),
    ))
    assert len(captured) == 1
    config = captured[0]["config"]
    assert config.automatic_function_calling.disable
    assert config.tool_config.function_calling_config.mode.value == "VALIDATED"
    assert config.response_mime_type is None and config.response_json_schema is None
    assert [x.name for x in config.tools[0].function_declarations] == ["CANONICAL", "GRAPH"]
    for definition in config.tools[0].function_declarations:
        assert definition.parameters_json_schema is None
        assert definition.parameters.properties["relationship"].nullable is True
        assert definition.parameters.properties["coordination_hint"].nullable is True
    assert [x.name for x in result.tool_calls] == list(names)
    assert all(x.thought_signature == b"opaque" for x in result.tool_calls)
    assert [x.call_id for x in result.tool_calls] == [f"native-{i}" for i in range(len(names))]


@pytest.mark.parametrize("route", [RetrievalRoute.CANONICAL, RetrievalRoute.GRAPH, RetrievalRoute.BOTH])
def test_native_selection(route):
    names = ("CANONICAL", "GRAPH") if route is RetrievalRoute.BOTH else (route.value,)
    calls = tuple(call(n, route=route, call_id=f"native-{i}") for i, n in enumerate(names))
    assert parse_selection("", calls).route is route


@pytest.mark.parametrize("finish", ["MAX_TOKENS", "SAFETY"])
def test_incomplete_provider_output_cannot_execute_even_valid_tool_arguments(monkeypatch, finish):
    from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider
    from app.domains.identity.contracts import CredentialPurpose
    from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest, RetrievalRouterOutputError
    from app.providers.contracts import ProviderToolCall
    material=SimpleNamespace(purpose=CredentialPurpose.MESSAGE_LLM,model="gemini-3.1-flash-lite",thinking_level="high",
        credential_id="synthetic",provider="google",fingerprint="synthetic",reveal=lambda:"synthetic")
    async def response(**kwargs):
        return SimpleNamespace(text="",finish_reason=finish,tool_calls=(ProviderToolCall("CANONICAL",call().arguments(),"native-1"),))
    monkeypatch.setattr("app.integrations.direct_llm.generate_text",response)
    with pytest.raises(RetrievalRouterOutputError) as error:
        asyncio.run(DirectLlmSupervisorSelectionProvider(material).route(RetrievalRouterRequest(user_message="synthetic")))
    assert error.value.validation_code=="native_output_incomplete"


def test_native_error_shape_never_copies_unknown_text_or_fields():
    from app.integrations.llm.supervisor_selection import _text_shape
    shape=_text_shape('{"control":{"private":"hidden"},"unknown_private_key":"hidden"}')
    assert shape["control"]=="other" and shape["other_key_count"]==1
    assert "private" not in json.dumps(shape) and "hidden" not in json.dumps(shape)


@pytest.mark.parametrize("control,slot", [("CURRENT_CONTEXT",None),("CLARIFICATION","entity_identity")])
def test_compact_no_tool_controls_preserve_semantics(control,slot):
    payload={"control":control,"intent":"current_context" if slot is None else "clarification_required",
        "entities":[],"relationship":None,"time_scope":None,"aggregation":None,"coordination_hint":None,"clarification_slot":slot}
    assert parse_selection(json.dumps(payload),()).route.value==control
    payload["world_id"]="foreign"
    with pytest.raises(RetrievalContractError): parse_selection(json.dumps(payload),())


@pytest.mark.parametrize("case", ["duplicate", "unknown", "duplicate_id", "conflict", "text", "empty", "foreign", "plain_fake"])
def test_selection_rejects_ambiguous_or_forged_requests(case):
    calls, text = (call(),), ""
    if case == "duplicate": calls = (call(), call(call_id="other"))
    if case == "unknown": calls = (call("BOTH"),)
    if case == "duplicate_id": calls = (call(route=RetrievalRoute.BOTH), call("GRAPH", route=RetrievalRoute.BOTH))
    if case == "conflict": calls = (call(), call("GRAPH", route=RetrievalRoute.BOTH, call_id="other"))
    if case == "text": text = '{"route":"CURRENT_CONTEXT"}'
    if case == "empty": calls = ()
    if case == "foreign": calls = (replace(call(), arguments_json='{"world_id":"foreign"}'),)
    if case == "plain_fake": calls, text = (), '{"tool_calls":[{"name":"CANONICAL"}]}'
    with pytest.raises(ValueError): parse_selection(text, calls)


def execution_fixture(route):
    request_id = "native-fixture"
    intent = _intent(route)
    names = ("CANONICAL", "GRAPH") if route is RetrievalRoute.BOTH else (route.value,)
    calls = tuple(call(n, route=route, call_id=f"native-{i}") for i,n in enumerate(names))
    resolved = _resolved(intent, request_id)
    execution = RetrievalToolExecution()
    execution.bind(SimpleNamespace(intent=intent, resolved=resolved, proposed_tool_calls=calls), SimpleNamespace(assert_active=lambda state: None), {})
    tracker = RouteAwareCallTracker(route, deadline_at=NOW+timedelta(minutes=2))
    tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=NOW)
    command = SimpleNamespace(resolved=resolved, call_tracker=tracker.snapshot())
    async def result(name):
        service = _Canonical() if name == "CANONICAL" else _Graph()
        return await service.plan_and_execute(command, now=NOW, deadline_at=NOW+timedelta(minutes=2))
    return execution, result


def test_actual_toolnode_parallel_join_and_duplicate_prevention():
    async def run():
        execution, result = execution_fixture(RetrievalRoute.BOTH)
        entered = set()
        async def job(name):
            entered.add(name)
            for _ in range(100):
                if len(entered) == 2: break
                await asyncio.sleep(.001)
            assert len(entered) == 2, "tools ran serially"
            return await result(name)
        values = await execution.run({name: lambda n=name: job(n) for name in ("CANONICAL", "GRAPH")})
        assert len(values) == 2
        execution.assert_complete()
        assert all(r.attempt == 1 for r in execution.receipts.values())
        with pytest.raises(RetrievalContractError, match="duplicate_execution"):
            await execution.run({"CANONICAL": lambda: job("CANONICAL")})
    asyncio.run(run())


def test_failed_parallel_branch_does_not_lose_or_repeat_success():
    async def run():
        execution, result = execution_fixture(RetrievalRoute.BOTH)
        async def fail(): raise RetrievalContractError("synthetic_failure")
        async def success():
            await asyncio.sleep(.005)
            return await result("GRAPH")
        with pytest.raises(RetrievalContractError, match="synthetic_failure"):
            await execution.run({"CANONICAL": fail, "GRAPH": success})
        assert execution.receipts["GRAPH"].status == "completed"
        assert execution.receipts["CANONICAL"].status == "failed"
        with pytest.raises(RetrievalContractError, match="result_missing"): execution.assert_complete()
    asyncio.run(run())


def test_result_contract_empty_short_circuit_foreign_and_missing():
    async def run():
        execution, result = execution_fixture(RetrievalRoute.CANONICAL)
        value = await result("CANONICAL")
        validate_result("CANONICAL", value, execution.request_id)
        with pytest.raises(RetrievalContractError): validate_result("CANONICAL", replace(value, request_id="foreign"), execution.request_id)
        with pytest.raises(RetrievalContractError): validate_result("CANONICAL", replace(value, metrics=replace(value.metrics, short_circuited=False)), execution.request_id)
    asyncio.run(run())


def test_executor_retry_is_one_failed_read_shared_across_axes():
    execution, _ = execution_fixture(RetrievalRoute.BOTH)
    counter = [0]
    def read():
        counter[0] += 1
        error = sqlite3.OperationalError("synthetic busy")
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raise error
    token = active_tool_execution.set(execution)
    try:
        wrapper = RetryingRead(SimpleNamespace(execute=read))
        with pytest.raises(sqlite3.OperationalError): wrapper.execute()
        assert counter[0] == 2 and execution.read_retries == 1
        with pytest.raises(sqlite3.OperationalError): wrapper.execute()
        assert counter[0] == 3
    finally: active_tool_execution.reset(token)


def test_cancellation_stops_tool_completion_and_freeze():
    async def run():
        execution, _ = execution_fixture(RetrievalRoute.CANONICAL)
        entered = asyncio.Event()
        async def job():
            entered.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(execution.run({"CANONICAL": job}))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        with pytest.raises(RetrievalContractError, match="result_missing"):
            execution.assert_complete()
    asyncio.run(run())


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign", "artifact"])
def test_toolmessage_contract_does_not_accept_transport_tampering(monkeypatch, mutation):
    from app.runtime.chat import retrieval_tools
    original = retrieval_tools.ToolNode
    class MutatedToolNode(original):
        async def ainvoke(self, *args, **kwargs):
            output = await super().ainvoke(*args, **kwargs)
            messages = output["messages"]
            if mutation == "missing": output["messages"] = []
            elif mutation == "duplicate": output["messages"] = messages * 2
            elif mutation == "foreign": messages[0].tool_call_id = "foreign"
            else: messages[0].artifact = object()
            return output
    monkeypatch.setattr(retrieval_tools, "ToolNode", MutatedToolNode)
    async def run():
        execution, result = execution_fixture(RetrievalRoute.CANONICAL)
        with pytest.raises(RetrievalContractError):
            await execution.run({"CANONICAL": lambda: result("CANONICAL")})
    asyncio.run(run())


@pytest.mark.parametrize("recipe,intent_name", [("INDEPENDENT_PARALLEL","mixed_evidence"),("GRAPH_THEN_CANONICAL","relationship_cause"),("CANONICAL_THEN_GRAPH","event_aggregation")])
@pytest.mark.parametrize("empty", [False,True])
def test_existing_coordinator_recipes_through_actual_tools(recipe, intent_name, empty):
    from chat import test_p8_l_n_both_workflow_coordinator as fixtures
    from app.runtime.chat.retrieval_tools import ToolPlanningService, ToolBothCoordinator, parallel_tools
    async def run():
        intent, resolved = fixtures._resolved(intent_name=intent_name,hint=recipe)
        coordinator, canonical, graph = fixtures._coordinator(resolved,
            canonical_recall=fixtures._CanonicalRecall(empty=empty),graph_recall=fixtures._GraphRecall(empty=empty))
        coordinator._canonical=ToolPlanningService("CANONICAL",coordinator._canonical)
        coordinator._graph=ToolPlanningService("GRAPH",coordinator._graph)
        coordinator._parallel_runner=parallel_tools
        execution=RetrievalToolExecution()
        args=json.dumps({key:intent.payload()[key] for key in SEMANTIC_FIELDS})
        calls=tuple(SelectionToolCall(f"native-{i}",name,args) for i,name in enumerate(("CANONICAL","GRAPH")))
        execution.bind(SimpleNamespace(intent=intent,resolved=resolved,proposed_tool_calls=calls),SimpleNamespace(assert_active=lambda s:None),{})
        token=active_tool_execution.set(execution)
        try:
            value=await ToolBothCoordinator(coordinator).coordinate(fixtures._command(intent,resolved),now=fixtures.NOW,deadline_at=fixtures.DEADLINE)
            execution.assert_complete()
            assert len(canonical.requests)<=1 and len(graph.requests)<=1
            if empty and recipe!="INDEPENDENT_PARALLEL":
                assert sum(r.status=="skipped_dependency" for r in execution.receipts.values())==1
            else: assert len(canonical.requests)==len(graph.requests)==1
            assert value.selection.selected.value==recipe
        finally: active_tool_execution.reset(token)
    asyncio.run(run())


@pytest.mark.parametrize("route", [RetrievalRoute.CURRENT_CONTEXT,RetrievalRoute.CANONICAL,RetrievalRoute.GRAPH,RetrievalRoute.CLARIFICATION])
def test_native_selection_to_toolnode_freeze_crg_once(response_session, route):
    from chat.test_p8_l_p_evidence_response_streaming import _Router,_workflow,_request,_command,_Generator,_collect
    from app.runtime.chat.retrieval_tools import ToolPlanningService
    from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
    class NativeSelection(_Router):
        async def route(self,*args,**kwargs):
            result=await super().route(*args,**kwargs)
            calls=() if route in {RetrievalRoute.CURRENT_CONTEXT,RetrievalRoute.CLARIFICATION} else (call(route.value,route=route),)
            return replace(result,selection_mode="native",proposed_tool_calls=calls)
    record=_request(response_session,route)
    response_session.commit()
    generator=_Generator()
    selector=NativeSelection(route)
    workflow=_workflow(response_session,route,generator,router=selector)
    workflow._canonical=ToolPlanningService("CANONICAL",workflow._canonical)
    workflow._graph=ToolPlanningService("GRAPH",workflow._graph)
    events=asyncio.run(_collect(workflow.run(_command(record))))
    assert events[-1].event_type is GenerationEventType.COMPLETED
    assert selector.calls==1 and len(generator.requests)==1
    expected=3 if route in {RetrievalRoute.CANONICAL,RetrievalRoute.GRAPH} else 2
    assert workflow._lifecycle.get_request(record.request_id).call_tracker["logical_total"]==expected
