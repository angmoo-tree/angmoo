"""Exact frozen child relationship and full transmitted parent hash; no I/O."""
from dataclasses import replace
import re
from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.situation_source_binding import PARENT_BINDING_POLICY, SituationSourceBinding

PARENT_PATH = re.compile(r"^((?:/context)?/today_activity/records/(?:0|[1-9][0-9]*))/parent_body$")


def candidate_child(context, original):
    match = PARENT_PATH.fullmatch(original.payload_path)
    if (context.version != 2 or context.lane not in {"inbox", "feed", "routine"}
        or not context.manifest.call_identity.startswith("sns:") or match is None
        or original.source_type not in {"POST", "REPLY"} or original.role != "background"
        or original.ranges or original.delivered_ranges or original.thread_id is not None
        or original.delivery_payload_digest != context.manifest.payload_digest):
        return None
    children = [source for source in context.manifest.sources
        if source.payload_path == match[1] + "/body" and source.source_type in {"POST", "REPLY"}
        and source.role == "background" and source.ranges and source.delivered_ranges
        and source.delivery_payload_digest == context.manifest.payload_digest and source.thread_id is None]
    return children[0] if len(children) == 1 else None


def resolve_parent_binding(context, original, basis, *, captured_at, now):
    child = candidate_child(context, original)
    parent = basis.parent
    if (child is None or child != basis.child or basis.child_current_digest != child.source_digest
        or basis.child_parent_id != parent.source_id or parent.source_id in {child.source_id, original.source_id}
        or parent.source_type not in {"POST", "REPLY"} or parent.world_id != original.world_id
        or not basis.parent_accessible or basis.parent_body_digest != original.delivered_digest
        or parent.delivered_digest != original.delivered_digest or not parent.ranges or not parent.delivered_ranges
        or utc_instant(basis.parent_created_at) > utc_instant(basis.child_created_at)
        or utc_instant(basis.child_created_at) > utc_instant(captured_at)):
        raise ValueError("situation_parent_binding_unproven")
    resolved = replace(parent, payload_path=original.payload_path, ordinal=original.ordinal,
        role=original.role, target_key=original.target_key, delivery_payload_digest=original.delivery_payload_digest)
    binding = SituationSourceBinding(context.manifest_digest, original.ordinal, PARENT_BINDING_POLICY,
        stable_digest(original.to_dict()), child.ordinal, child.source_id, child.source_digest,
        resolved, utc_instant(now).isoformat(), "")
    return replace(binding, resolution_digest=stable_digest(binding.material()))


def verify_parent_binding(context, binding):
    binding.check_integrity()
    original = next((entry for entry in context.manifest.sources if entry.ordinal == binding.entry_ordinal), None)
    child = candidate_child(context, original) if original is not None else None
    resolved = binding.resolved_source
    if (binding.manifest_id != context.manifest_digest or original is None or child is None
        or binding.original_entry_digest != stable_digest(original.to_dict())
        or (binding.basis_ordinal, binding.basis_source_id, binding.basis_source_digest)
            != (child.ordinal, child.source_id, child.source_digest)
        or (resolved.ordinal, resolved.payload_path, resolved.role, resolved.target_key, resolved.world_id,
            resolved.delivered_digest, resolved.delivery_payload_digest, resolved.thread_id)
            != (original.ordinal, original.payload_path, original.role, original.target_key, original.world_id,
                original.delivered_digest, original.delivery_payload_digest, None)
        or resolved.source_id in {child.source_id, original.source_id} or resolved.source_type not in {"POST", "REPLY"}
        or not resolved.ranges or not resolved.delivered_ranges or resolved.partial or resolved.transformation is not None):
        raise ValueError("situation_parent_binding_invalid")
    return binding
