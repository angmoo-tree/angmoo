"""Native selection receipts -> validated ToolNode batches -> typed artifacts.

The context is per response, never graph-global. Selection AI is not called
again to judge results; validated evidence still reaches the persona writer.
"""
import asyncio
import sqlite3
import hashlib
from contextvars import ContextVar
from dataclasses import dataclass, replace

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from sqlalchemy.exc import OperationalError

from app.contracts.retrieval_observation import observe
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.supervisor_selection import CONTROL_NAMES, effective_calls, execution_arguments_schema
from app.domains.chat.service.canonical_retrieval import CanonicalPlanningResult
from app.domains.chat.service.graph_retrieval import GraphPlanningResult

active_tool_execution: ContextVar = ContextVar("chat_tool_execution", default=None)
_inside_tool: ContextVar = ContextVar("chat_inside_tool", default=False)


def validate_result(name, result, request_id, envelope_hash=None):
    from app.domains.chat.service.hybrid_canonical import HybridCanonicalResult
    if isinstance(result, HybridCanonicalResult):
        if (name != "CANONICAL" or result.request_id != request_id or result.recall.request_id != request_id
            or result.recall.envelope_hash != envelope_hash or not isinstance(result.call_tracker, dict)):
            raise RetrievalContractError("chat_tool_result_contract_invalid")
        return
    expected = CanonicalPlanningResult if name == "CANONICAL" else GraphPlanningResult
    if not isinstance(result, expected) or result.request_id != request_id or not isinstance(result.call_tracker, dict):
        raise RetrievalContractError("chat_tool_result_contract_invalid")
    if result.metrics.short_circuited:
        if result.plan is not None or result.execution is not None or not result.metrics.short_circuit_reason:
            raise RetrievalContractError("chat_tool_short_circuit_invalid")
        return
    execution = result.execution
    if result.plan is None or execution is None or execution.request_id != request_id or execution.plan != result.plan:
        raise RetrievalContractError("chat_tool_execution_missing")
    if envelope_hash is not None and result.plan.envelope_hash != envelope_hash:
        raise RetrievalContractError("chat_tool_result_scope_mismatch")
    if not isinstance(execution.steps, tuple) or [s.id for s in result.plan.steps] != [s.step_id for s in execution.steps]:
        raise RetrievalContractError("chat_tool_step_result_missing")
    for step in execution.steps:
        if name == "CANONICAL":
            if not isinstance(step.result.records, tuple):
                raise RetrievalContractError("chat_tool_records_invalid")
        elif not isinstance(step.results, tuple) or (not step.dependency_short_circuited and len(step.queries) != len(step.results)):
            raise RetrievalContractError("chat_tool_records_invalid")


@dataclass
class ToolReceipt:
    call: object
    status: str = "ready"
    attempt: int = 0
    result: object = None


