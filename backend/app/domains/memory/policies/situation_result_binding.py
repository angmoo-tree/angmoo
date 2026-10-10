"""Prove formatting equivalence while retaining independent effect checks."""
from dataclasses import replace
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.situation_result_binding import (
    SituationResultBinding, RESULT_BINDING_REVISION, SUPPORTED_RESULT_RULES,
)


def approve(admission, basis, *, run_id, now):
    receipt, result = admission.receipt, admission.result
    if (basis.logical_activity_id != receipt.logical_activity_id or basis.lane != receipt.lane
        or basis.target_key != receipt.target_key or receipt.lane not in {"routine", "inbox", "feed"}
        or basis.rules_revision not in SUPPORTED_RESULT_RULES
        or stable_digest(basis.raw_output) != result["planned_output_digest"]
        or stable_digest(basis.actual_output) != result["final_output_digest"]
        or basis.result_source not in admission.result_sources
        or basis.result_source.role != "committed_result"
        or basis.raw_output.get("action") not in {"post", "reply"}
        or any(basis.raw_output.get(key) != basis.actual_output.get(key) for key in ("action", "target"))):
        raise ValueError("situation_result_basis_invalid")
    if stable_digest(basis.normalized_output) != result["final_output_digest"]:
        raise ValueError("situation_result_substantive_mismatch")
    source = basis.result_source
    proof = SituationResultBinding(receipt.sequence, receipt.scope_setting_id,
        admission.manifest_digest, receipt.content_digest, result["planned_output_digest"],
        result["final_output_digest"], stable_digest(result["effects"]), basis.rules_revision,
        RESULT_BINDING_REVISION, stable_digest(basis.normalized_output), source.source_id,
        source.source_version, source.source_digest, now.isoformat(), run_id, "")
    return replace(proof, proof_digest=stable_digest(proof.material()))


def verify(admission, proof):
    proof.check_integrity()
    receipt, result = admission.receipt, admission.result
    sources = [source for source in admission.result_sources if source.role == "committed_result"]
    if (proof.receipt_sequence != receipt.sequence or proof.scope_setting_id != receipt.scope_setting_id
        or proof.manifest_digest != admission.manifest_digest or proof.content_digest != receipt.content_digest
        or proof.planned_output_digest != result["planned_output_digest"]
        or proof.final_output_digest != result["final_output_digest"]
        or proof.effect_identity_digest != stable_digest(result["effects"])
        or not any((source.source_id, source.source_version, source.source_digest) ==
            (proof.result_source_id, proof.result_source_version, proof.result_source_digest) for source in sources)):
        raise ValueError("situation_result_binding_invalid")
