"""Strict Canonical Planner output owned by the Memory domain."""

from __future__ import annotations

from dataclasses import dataclass
import re


CANONICAL_PLAN_VERSION = "canonical-plan.v1"
MAX_CANONICAL_PLAN_STEPS = 6
_STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PARAMETER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class CanonicalPlanContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalPlanStep:
    id: str
    operation: str
    input_ref: str | None = None
    parameters: tuple[tuple[str, str | int | bool], ...] = ()

    def __post_init__(self) -> None:
        if not _STEP_ID_RE.fullmatch(self.id):
            raise CanonicalPlanContractError("canonical_plan_step_id_invalid")
        if not _OPERATION_RE.fullmatch(self.operation):
            raise CanonicalPlanContractError("canonical_plan_raw_sql_forbidden")
        if len(self.parameters) > 8:
            raise CanonicalPlanContractError("canonical_plan_parameter_limit_invalid")
        if len({key for key, _value in self.parameters}) != len(self.parameters):
            raise CanonicalPlanContractError("canonical_plan_parameter_duplicate")
        for key, value in self.parameters:
            if not _PARAMETER_KEY_RE.fullmatch(key):
                raise CanonicalPlanContractError("canonical_plan_parameter_key_invalid")
            if isinstance(value, str) and (
                not value.strip() or len(value) > 160 or ";" in value
            ):
                raise CanonicalPlanContractError("canonical_plan_parameter_value_invalid")
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and abs(value) > 1_000_000
            ):
                raise CanonicalPlanContractError("canonical_plan_parameter_value_invalid")


@dataclass(frozen=True, slots=True)
class CanonicalRetrievalPlan:
    request_id: str
    envelope_version: str
    envelope_hash: str
    steps: tuple[CanonicalPlanStep, ...]
    version: str = CANONICAL_PLAN_VERSION

    def __post_init__(self) -> None:
        if self.version != CANONICAL_PLAN_VERSION:
            raise CanonicalPlanContractError("canonical_plan_version_mismatch")
        if not self.request_id or len(self.envelope_hash) != 64:
            raise CanonicalPlanContractError("canonical_plan_binding_invalid")
        if not 1 <= len(self.steps) <= MAX_CANONICAL_PLAN_STEPS:
            raise CanonicalPlanContractError("canonical_plan_step_limit_invalid")
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise CanonicalPlanContractError("canonical_plan_step_id_duplicate")
            if step.input_ref:
                if "." not in step.input_ref:
                    raise CanonicalPlanContractError("canonical_plan_input_ref_invalid")
                source = step.input_ref.split(".", 1)[0]
                if source not in seen and not source.startswith("graph"):
                    raise CanonicalPlanContractError("canonical_plan_reference_invalid")
            seen.add(step.id)


__all__ = [
    "CANONICAL_PLAN_VERSION",
    "MAX_CANONICAL_PLAN_STEPS",
    "CanonicalPlanContractError",
    "CanonicalPlanStep",
    "CanonicalRetrievalPlan",
]
