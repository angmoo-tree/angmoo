"""Chat's pure manual retry policy, independent of the repair budget."""

from app.domains.chat.contracts.graph_failure import GraphFailureDiagnostic


# These exact codes originate in graph_plan_schema's missing-field checks.
# Missing/extra object keys and invalid refs may include forbidden material;
# generic errors and binding/direction violations deliberately are not here.
_MISSING_FIELDS = frozenset({
    "graph_plan_direction_required",
    "graph_plan_ranking_required",
    "graph_plan_hops_required",
    "graph_plan_depth_required",
})


def graph_failure_allows_user_retry(diagnostic: GraphFailureDiagnostic | None) -> bool:
    if not isinstance(diagnostic, GraphFailureDiagnostic):
        return False
    if diagnostic.terminal_code != "graph_planner_request_wide_repair_exhausted":
        return False
    if diagnostic.repair_node is None:
        return False
    for rejection in diagnostic.rejections:
        if rejection.phase not in {"first", "repair"}:
            return False
        if rejection.finish_reason not in {None, "STOP", "MAX_TOKENS"}:
            return False
        if rejection.validation_code == "JSONDecodeError":
            if rejection.failure_stage != "json_decode":
                return False
        elif rejection.validation_code in _MISSING_FIELDS:
            if rejection.failure_stage not in {"provider_output", "schema_validation"}:
                return False
        else:
            return False
    return True