class RetrievalToolExecution:
    def __init__(self):
        self.receipts = {}
        self.request_id = None
        self.steps = None
        self.state = None
        self.read_retries = 0
        self.envelope_hash = None
        self.control_receipts = {}
        self.control_messages = []

    def bind(self, routing, steps, state):
        if self.request_id is not None:
            raise RetrievalContractError("chat_tool_selection_already_bound")
        self.request_id = routing.resolved.request_id
        self.envelope_hash = routing.resolved.envelope_hash
        self.steps, self.state = steps, state
        self.receipts = {c.name: ToolReceipt(c) for c in effective_calls(self.request_id, routing.intent, routing.proposed_tool_calls)}
        from app.domains.chat.contracts.recall_mode import ChatRecallMode
        mode = ChatRecallMode(getattr(getattr(steps, "command", None), "recall_mode", "legacy_checkpoint"))
        if not mode.graph_tools_enabled and "GRAPH" in self.receipts:
            raise RetrievalContractError("chat_graph_tool_disabled")
        control_routes = {"USE_CONTEXT": "CURRENT_CONTEXT", "REQUEST_CLARIFICATION": "CLARIFICATION"}
        for call in routing.proposed_tool_calls:
            if call.name in CONTROL_NAMES:
                status = "ready" if control_routes[call.name] == routing.intent.route.value else "suppressed"
                self.control_receipts[call.name] = ToolReceipt(call, status=status)
                observe("control_selection", operation=call.name, status=status, call_ref=_call_ref(call.call_id))
                continue
            observe("tool_selection", axis=call.name.lower(), source="model", status="selected" if call.name in self.receipts else "suppressed")
        for receipt in self.receipts.values():
            observe("tool_effective", axis=receipt.call.name.lower(), source=receipt.call.origin, status="ready", call_ref=_call_ref(receipt.call.call_id))

    def assert_complete(self):
        if any(r.status not in {"completed", "suppressed"} for r in self.control_receipts.values()):
            raise RetrievalContractError("chat_control_result_missing")
        # Dependency-skipped second axes are explicitly accounted for by BOTH.
        if any(r.status not in {"completed", "skipped_dependency"} for r in self.receipts.values()):
            raise RetrievalContractError("chat_tool_result_missing")

    def complete_control(self, route):
        name = {"CURRENT_CONTEXT": "USE_CONTEXT", "CLARIFICATION": "REQUEST_CLARIFICATION"}.get(route)
        receipt = self.control_receipts.get(name)
        if receipt is None or receipt.status == "suppressed":
            return  # Existing guard may produce the control without a model call.
        if receipt.status != "ready":
            raise RetrievalContractError("chat_control_duplicate_execution")
        receipt.status, receipt.attempt = "completed", 1
        receipt.result = {"control": route, "retrieval_executed": False}
        self.control_messages.append(ToolMessage(
            content="prepared", name=name, tool_call_id=receipt.call.call_id,
            status="success", artifact=receipt.result,
        ))
        observe("control_return", operation=name, status="completed", executed=False, call_ref=_call_ref(receipt.call.call_id))

    async def run(self, jobs, *, return_exceptions=False):
        if self.request_id is None or not jobs or not set(jobs) <= self.receipts.keys():
            raise RetrievalContractError("chat_tool_unrequested")
        tools = []
        native = []
        for name, job in jobs.items():
            receipt = self.receipts[name]
            if receipt.status != "ready":
                raise RetrievalContractError("chat_tool_duplicate_execution")
            receipt.status, receipt.attempt = "running", 1

            async def invoke(_job=job, _name=name, _receipt=receipt, **arguments):
                if arguments != _receipt.call.arguments():
                    raise RetrievalContractError("chat_tool_arguments_mismatch")
                token = _inside_tool.set(True)
                try:
                    self.steps.assert_active(self.state)
                    value = await _job()
                    self.steps.assert_active(self.state)
                    validate_result(_name, value, self.request_id, self.envelope_hash)
                    from app.domains.chat.service.hybrid_canonical import HybridCanonicalResult
                    from app.domains.chat.contracts.recall_mode import ChatRecallMode
                    is_hybrid = ChatRecallMode(getattr(getattr(self.steps, "command", None), "recall_mode", "legacy_checkpoint")) is ChatRecallMode.SOCIAL_HYBRID
                    if _name == "CANONICAL" and is_hybrid != isinstance(value, HybridCanonicalResult):
                        raise RetrievalContractError("chat_tool_result_mode_mismatch")
                    if isinstance(value, HybridCanonicalResult):
                        resolved = self.state["routing"].resolved
                        scope = value.recall.scope
                        if (value.recall.call_id != _receipt.call.call_id or
                            (scope.owner_id, scope.world_id, scope.subject_world_character_id) !=
                            (resolved.owner_id, resolved.world_id, resolved.responding_world_character_id)):
                            raise RetrievalContractError("chat_tool_result_scope_mismatch")
                    _receipt.result, _receipt.status = value, "completed"
                    observe("tool_return", axis=_name.lower(), status="completed", executed=True, call_ref=_call_ref(_receipt.call.call_id), attempt=_receipt.attempt)
                    return ToolMessage(content="completed", name=_name, tool_call_id=_receipt.call.call_id,
                                       status="success", artifact=value)
                except asyncio.CancelledError:
                    _receipt.status = "failed"
                    observe("tool_return", axis=_name.lower(), status="cancelled", call_ref=_call_ref(_receipt.call.call_id), attempt=_receipt.attempt)
                    raise
                except Exception as exc:
                    # Await every parallel receipt before propagating terminal failure.
                    # Never turn a failed branch into empty evidence.
                    _receipt.status, _receipt.result = "failed", exc
                    observe("tool_return", axis=_name.lower(), status="failed", call_ref=_call_ref(_receipt.call.call_id), attempt=_receipt.attempt)
                    return ToolMessage(content="failed", name=_name, tool_call_id=_receipt.call.call_id,
                                       status="error", artifact=exc)
                finally:
                    _inside_tool.reset(token)

            tools.append(StructuredTool.from_function(coroutine=invoke, name=name, description="Execute a code-validated retrieval request.", args_schema=execution_arguments_schema(graph_query_contract="graph_queries" in receipt.call.arguments(), hybrid_recall="search_text" in receipt.call.arguments())))
            native.append({"name": name, "args": receipt.call.arguments(), "id": receipt.call.call_id, "type": "tool_call"})
        node = ToolNode(tools, handle_tool_errors=False)
        batch = StateGraph(dict)
        batch.add_node("retrieval_tools", node)
        batch.add_edge(START, "retrieval_tools")
        batch.add_edge("retrieval_tools", END)
        output = await batch.compile().ainvoke(
            {"messages": [AIMessage(content="", tool_calls=native)]},
            config={"recursion_limit": 3},
        )
        messages = output.get("messages")
        if not isinstance(messages, list) or len(messages) != len(jobs):
            raise RetrievalContractError("chat_tool_message_missing")
        expected = {r.call.call_id: name for name, r in self.receipts.items() if name in jobs}
        received = {}
        for message in messages:
            if not isinstance(message, ToolMessage) or message.tool_call_id not in expected or message.tool_call_id in received:
                raise RetrievalContractError("chat_tool_message_mismatch")
            name = expected[message.tool_call_id]
            expected_status = "success" if self.receipts[name].status == "completed" else "error"
            if message.name != name or message.status != expected_status or message.artifact is not self.receipts[name].result:
                raise RetrievalContractError("chat_tool_artifact_mismatch")
            received[message.tool_call_id] = message.artifact
        values = [received[self.receipts[name].call.call_id] for name in jobs]
        if not return_exceptions:
            for value in values:
                if isinstance(value, BaseException):
                    raise value
        return values


