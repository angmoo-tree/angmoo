"""LangGraph wiring only; request resources live in the runtime context."""

from functools import lru_cache

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.contracts.retrieval_observation import observe
from app.domains.chat.contracts.response_execution import (
    ResponseAction,
    ResponseExecutionError,
    ResponseGraphState,
    ResponseStepRunner,
)
from app.domains.chat.policies import select_response_action
from app.runtime.chat.retrieval_tools import active_tool_execution, RetrievalToolExecution


async def _supervisor(state: ResponseGraphState, runtime: Runtime[ResponseStepRunner]):
    runtime.context.assert_active(state)
    action = select_response_action(state)
    observe(
        "supervisor",
        step=state["visits"] + 1,
        phase=state["phase"].value,
        operation=action.value,
        reason="phase_ready",
    )
    update = {**state, "visits": state["visits"] + 1, "action": action}
    if action is ResponseAction.ROUTE:
        # Initial AI selection and deterministic scope resolution belong here.
        update = await runtime.context.execute(action, update)
        runtime.context.assert_active(update)
        execution = active_tool_execution.get()
        if execution is not None and update["routing"].selection_mode in {"native", "native_control"}:
            execution.bind(update["routing"], runtime.context, update)
    elif action is ResponseAction.FREEZE:
        execution = active_tool_execution.get()
        if execution is not None:
            execution.assert_complete()
    return update


def _worker(action: ResponseAction):
    async def run(state: ResponseGraphState, runtime: Runtime[ResponseStepRunner]):
        result = await runtime.context.execute(action, state)
        if action in {ResponseAction.CURRENT, ResponseAction.CLARIFY}:
            runtime.context.assert_active(result)
            execution = active_tool_execution.get()
            if execution is not None:
                execution.complete_control(result["routing"].intent.route.value)
        return result

    return run


async def _next(state: ResponseGraphState):
    return state["action"].value


@lru_cache(maxsize=1)
def compiled_response_graph():
    graph = StateGraph(ResponseGraphState, context_schema=ResponseStepRunner)
    graph.add_node("supervisor", _supervisor)
    paths = {ResponseAction.END.value: END, ResponseAction.ROUTE.value: "supervisor"}
    for action in ResponseAction:
        if action in {ResponseAction.END, ResponseAction.ROUTE}:
            continue
        graph.add_node(action.value, _worker(action))
        graph.add_edge(action.value, "supervisor")
        paths[action.value] = action.value
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _next, paths)
    return graph.compile()


class LangGraphResponseExecutor:
    async def run(
        self, state: ResponseGraphState, steps: ResponseStepRunner
    ) -> ResponseGraphState:
        try:
            token = active_tool_execution.set(RetrievalToolExecution())
            return await compiled_response_graph().ainvoke(
                # Five Supervisor phases + three workers = eight graph steps;
                # repairs/ToolNode batches are bounded inside their owning step.
                state, context=steps, config={"recursion_limit": 10}
            )
        except GraphRecursionError as exc:
            raise ResponseExecutionError("chat_supervisor_step_limit") from exc
        finally:
            active_tool_execution.reset(token)
