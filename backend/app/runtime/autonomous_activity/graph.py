"""Actual nested LangGraph execution with small, checkpointable stage results."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from time import monotonic
from uuid import uuid4

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
    observe: Callable[..., None] | None = None


def build_lane(lane: str, ports: LanePorts, *, combined=False):
    builder = StateGraph(LaneState)

    def trace(event_type, name, **details):
        if ports.observe is not None:
            try:
                ports.observe(event_type, name, **details)
            except Exception:
                pass  # Diagnostics cannot change graph behavior.

    def guarded(name: str, callback: Node):
        async def invoke(state):
            started = monotonic()
            stage_attempt_id = uuid4().hex
            trace("node_started", name, state=state, stage_attempt_id=stage_attempt_id)
            try:
                await ports.guard({**state, "stage": name})
            except BaseException as exc:
                trace("node_failed", name, state=state, phase="guard", exc=exc,
                      stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
                raise
            if name == "Execute" and state.get("failure"):
                result = {"executions": []}
                trace("node_completed", name, state=state, result=result,
                      stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
                return result
            try:
                result = await callback(state)
            except BaseException as exc:
                from app.runtime.autonomous_activity.output_recovery import ActivityRetryGuardError
                if isinstance(exc, ActivityRetryGuardError):
                    trace("node_failed", name, state=state, phase="retry_guard", exc=exc.original,
                          stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
                    raise exc.original from exc
                trace("node_failed", name, state=state, phase="callback", exc=exc,
                      stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
                from app.integrations.direct_llm import DirectLlmError, DirectLlmDeferred
                if name not in {"Writer", "ValidateDraft"} or isinstance(exc, DirectLlmDeferred) or not isinstance(exc, (ValueError, DirectLlmError)):
                    raise
                # A normal Planner already interpreted experience. Keep its
                # settlement independent of failed public expression.
                result = {"failure": {"stage": name, "reason": type(exc).__name__}, "drafts": []}
            trace("node_completed", name, state=state, result=result,
                  stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
            return result
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
    planner = "DecisionDraft" if combined else "ActionPlanner"
    writer = "ValidateDraft" if combined else "Writer"
    for name, callback in (
        ("RecallSelected", ports.recall), ("BuildDecisionContext", ports.build_context),
        (planner, ports.plan), ("ValidateDecision", ports.validate),
        (writer, ports.write), ("Execute", ports.execute),
        ("Settle", ports.settle), ("PathResult", ports.finalize),
    ):
        builder.add_node(name, guarded(name, callback))
    builder.add_edge(START, "LoadCandidates")
    builder.add_conditional_edges("LoadCandidates", lambda s: (
        "PathResult" if not s.get("candidates") or s.get("preparation_error") else
        ("ResolveQuery" if s.get("selections") else "PathResult") if combined and lane != "routine" else
        "ResolveQuery" if lane == "routine" else "TargetSelector"
    ), ["PathResult", "ResolveQuery", "TargetSelector"])
    builder.add_conditional_edges("TargetSelector", lambda s: "ResolveQuery" if s.get("selections") else "PathResult", ["ResolveQuery", "PathResult"])
    builder.add_edge("ResolveQuery", "RecallSelected")
    builder.add_edge("RecallSelected", "BuildDecisionContext")
    if combined:
        from app.runtime.autonomous_activity.generation_contracts import generation_mode
        builder.add_node("ChooseGenerationMode", guarded("ChooseGenerationMode", generation_mode))
        builder.add_edge("BuildDecisionContext", "ChooseGenerationMode")
        builder.add_edge("ChooseGenerationMode", planner)
    else:
        builder.add_edge("BuildDecisionContext", planner)
    builder.add_edge(planner, "ValidateDecision")
    builder.add_conditional_edges("ValidateDecision", lambda s: writer if s.get("assignments") else "Execute", [writer, "Execute"])
    builder.add_edge(writer, "Execute")
    builder.add_edge("Execute", "Settle")
    builder.add_edge("Settle", "PathResult")
    builder.add_edge("PathResult", END)
    # Inherit the parent's durable saver and per-invocation namespace.
    return builder.compile(name=f"{lane.capitalize()}ActivityGraph")


def build_autonomous_graph(*, lanes: dict[str, LanePorts], load_context: Node,
                           refresh: Node, finalize: Node, checkpointer: Any,
                           observe: Callable[..., None] | None = None,
                           prepare: Node | None = None, choose_selection_mode: Node | None = None,
                           combined_select: Node | None = None):
    combined = combined_select is not None
    builder = StateGraph(ParentState)

    def parent(name, callback):
        async def invoke(state):
            started = monotonic()
            stage_attempt_id = uuid4().hex
            if observe is not None:
                try:
                    observe("node_started", name, state=state, stage_attempt_id=stage_attempt_id)
                except Exception:
                    pass
            try:
                result = await callback(state)
            except BaseException as exc:
                if observe is not None:
                    try:
                        observe("node_failed", name, state=state, phase="callback", exc=exc,
                                stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
                    except Exception:
                        pass
                raise
            if observe is not None:
                try:
                    observe("node_completed", name, state=state, result=result,
                            stage_attempt_id=stage_attempt_id, duration_ms=int((monotonic() - started) * 1000))
                except Exception:
                    pass
            return result
        return invoke

    builder.add_node("LoadContext", parent("LoadContext", load_context))
    for lane in ("inbox", "routine", "feed"):
        graph = build_lane(lane, lanes[lane], combined=combined)

        async def invoke(state, config, child=graph, path=lane, port=lanes[lane]):
            # Private lane channels never bleed into another lane's state.
            started = monotonic()
            stage_attempt_id = uuid4().hex
            if observe is not None:
                try:
                    observe("node_started", f"{path.capitalize()}ActivityGraph", state=state,
                            stage_attempt_id=stage_attempt_id)
                except Exception:
                    pass
            try:
                prepared = state.get("prepared_lanes", {}).get(path, {}) if combined else {}
                extra_context = prepared.get("shared_context", {}).get("action_preferences")
                shared = dict(state["shared_context"])
                if extra_context is not None:
                    shared["action_preferences"] = extra_context
                result = await child.ainvoke({**prepared, "identity": state["identity"], "shared_context": shared}, config)
            except BaseException as exc:
                if observe is not None:
                    try:
                        observe("node_failed", f"{path.capitalize()}ActivityGraph", state=state,
                                phase="child", exc=exc, stage_attempt_id=stage_attempt_id,
                                duration_ms=int((monotonic() - started) * 1000))
                    except Exception:
                        pass
                if not isinstance(exc, Exception) or port.on_error is None:
                    raise
                failure = await port.on_error(exc)
                if combined and "selections" in prepared:
                    failure = {"selected_ids": [s["target_id"] for s in prepared["selections"]], **failure}
                recovered = {f"{path}_result": failure}
                if observe is not None:
                    try:
                        observe("node_completed", f"{path.capitalize()}ActivityGraph", state=state,
                                result=recovered, stage_attempt_id=stage_attempt_id,
                                duration_ms=int((monotonic() - started) * 1000))
                    except Exception:
                        pass
                return recovered
            completed = {f"{path}_result": result.get("result", {})}
            if observe is not None:
                try:
                    observe("node_completed", f"{path.capitalize()}ActivityGraph", state=state,
                            result=completed, stage_attempt_id=stage_attempt_id,
                            duration_ms=int((monotonic() - started) * 1000))
                except Exception:
                    pass
            return completed

        builder.add_node(f"{lane.capitalize()}ActivityGraph", invoke)
    builder.add_node("RefreshAfterInbox", parent("RefreshAfterInbox", refresh))
    builder.add_node("RefreshAfterRoutine", parent("RefreshAfterRoutine", refresh))
    builder.add_node("Finalize", parent("Finalize", finalize))
    if combined:
        if prepare is None or choose_selection_mode is None:
            raise ValueError("combined_selection_ports_missing")
        builder.add_node("PrepareCandidates", parent("PrepareCandidates", prepare))
        builder.add_node("ChooseSelectionMode", parent("ChooseSelectionMode", choose_selection_mode))
        builder.add_node("CombinedTargetSelector", parent("CombinedTargetSelector", combined_select))
        builder.add_node("RefreshAfterFeed", parent("RefreshAfterFeed", refresh))
        sequence = [START, "LoadContext", "PrepareCandidates", "ChooseSelectionMode", "CombinedTargetSelector",
                    "InboxActivityGraph", "RefreshAfterInbox", "FeedActivityGraph", "RefreshAfterFeed",
                    "RoutineActivityGraph", "Finalize", END]
    else:
        sequence = [START, "LoadContext", "InboxActivityGraph", "RefreshAfterInbox", "RoutineActivityGraph",
                    "RefreshAfterRoutine", "FeedActivityGraph", "Finalize", END]
    for left, right in zip(sequence, sequence[1:]):
        builder.add_edge(left, right)
    return builder.compile(checkpointer=checkpointer, name="AutonomousActivityGraphV2")
