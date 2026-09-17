"""Provider-neutral Canonical Retrieval Planner port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.memory.contracts.retrieval_plan import (
    CanonicalPlanContractError,
    CanonicalRetrievalPlan,
)

MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS = 4_000


class CanonicalPlannerOutputError(CanonicalPlanContractError):
    """Typed provider output failure eligible for request-wide repair."""

    def __init__(
        self,
        diagnostic: str,
        *,
        physical_attempt_count: int = 1,
    ) -> None:
        if physical_attempt_count < 1 or physical_attempt_count > 2:
            raise CanonicalPlanContractError(
                "canonical_planner_physical_attempt_invalid"
            )
        super().__init__("canonical_planner_output_invalid")
        self.diagnostic = diagnostic[:160]
        self.physical_attempt_count = physical_attempt_count


@dataclass(frozen=True, slots=True)
class CanonicalPlannerEntity:
    ref: str
    mention: str
    role: str

    def __post_init__(self) -> None:
        if not self.ref or not self.mention.strip() or not self.role.strip():
            raise CanonicalPlanContractError("canonical_planner_entity_invalid")
        if len(self.ref) > 64 or len(self.mention) > 160 or len(self.role) > 64:
            raise CanonicalPlanContractError("canonical_planner_entity_invalid")


@dataclass(frozen=True, slots=True)
class CanonicalPlannerRelationship:
    from_ref: str
    to_ref: str
    dimension: str | None = None
    requested_polarity: str | None = None

    def __post_init__(self) -> None:
        if not self.from_ref or not self.to_ref or self.from_ref == self.to_ref:
            raise CanonicalPlanContractError(
                "canonical_planner_relationship_invalid"
            )


@dataclass(frozen=True, slots=True)
class CanonicalPlannerRequest:
    """Bounded semantic input; no canonical owner/World/Character ID exists."""

    request_id: str
    envelope_version: str
    envelope_hash: str
    user_message: str
    intent: str
    entities: tuple[CanonicalPlannerEntity, ...] = ()
    relationship: CanonicalPlannerRelationship | None = None
    resolved_time_available: bool = False
    aggregation_kind: str | None = None
    aggregation_target: str | None = None
    repair_diagnostic: str | None = None
    memory_subject_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise CanonicalPlanContractError("canonical_planner_request_id_invalid")
        if not self.envelope_version or len(self.envelope_version) > 64:
            raise CanonicalPlanContractError(
                "canonical_planner_envelope_version_invalid"
            )
        if len(self.envelope_hash) != 64:
            raise CanonicalPlanContractError("canonical_planner_envelope_hash_invalid")
        if not self.user_message.strip() or (
            len(self.user_message) > MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS
        ):
            raise CanonicalPlanContractError("canonical_planner_message_invalid")
        if not self.intent.strip() or len(self.intent) > 96:
            raise CanonicalPlanContractError("canonical_planner_intent_invalid")
        if len(self.entities) > 4 or len({item.ref for item in self.entities}) != len(
            self.entities
        ):
            raise CanonicalPlanContractError("canonical_planner_entities_invalid")
        entity_refs = {item.ref for item in self.entities}
        if (
            not isinstance(self.memory_subject_refs, tuple)
            or len(self.memory_subject_refs) > len(self.entities)
            or any(
                not isinstance(ref, str) or ref not in entity_refs
                for ref in self.memory_subject_refs
            )
            or len(set(self.memory_subject_refs)) != len(self.memory_subject_refs)
        ):
            raise CanonicalPlanContractError(
                "canonical_planner_memory_subject_refs_invalid"
            )
        if (self.aggregation_kind is None) != (self.aggregation_target is None):
            raise CanonicalPlanContractError(
                "canonical_planner_aggregation_incomplete"
            )
        if self.repair_diagnostic is not None and (
            not self.repair_diagnostic.strip()
            or len(self.repair_diagnostic) > 160
        ):
            raise CanonicalPlanContractError(
                "canonical_planner_repair_diagnostic_invalid"
            )


@dataclass(frozen=True, slots=True)
class CanonicalPlannerProviderResult:
    plan: CanonicalRetrievalPlan
    provider: str
    model: str
    physical_attempt_count: int
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    thought_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None
    thinking_level: str | None = None
    max_output_tokens: int | None = None
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if self.physical_attempt_count < 1 or self.physical_attempt_count > 2:
            raise CanonicalPlanContractError(
                "canonical_planner_physical_attempt_invalid"
            )


class CanonicalPlannerProviderPort(Protocol):
    async def plan(
        self,
        request: CanonicalPlannerRequest,
    ) -> CanonicalPlannerProviderResult: ...


# Exact code vocabulary, not a regex accepting arbitrary provider text.
_SAFE_CODES = frozenset({
    'CanonicalPlanContractError',
    'JSONDecodeError',
    'TypeError',
    'ValidationError',
    'ValueError',
    'canonical_execution_allowlist_duplicate',
    'canonical_execution_allowlist_operation_unknown',
    'canonical_execution_binding_invalid',
    'canonical_execution_entity_binding_invalid',
    'canonical_execution_row_limit_invalid',
    'canonical_plan_binding_invalid',
    'canonical_plan_binding_mismatch',
    'canonical_plan_counterpart_ref_invalid',
    'canonical_plan_counterpart_ref_keys_invalid',
    'canonical_plan_cross_axis_ref_forbidden',
    'canonical_plan_current_thread_invalid',
    'canonical_plan_entity_ref_invalid',
    'canonical_plan_entity_ref_keys_invalid',
    'canonical_plan_entity_ref_required',
    'canonical_plan_entity_ref_unresolved',
    'canonical_plan_memory_subject_as_counterpart',
    'canonical_plan_envelope_hash_invalid',
    'canonical_plan_envelope_hash_keys_invalid',
    'canonical_plan_envelope_version_invalid',
    'canonical_plan_envelope_version_keys_invalid',
    'canonical_plan_forbidden_field',
    'canonical_plan_id_invalid',
    'canonical_plan_id_keys_invalid',
    'canonical_plan_input_ref_forbidden',
    'canonical_plan_input_ref_invalid',
    'canonical_plan_input_ref_keys_invalid',
    'canonical_plan_input_ref_required',
    'canonical_plan_key_invalid',
    'canonical_plan_limit_invalid',
    'canonical_plan_limit_keys_invalid',
    'canonical_plan_occurred_from_invalid',
    'canonical_plan_occurred_from_keys_invalid',
    'canonical_plan_occurred_to_invalid',
    'canonical_plan_occurred_to_keys_invalid',
    'canonical_plan_operation_forbidden',
    'canonical_plan_operation_invalid',
    'canonical_plan_operation_keys_invalid',
    'canonical_plan_operation_unknown',
    'canonical_plan_parameter_duplicate',
    'canonical_plan_parameter_forbidden',
    'canonical_plan_parameter_key_invalid',
    'canonical_plan_parameter_limit_invalid',
    'canonical_plan_parameter_value_invalid',
    'canonical_plan_parameters_invalid',
    'canonical_plan_parameters_keys_invalid',
    'canonical_plan_payload_invalid',
    'canonical_plan_payload_keys_invalid',
    'canonical_plan_payload_not_object',
    'canonical_plan_raw_query_forbidden',
    'canonical_plan_raw_sql_forbidden',
    'canonical_plan_reference_invalid',
    'canonical_plan_request_id_invalid',
    'canonical_plan_request_id_keys_invalid',
    'canonical_plan_search_text_invalid',
    'canonical_plan_search_text_keys_invalid',
    'canonical_plan_search_text_required',
    'canonical_plan_step_id_duplicate',
    'canonical_plan_step_id_invalid',
    'canonical_plan_step_invalid',
    'canonical_plan_step_keys_invalid',
    'canonical_plan_step_limit_invalid',
    'canonical_plan_steps_invalid',
    'canonical_plan_version_invalid',
    'canonical_plan_version_keys_invalid',
    'canonical_plan_version_mismatch',
    'malformed_json',
    'schema_validation_failed',
})

def canonical_planner_diagnostic(
    exc: BaseException, *, fallback: str = "schema_validation_failed"
) -> str:
    """Prefer a concrete contract code without forwarding exception bodies."""
    result = fallback
    current: BaseException | None = exc
    for _ in range(6):
        if current is None:
            break
        for code in (
            getattr(current, "parse_error_type", None),
            getattr(current, "diagnostic", None),
            str(current),
        ):
            if isinstance(code, str) and code in _SAFE_CODES:
                if code.startswith("canonical_") or not result.startswith("canonical_"):
                    result = code
        current = current.__cause__
    return result



__all__ = [
    "canonical_planner_diagnostic",
    "MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS",
    "CanonicalPlannerEntity",
    "CanonicalPlannerOutputError",
    "CanonicalPlannerProviderPort",
    "CanonicalPlannerProviderResult",
    "CanonicalPlannerRelationship",
    "CanonicalPlannerRequest",
]
