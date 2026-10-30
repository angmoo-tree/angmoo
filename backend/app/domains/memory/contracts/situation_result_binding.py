"""Narrow port for authenticating an original SNS draft without rewriting it."""
from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable
from .activity_situation import DeliveredSourceEntry, stable_digest

RESULT_BINDING_REVISION = "situation-validation.v4"
# v5 changes description eligibility, not the existing formatting proof rule.
RESULT_BINDING_RUN_REVISIONS = frozenset({RESULT_BINDING_REVISION, "situation-validation.v5", "situation-validation.v6", "situation-validation.v7"})
SUPPORTED_RESULT_RULES = frozenset({"social-visible-text.v1"})


@dataclass(frozen=True)
class SituationResultBasis:
    logical_activity_id: str
    lane: str
    target_key: str
    raw_output: dict
    normalized_output: dict
    actual_output: dict
    rules_revision: str
    result_source: DeliveredSourceEntry


@dataclass(frozen=True)
class SituationResultBinding:
    receipt_sequence: int
    scope_setting_id: str
    manifest_digest: str
    content_digest: str
    planned_output_digest: str
    final_output_digest: str
    effect_identity_digest: str
    rules_revision: str
    validation_revision: str
    normalized_output_digest: str
    result_source_id: str
    result_source_version: str
    result_source_digest: str
    approved_at: str
    recheck_run_id: str
    proof_digest: str

    def material(self):
        value = asdict(self)
        value.pop("proof_digest")
        return value

    def check_integrity(self):
        if (self.validation_revision != RESULT_BINDING_REVISION
            or self.rules_revision not in SUPPORTED_RESULT_RULES
            or self.normalized_output_digest != self.final_output_digest
            or stable_digest(self.material()) != self.proof_digest):
            raise ValueError("situation_result_binding_invalid")


@runtime_checkable
class SituationResultBasisResolver(Protocol):
    def result_binding_basis(self, admission, *, now) -> SituationResultBasis: ...