class ToolPlanningService:
    """Single/serial calls use ToolNode; a ready parallel batch already owns it."""
    def __init__(self, name, service):
        self.name, self.service = name, service

    async def plan_and_execute(self, command, **kwargs):
        execution = active_tool_execution.get()
        if execution is None or command.resolved.request_id != execution.request_id or command.resolved.envelope_hash != execution.envelope_hash:
            raise RetrievalContractError("chat_tool_command_scope_mismatch")
        if self.name == "CANONICAL" and command.intent.search_text is not None:
            command = replace(command, call_id=execution.receipts[self.name].call.call_id)
        if _inside_tool.get():
            return await self.service.plan_and_execute(command, **kwargs)
        return (await execution.run({self.name: lambda: self.service.plan_and_execute(command, **kwargs)}))[0]


async def parallel_tools(jobs):
    execution = active_tool_execution.get()
    if execution is None:
        raise RetrievalContractError("chat_tool_request_context_missing")
    # BOTH owns failure precedence and must receive every axis outcome.
    return await execution.run(jobs, return_exceptions=True)


class ToolBothCoordinator:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    async def coordinate(self, command, **kwargs):
        result = await self.coordinator.coordinate(command, **kwargs)
        if result.metrics.downstream_short_circuited:
            execution = active_tool_execution.get()
            for receipt in execution.receipts.values():
                if receipt.status == "ready":
                    receipt.status = "skipped_dependency"
                    observe("tool_return", axis=receipt.call.name.lower(), status="skipped_dependency", skipped=True)
        return result


class RetryingRead:
    """Retry only a failed SQLite busy/locked read, never a whole plan/LLM.

    Other gateway errors/degraded results keep their existing policy. The
    request-wide token is shared by both axes and all plan steps.
    """
    def __init__(self, service):
        self.service = service

    def execute(self, *args, **kwargs):
        try:
            return self.service.execute(*args, **kwargs)
        except (sqlite3.OperationalError, OperationalError) as exc:
            original = getattr(exc, "orig", exc)
            code = getattr(original, "sqlite_errorcode", None)
            execution = active_tool_execution.get()
            if code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or execution is None or execution.read_retries >= 1:
                raise
            execution.steps.assert_active(execution.state)
            execution.read_retries += 1
            observe("executor_retry", reason="sqlite_busy", step=1)
            return self.service.execute(*args, **kwargs)


def _call_ref(call_id):
    return "call-" + hashlib.sha256(call_id.encode()).hexdigest()[:16]
