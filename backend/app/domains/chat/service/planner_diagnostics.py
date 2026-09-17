"""Content-free canonical planner rejection observations; never expose payloads."""
from app.contracts.retrieval_observation import observe
from app.domains.memory.contracts.planner_provider import canonical_planner_diagnostic
from app.domains.chat.contracts.call_tracker import RouteAwareCallTracker
from app.domains.memory.contracts.planner_provider import CanonicalPlannerOutputError
from app.domains.relationships.contracts.graph_diagnostics import graph_rejection

_FINISH = frozenset({"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER", "MALFORMED_FUNCTION_CALL"})


def observe_graph_rejection(exc: BaseException, *, phase: str, stage: str, tracker: RouteAwareCallTracker):
    rejection = graph_rejection(exc, phase=phase, stage=stage)
    snapshot = tracker.snapshot()
    observe("planner_validation", axis="graph", status="rejected", reason="plan_contract_invalid",
            **rejection.payload(), logical_calls=snapshot["logical_counts"]["graph_planner"],
            physical_attempts=snapshot["physical_counts"]["graph_planner"])
    return rejection


def observe_canonical_rejection(exc: Exception, *, phase: str, tracker: RouteAwareCallTracker) -> None:
    try:
        values = {"axis": "canonical", "phase": phase, "status": "rejected",
                  "reason": "plan_contract_invalid", "validation_code": canonical_planner_diagnostic(exc, fallback="unknown"),
                  "failure_stage": "provider_output" if isinstance(exc, CanonicalPlannerOutputError) else "execution_contract"}
        current = exc
        for _ in range(6):
            if current is None:
                break
            rows = getattr(current, "json_error_diagnostics", None)
            if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
                row = rows[-1]
                if row.get("finish_reason") in _FINISH:
                    values["finish_reason"] = row["finish_reason"]
                if row.get("shape_hint") == "schema_validation":
                    values["failure_stage"] = "schema_validation"
                elif getattr(current, "parse_error_type", None) == "JSONDecodeError":
                    values["failure_stage"] = "json_decode"
                if isinstance(row.get("response_length"), int):
                    values["response_chars"] = row["response_length"]
            current = current.__cause__
        snapshot = tracker.snapshot()
        values["logical_calls"] = snapshot["logical_counts"]["canonical_planner"]
        values["physical_attempts"] = snapshot["physical_counts"]["canonical_planner"]
        observe("planner_validation", **values)
    except Exception:
        observe("planner_validation", axis="canonical", phase=phase, status="rejected", reason="plan_contract_invalid")
