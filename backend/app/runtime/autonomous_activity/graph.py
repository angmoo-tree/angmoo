"""Actual nested LangGraph execution with small, checkpointable stage results."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.runtime.autonomous_activity.contracts import (
    Candidate, INBOX_TARGET_LIMIT, LaneState, ParentState, Selection,
)
from app.runtime.autonomous_activity.queries import resolve_query, validate_selection

Node = Callable[[dict], Awaitable[dict]]


@dataclass(frozen=True)
class LanePorts:
    """Concrete domain adapters; no Session/provider is serialized in State.

    Each effectful port revalidates scope/claim/revisions and uses its canonical
    receipt. Checkpoint success alone is not evidence of a committed action.
    """
    load_candidates: Node
    select: Node
    recall: Node
    build_context: Node
    plan: Node
    validate: Node
    write: Node
    execute: Node
    settle: Node
    finalize: Node
    guard: Node
    resolve_routine_query: Node | None = None
    on_error: Callable[[Exception], Awaitable[dict]] | None = None


def build_lane(lane: str, ports: LanePorts):
    builder = StateGraph(LaneState)

    def guarded(name: str, callback: Node):
        async def invoke(state):
            await ports.guard({**state, "stage": name})
            if name == "Execute" and state.get("failure"):
                return {"executions": []}
            try:
                return await callback(state)
            except Exception as exc:
                from app.integrations.direct_llm import DirectLlmError, DirectLlmDeferred
                if name != "Writer" or isinstance(exc, DirectLlmDeferred) or not isinstance(exc, (ValueError, DirectLlmError)):
                    raise
                # A normal Planner already interpreted experience. Keep its
                # settlement independent of failed public expression.
                return {"failure": {"stage": name, "reason": type(exc).__name__}, "drafts": []}
        return invoke

    async def select(state):
        candidates = [Candidate.model_validate(c) for c in state.get("candidates", [])]
        if len(candidates) == 1:
            return {"selections": [Selection(target_id=candidates[0].target_id).model_dump()]}
        payload = await ports.select(state)
        selected = validate_selection(payload, candidates, INBOX_TARGET_LIMIT if lane == "inbox" else 1)
        return {"selections": [s.model_dump() for s in selected]}

    async def queries(state):
        if lane == "routine":
            if ports.resolve_routine_query is None:
                raise ValueError("routine_query_port_missing")
            return await ports.resolve_routine_query(state)
        candidates = {c["target_id"]: Candidate.model_validate(c) for c in state["candidates"]}
        return {"queries": [resolve_query(Selection.model_validate(s), candidates[s["target_id"]], lane=lane).model_dump()
                            for s in state["selections"]]}

    builder.add_node("LoadCandidates", guarded("LoadCandidates", ports.load_candidates))
    builder.add_node("TargetSelector", guarded("TargetSelector", select))
    builder.add_node("ResolveQuery", guarded("ResolveQuery", queries))
    for name, callback in (
        ("RecallSelected", ports.recall), ("BuildDecisionContext", ports.build_context),
        ("ActionPlanner", ports.plan), ("ValidateDecision", ports.validate),
        ("Writer", ports.write), ("Execute", ports.execute),
        ("Settle", ports.settle), ("PathResult", ports.finalize),
    ):
        builder.add_node(name, guarded(name, callback))
    builder.add_edge(START, "LoadCandidates")
    builder.add_conditional_edges("LoadCandidates", lambda s: (
        "PathResult" if not s.get("candidates") else "ResolveQuery" if lane == "routine" else "TargetSelector"
    ), ["PathResult", "ResolveQuery", "TargetSelector"])
    builder.add_conditional_edges("TargetSelector", lambda s: "ResolveQuery" if s.get("selections") else "PathResult", ["ResolveQuery", "PathResult"])
    builder.add_edge("ResolveQuery", "RecallSelected")
    builder.add_edge("RecallSelected", "BuildDecisionContext")
    builder.add_edge("BuildDecisionContext", "ActionPlanner")
    builder.add_edge("ActionPlanner", "ValidateDecision")
    builder.add_conditional_edges("ValidateDecision", lambda s: "Writer" if s.get("assignments") else "Execute", ["Writer", "Execute"])
    builder.add_edge("Writer", "Execute")
    builder.add_edge("Execute", "Settle")
    builder.add_edge("Settle", "PathResult")
    builder.add_edge("PathResult", END)
    # Inherit the parent's durable saver and per-invocation namespace.
    return builder.compile(name=f"{lane.capitalize()}ActivityGraph")


def build_autonomous_graph(*, lanes: dict[str, LanePorts], load_context: Node,
                           refresh: Node, finalize: Node, checkpointer: Any):
    builder = StateGraph(ParentState)
    builder.add_node("LoadContext", load_context)
    for lane in ("inbox", "routine", "feed"):
        graph = build_lane(lane, lanes[lane])

        async def invoke(state, config, child=graph, path=lane, port=lanes[lane]):
            # Private lane channels never bleed into another lane's state.
            try:
                result = await child.ainvoke({"identity": state["identity"], "shared_context": state["shared_context"]}, config)
            except Exception as exc:
                if port.on_error is None:
                    raise
                return {f"{path}_result": await port.on_error(exc)}
            return {f"{path}_result": result.get("result", {})}

        builder.add_node(f"{lane.capitalize()}ActivityGraph", invoke)
    builder.add_node("RefreshAfterInbox", refresh)
    builder.add_node("RefreshAfterRoutine", refresh)
    builder.add_node("Finalize", finalize)
    sequence = [START, "LoadContext", "InboxActivityGraph", "RefreshAfterInbox", "RoutineActivityGraph",
                "RefreshAfterRoutine", "FeedActivityGraph", "Finalize", END]
    for left, right in zip(sequence, sequence[1:]):
        builder.add_edge(left, right)
    return builder.compile(checkpointer=checkpointer, name="AutonomousActivityGraphV2")
