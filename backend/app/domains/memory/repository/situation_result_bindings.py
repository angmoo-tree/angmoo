"""Receipt proof approval is restricted to the existing fenced recheck UoW."""
from dataclasses import asdict
from sqlalchemy import select
from app.domains.memory.contracts.situation_result_binding import (
    SituationResultBinding, SituationResultBasisResolver, RESULT_BINDING_REVISION,
)
from app.domains.memory.models.situation_result_binding import MemorySituationResultBinding
from app.domains.memory.policies.situation_result_binding import approve, verify


def stored_binding(session, admission, *, revision):
    if revision != RESULT_BINDING_REVISION:
        return None
    rows = list(session.scalars(select(MemorySituationResultBinding).where(
        MemorySituationResultBinding.receipt_sequence == admission.receipt.sequence,
        MemorySituationResultBinding.validation_revision == revision)))
    if len(rows) > 1:
        raise ValueError("situation_result_binding_invalid")
    if not rows:
        return None
    row = rows[0]
    proof = SituationResultBinding(**row.proof)
    if (row.scope_setting_id != proof.scope_setting_id or row.rules_revision != proof.rules_revision
        or row.recheck_run_id not in {None, proof.recheck_run_id}):
        raise ValueError("situation_result_binding_invalid")
    verify(admission, proof)
    return proof


def prepare_binding(session, admission, resolver, *, revision, run_id, now):
    if stored_binding(session, admission, revision=revision) is not None:
        return
    if revision != RESULT_BINDING_REVISION or not isinstance(resolver, SituationResultBasisResolver):
        raise ValueError("situation_result_basis_missing")
    proof = approve(admission, resolver.result_binding_basis(admission, now=now), run_id=run_id, now=now)
    session.add(MemorySituationResultBinding(receipt_sequence=proof.receipt_sequence,
        scope_setting_id=proof.scope_setting_id, recheck_run_id=run_id,
        validation_revision=revision, rules_revision=proof.rules_revision, proof=asdict(proof)))
    session.flush()
