"""Observe the values used by Graph validation without calculating its decisions."""
from contextvars import ContextVar
from functools import wraps

from app.contracts.decision_observation import alias, closed, emit, safe_observation, scope
from app.domains.relationships.contracts.graph_diagnostics import graph_rejection
from app.domains.relationships.contracts.graph_recall import GraphRecallDirection, GraphRecallOperation

_active = ContextVar("graph_validation_observation", default=None)
_DIRECTIONS = {v.value for v in GraphRecallDirection}
_OPERATIONS = {v.value for v in GraphRecallOperation}


def _identity(context, value):
    if value is None:
        return "not_constrained"
    if value == context.scope.subject_world_character_id:
        return "responding_character"
    return alias("identity", value)


class _ValidationTrace:
    def __init__(self, plan, context):
        self.context = context
        self.phase = scope.get()[1]
        self.validation_pass = scope.get()[2]
        self.rule = "query_binding.v2" if context.graph_queries else "request_pair_direction.v1"
        self.rows = []
        self.ordinal = 0
        bindings = dict(context.entity_bindings)
        values = {}
        for i, (ref, identity) in enumerate(list(bindings.items())[:4], 1):
            values[f"entity_{i}_ref"] = alias("ref", ref)
            values[f"entity_{i}_identity"] = _identity(context, identity)
        emit("graph_input", axis="graph", phase=self.phase,
             validation_pass=self.validation_pass, applied_rule=self.rule,
             upstream_from=_identity(context, context.relationship_from_world_character_id),
             upstream_to=_identity(context, context.relationship_to_world_character_id),
             plan_steps=len(plan.steps), **values)
        for ordinal, query in enumerate(context.graph_queries, 1):
            emit("graph_input", axis="graph", phase=self.phase, step=ordinal,
                 validation_pass=self.validation_pass, applied_rule=self.rule,
                 operation=query.kind, expected_direction=query.direction,
                 expected_counterpart=alias("ref", query.target_ref) if query.target_ref else "none",
                 expected_identity=_identity(context, bindings.get(query.target_ref)),
                 input_kind="previous_requirement" if query.result_of else "direct" if query.target_ref else "none",
                 input_step=f"requirement-{query.result_of}" if query.result_of else "none")

    def step(self, step):
        self.ordinal += 1
        parameters = dict(step.parameters)
        ref = parameters.get("counterpart_ref")
        bindings = dict(self.context.entity_bindings)
        row = {"step": self.ordinal, "step_ref": alias("step", step.id), "operation": closed(step.operation, _OPERATIONS),
               "validation_pass": self.validation_pass,
               "input_kind": "previous_step" if step.input_ref is not None else "direct" if ref is not None else "none",
               "input_step": alias("step", step.input_ref.partition(".")[0]) if step.input_ref else "none",
               "returned_counterpart": alias("ref", ref) if ref in bindings else "unresolved" if ref is not None else "absent",
               "returned_identity": _identity(self.context, bindings.get(ref)) if ref in bindings else "unresolved",
               "returned_direction": closed(parameters.get("direction"), _DIRECTIONS),
               "counterpart_check": "not_evaluated", "direction_check": "not_evaluated",
               "expected_direction": "not_evaluated", "expected_identity": "not_evaluated"}
        for key in ("limit", "max_hops", "depth"):
            if type(parameters.get(key)) is int:
                row[key] = parameters[key]
        row["ranking"] = closed(parameters.get("ranking"), {"positive", "tense", "recent"})
        self.rows.append(row)

    def counterpart(self, expected, actual):
        row = self.rows[-1]
        row["expected_identity"] = _identity(self.context, expected)
        row["expected_ref_count"] = sum(identity == expected for _, identity in self.context.entity_bindings) if expected else 0
        row["counterpart_check"] = "not_constrained" if expected is None else "matched" if actual == expected else "mismatch"

    def direction(self, expected, actual):
        row = self.rows[-1]
        row["expected_direction"] = expected.value if expected is not None else "not_constrained"
        row["direction_check"] = "not_constrained" if expected is None else "matched" if actual is expected else "mismatch"

    def finish(self, error):
        code = graph_rejection(error, phase=self.phase, stage="execution_contract").validation_code if error else "valid"
        for i, row in enumerate(self.rows):
            row_code = code if i == len(self.rows) - 1 else "valid"
            emit("graph_step", axis="graph", phase=self.phase, **row, validation_code=row_code,
                 applied_rule=self.rule, execution_state="not_entered",
                 basic={"operation": row["operation"], "step": row["step"], "validation_code": row_code,
                        "status": "rejected" if row_code != "valid" else "validated",
                        "expected_direction": row["expected_direction"], "returned_direction": row["returned_direction"],
                        "check": row["counterpart_check"] if row["counterpart_check"] == "mismatch" else row["direction_check"],
                        "validation_pass": self.validation_pass, "applied_rule": self.rule})
        emit("graph_validation", axis="graph", phase=self.phase, validation_code=code,
             validation_pass=self.validation_pass, status="rejected" if error else "validated",
             basic={"validation_code": code, "validation_pass": self.validation_pass,
                    "status": "rejected" if error else "validated"})


@safe_observation
def _new_trace(plan, context):
    return _ValidationTrace(plan, context)


@safe_observation
def validation_step(step):
    if _active.get() is not None:
        _active.get().step(step)


@safe_observation
def validation_counterpart(expected, actual):
    if _active.get() is not None:
        _active.get().counterpart(expected, actual)


@safe_observation
def validation_direction(expected, actual):
    if _active.get() is not None:
        _active.get().direction(expected, actual)


@safe_observation
def _finish(trace, error):
    trace.finish(error)


def observe_validation(function):
    @wraps(function)
    def wrapped(self, plan, context):
        trace = _new_trace(plan, context)
        if trace is None:
            return function(self, plan, context)
        token = _active.set(trace)
        try:
            result = function(self, plan, context)
        except BaseException as exc:
            _finish(trace, exc)
            raise
        else:
            _finish(trace, None)
            return result
        finally:
            _active.reset(token)
    return wrapped
