"""Pure policy: delivery proves observation, never current access or integrity."""
from dataclasses import replace

from app.domains.memory.contracts.activity_situation import SituationValidationContext


def delivered_evidence(context, source, evidence, blocked_code):
    if (blocked_code == "memory_unobserved" and isinstance(context, SituationValidationContext)
            and source.source_type in {"POST", "REPLY"}
            and source.ranges
            and context.proof_for(source) is not None):
        return replace(evidence, observed_by_subject=True), context.proof_for(source).origin
    return evidence, None


def historical_relationship(context, source):
    basis = source.relationship_basis
    return bool(isinstance(context, SituationValidationContext) and context.proof_for(source)
        and context.version == 2 and basis is not None and source.role == "background"
        and basis.state_id == source.source_id and basis.actor_id == source.actor_id
        and basis.target_id == source.counterpart_id and str(basis.version) == source.source_version
        and basis.facts_digest == source.source_digest)
