"""Same-session resolution storage; no commit, manifest rewrite or source search."""
from dataclasses import replace
from datetime import datetime
from sqlalchemy import select
from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry, PARENT_BINDING_REVISIONS
from app.domains.memory.contracts.situation_source_binding import SituationSourceBinding
from app.domains.memory.contracts.situation_validation import SituationParentBindingResolver
from app.domains.memory.models.situation_source_binding import MemorySituationSourceBinding
from app.domains.memory.policies.situation_source_binding import candidate_child, resolve_parent_binding, verify_parent_binding


def restore_bindings(session, context, *, validation=None):
    if context.revision not in PARENT_BINDING_REVISIONS:
        return context
    bindings = []
    rows = (validation.collections[("source_bindings", context.manifest_digest)]
        if validation is not None and ("source_bindings", context.manifest_digest) in validation.collections
        else session.scalars(select(MemorySituationSourceBinding).where(
            MemorySituationSourceBinding.manifest_id == context.manifest_digest)))
    for row in rows:
        binding = SituationSourceBinding(row.manifest_id, row.entry_ordinal, row.resolution_policy,
            row.original_entry_digest, row.basis_ordinal, row.basis_source_id, row.basis_source_digest,
            DeliveredSourceEntry.from_dict(row.resolved_source), utc_instant(row.resolved_at).isoformat(), row.resolution_digest)
        bindings.append(verify_parent_binding(context, binding))
    if len({row.entry_ordinal for row in bindings}) != len(bindings):
        raise ValueError("situation_parent_binding_duplicate")
    return replace(context, source_bindings=tuple(bindings))


def prepare_bindings(session, context, validator, *, captured_at, now):
    if context.revision not in PARENT_BINDING_REVISIONS:
        return context
    if not isinstance(validator, SituationParentBindingResolver):
        return context
    bindings = list(context.source_bindings)
    for original in context.manifest.sources:
        if any(binding.entry_ordinal == original.ordinal for binding in bindings):
            continue
        child = candidate_child(context, original)
        if child is None:
            continue
        basis = validator.parent_binding_basis(context, original, child=child, now=now)
        binding = verify_parent_binding(context, resolve_parent_binding(context, original, basis,
            captured_at=captured_at, now=now))
        session.add(MemorySituationSourceBinding(manifest_id=binding.manifest_id, entry_ordinal=binding.entry_ordinal,
            resolution_policy=binding.resolution_policy, original_entry_digest=binding.original_entry_digest,
            basis_ordinal=binding.basis_ordinal, basis_source_id=binding.basis_source_id,
            basis_source_digest=binding.basis_source_digest, resolved_source=binding.resolved_source.to_dict(),
            resolved_at=datetime.fromisoformat(binding.resolved_at), resolution_digest=binding.resolution_digest))
        session.flush()
        bindings.append(binding)
    return replace(context, source_bindings=tuple(bindings))
