"""Project only existing planner inputs and dispatch observations into diagnostics."""
from hashlib import sha256

from app.contracts.decision_observation import alias, closed, emit, safe_observation
from app.domains.relationships.contracts.graph_diagnostics import graph_rejection
from app.domains.relationships.policies.graph_plan_schema import graph_planner_repair_instruction


@safe_observation
def planner_attempt(request, tracker, *, error=None):
    phase = "repair" if request.repair_diagnostic is not None else "first"
    code = graph_rejection(error, phase=phase, stage="provider_output").validation_code if error else "valid"
    repair = request.repair_diagnostic
    relation = request.relationship
    endpoints = {}
    if relation is not None:
        for key, value in (("from_ref", relation.from_ref), ("to_ref", relation.to_ref)):
            endpoints[key] = value if value in {"responding_character", "requester_character"} else alias("ref", value)
    emit("graph_provider", axis="graph", phase=phase,
         status="rejected" if error else "validated", validation_code=code,
         physical_attempts=tracker.provider_call_order_in_run,
         repair_code=repair if repair else "none", repair_rule="graph_planner_repair_instruction.v1" if repair else "none",
         repair_digest="sha256-" + sha256(graph_planner_repair_instruction(repair).encode()).hexdigest() if repair else "none",
         expected_values_supplied="no", **endpoints,
         basic={"status": "rejected" if error else "validated", "validation_code": code,
                "physical_attempts": tracker.provider_call_order_in_run})
