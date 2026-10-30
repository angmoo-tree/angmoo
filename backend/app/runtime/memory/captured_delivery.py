"""Project an already admitted input fragment without reading its live original.

Callers bind identifiers to their code-owned request/checkpoint before using this
adapter. This is delivery evidence, not authorization to publish or use a memory.
"""
from hashlib import sha256

from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry


def captured_entry(scope, *, kind, identifier, delivery, ordinal, role="background",
                   target=None, thread=None, actor=None, counterpart=None,
                   version="initial-input.v1", source_digest=None, occurred_at=None,
                   basis=None, author_role=None):
    text = delivery.text
    digest = sha256(text.encode()).hexdigest()
    if basis is not None:
        if basis.actor_id != scope.subject_world_character_id:
            raise ValueError("situation_relationship_scope_invalid")
        version, source_digest = str(basis.version), basis.facts_digest
        actor, counterpart = basis.actor_id, basis.target_id
    return DeliveredSourceEntry(
        source_type=kind, source_id=str(identifier), source_version=str(version),
        source_digest=source_digest or digest, delivered_digest=digest,
        payload_path=delivery.path, role=role, ordinal=ordinal, world_id=scope.world_id,
        target_key=target, thread_id=thread, actor_id=actor, counterpart_id=counterpart,
        ranges=((0, len(text)),), delivered_ranges=((0, len(text)),), partial=True,
        transformation="initial-input.v1", relationship_basis=basis,
        delivery_payload_digest=delivery.payload_digest, delivered_text=text,
        source_created_at=occurred_at.isoformat() if hasattr(occurred_at, "isoformat") else occurred_at,
        author_role=author_role)


def post_reference(post):
    """Small provenance captured in the same read as the candidate's text."""
    from app.domains.social.utils.post_revision import post_revision
    return {"kind": "REPLY" if post.reply_to_post_id else "POST", "id": post.id,
        "world_id": post.world_id, "actor": post.author_world_character_id,
        "revision": post_revision(post), "created_at": post.created_at.isoformat(),
        "body": post.body}


def bind_candidate_sources(candidates, references):
    """Bind each body to its exact span in a potentially multi-post conversation."""
    for candidate in candidates:
        cursor = 0
        for identifier in candidate["source_ids"]:
            row = references[identifier]
            body = row["body"]
            start = candidate["text"].find(body, cursor)
            if start < 0:
                raise ValueError("activity_initial_source_binding_invalid")
            row.setdefault("views", {})[candidate["target_id"]] = {
                "start": start, "end": start + len(body)}
            cursor = start + len(body)


def candidate_fragment(reference, candidate, delivered):
    """Input budgeting may keep a prefix; never attribute adjacent posts to this one."""
    view = reference.get("views", {}).get(candidate["target_id"])
    if view is None:
        raise ValueError("situation_initial_post_binding_missing")
    original = candidate["text"]
    common = 0
    for left, right in zip(original, delivered):
        if left != right:
            break
        common += 1
    return delivered[view["start"]:min(view["end"], common)]
