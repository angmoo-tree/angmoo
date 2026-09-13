"""Bounded Graph error vocabulary; never retain model payloads or exception text."""
from dataclasses import dataclass


GRAPH_VALIDATION_CODES = frozenset({
    "graph_draft_keys_invalid", "graph_draft_requirement_invalid", "graph_draft_operation_mismatch",
    "graph_draft_dependency_ambiguous", "graph_query_coverage_missing", "graph_query_step_binding_mismatch",
    "graph_query_direction_invalid", "graph_query_collection_target_forbidden", "graph_query_target_required",
    "graph_query_target_invalid", "graph_query_dependency_invalid", "graph_query_count_invalid",
    "graph_query_target_unbound", "graph_query_self_target_invalid", "graph_plan_step_limit_exceeded",
    "unknown", "JSONDecodeError", "GraphPlanContractError", "ValidationError",
    "TypeError", "ValueError", "schema_validation_failed",
    "graph_plan_payload_not_object", "graph_plan_payload_keys_invalid",
    "graph_plan_steps_invalid", "graph_plan_step_limit_invalid",
    "graph_plan_step_invalid", "graph_plan_step_keys_invalid",
    "graph_plan_step_id_invalid", "graph_plan_step_id_duplicate",
    "graph_plan_operation_invalid", "graph_plan_operation_unknown",
    "graph_plan_operation_forbidden", "graph_plan_parameters_invalid",
    "graph_plan_parameter_forbidden", "graph_plan_parameter_duplicate",
    "graph_plan_parameter_key_invalid", "graph_plan_parameter_value_invalid",
    "graph_plan_parameter_limit_invalid", "graph_plan_entity_ref_invalid",
    "graph_plan_entity_ref_unresolved", "graph_plan_counterpart_ref_invalid",
    "graph_plan_counterpart_binding_invalid", "graph_plan_counterpart_forbidden",
    "graph_plan_counterpart_direction_mismatch", "graph_plan_direction_invalid",
    "graph_plan_direction_required", "graph_plan_direction_mismatch",
    "graph_plan_ranking_invalid", "graph_plan_ranking_required",
    "graph_plan_hops_invalid", "graph_plan_hops_required",
    "graph_plan_depth_invalid", "graph_plan_depth_required", "graph_plan_limit_invalid",
    "graph_plan_reference_invalid", "graph_plan_input_ref_invalid",
    "graph_plan_key_invalid", "graph_plan_forbidden_field",
    "graph_plan_raw_query_forbidden", "graph_plan_raw_cypher_forbidden",
    "graph_plan_cross_axis_ref_forbidden", "graph_plan_binding_invalid",
    "graph_plan_binding_mismatch", "graph_plan_version_invalid",
    "graph_plan_version_mismatch", "graph_plan_request_id_invalid",
    "graph_plan_envelope_hash_invalid", "graph_plan_envelope_version_invalid",
    "graph_execution_allowlist_operation_unknown",
    "graph_planner_output_invalid", "graph_planner_physical_attempt_invalid",
    "graph_planner_entity_invalid", "graph_planner_relationship_invalid",
    "graph_planner_request_id_invalid", "graph_planner_envelope_version_invalid",
    "graph_planner_envelope_hash_invalid", "graph_planner_message_invalid",
    "graph_planner_intent_invalid", "graph_planner_entities_invalid",
    "graph_planner_aggregation_incomplete", "graph_planner_hop_hint_invalid",
    "graph_planner_repair_diagnostic_invalid",
})
_FINISH = frozenset({"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER", "MALFORMED_FUNCTION_CALL"})
_STAGES = frozenset({"request", "provider_output", "json_decode", "schema_validation", "execution_contract", "execution", "transport", "cancelled"})


@dataclass(frozen=True, slots=True)
class GraphAttemptObservation:
    """Known dispatches, including a dispatch interrupted before its response."""
    physical_attempts: int
    complete: bool = True

    def __post_init__(self):
        if type(self.physical_attempts) is not int or not 0 <= self.physical_attempts <= 2 or type(self.complete) is not bool:
            raise ValueError("graph_attempt_observation_invalid")


@dataclass(frozen=True, slots=True)
class GraphRejection:
    phase: str
    validation_code: str
    failure_stage: str
    finish_reason: str | None = None
    response_chars: int | None = None

    def __post_init__(self):
        if self.phase not in {"first", "repair", "request", "execution"} or self.validation_code not in GRAPH_VALIDATION_CODES or self.failure_stage not in _STAGES:
            raise ValueError("graph_rejection_invalid")
        if self.finish_reason is not None and self.finish_reason not in _FINISH:
            raise ValueError("graph_rejection_finish_invalid")
        if self.response_chars is not None and (type(self.response_chars) is not int or not 0 <= self.response_chars <= 1_000_000):
            raise ValueError("graph_rejection_size_invalid")

    def payload(self):
        values = {"phase": self.phase, "validation_code": self.validation_code, "failure_stage": self.failure_stage}
        if self.finish_reason is not None:
            values["finish_reason"] = self.finish_reason
        if self.response_chars is not None:
            values["response_chars"] = self.response_chars
        return values


def graph_rejection(exc: BaseException, *, phase: str, stage: str) -> GraphRejection:
    code = "unknown"
    finish = None
    chars = None
    current = exc
    for _ in range(6):
        if current is None:
            break
        for candidate in (getattr(current, "parse_error_type", None), getattr(current, "diagnostic", None), str(current)):
            if isinstance(candidate, str) and candidate in GRAPH_VALIDATION_CODES and candidate != "graph_planner_output_invalid":
                # A wrapping output error must not hide a concrete parser error.
                concrete = candidate.startswith("graph_") and candidate != "graph_planner_output_invalid"
                if concrete or code in {"unknown", "GraphPlanContractError", "graph_planner_output_invalid", "TypeError", "ValueError", "ValidationError", "schema_validation_failed"}:
                    code = candidate
        rows = getattr(current, "json_error_diagnostics", None)
        if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
            row = rows[-1]
            if isinstance(row.get("finish_reason"), str) and row["finish_reason"] in _FINISH:
                finish = row["finish_reason"]
            if row.get("shape_hint") == "schema_validation":
                stage = "schema_validation"
            if getattr(current, "parse_error_type", None) == "JSONDecodeError":
                stage = "json_decode"
            size = row.get("response_length")
            if type(size) is int and 0 <= size <= 1_000_000:
                chars = size
        current = current.__cause__
    if code == "JSONDecodeError" and stage == "provider_output":
        stage = "json_decode"
    return GraphRejection(phase, code, stage, finish, chars)
