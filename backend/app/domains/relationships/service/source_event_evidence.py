"""Canonical manual source binding, independent of search/projection eligibility."""
from collections.abc import Mapping, Sequence
from datetime import UTC
from hashlib import sha256
import json

from app.domains.relationships.contracts.source_event_evidence import (
    SourceEvent, SourceEvidence, SourcePost, SourceEventBasis,
)

MANUAL_EVENT_TYPES = frozenset({"like_added", "like_removed", "post_published", "reply_created"})


class SourceEventEvidenceError(ValueError):
    """Bounded reason only; never include source text or identifiers."""


def _require(condition, reason):
    if not condition:
        raise SourceEventEvidenceError("situation_manual_" + reason)


def _time(value):
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


def manual_source_basis(event: SourceEvent, evidences: Sequence[SourceEvidence],
                        posts: Mapping[str, SourcePost], *, world_id: str, subject_id: str,
                        active_ids: set[str] | frozenset[str], blocked_ids: set[str] | frozenset[str],
                        max_depth: int, allowed_visibilities: set[str] | frozenset[str],
                        execution=None) -> SourceEventBasis:
    _require(event.world_id == world_id and subject_id in {
        event.actor_world_character_id, event.target_world_character_id}, "scope_invalid")
    _require(event.event_type in MANUAL_EVENT_TYPES and event.retrieval_status == "audit_only",
             "type_unsupported")
    _require(event.result == "succeeded" and event.invalidated_at is None
             and event.invalidation_reason is None, "event_unavailable")
    _require(len(evidences) == 1, "evidence_ambiguous")
    proof = evidences[0]
    _require(proof.social_event_id == event.id and proof.source_object_type == "post"
             and proof.source_object_id == proof.source_post_id
             and isinstance(proof.content_sha256, str) and len(proof.content_sha256) == 64,
             "evidence_invalid")
    if proof.public_action_execution_id is not None:
        _require(execution is not None and execution.id == proof.public_action_execution_id
                 and execution.status == "succeeded" and execution.social_event_id == event.id
                 and execution.world_id == world_id
                 and execution.actor_world_character_id == event.actor_world_character_id,
                 "execution_invalid")
    else:
        _require(proof.agent_run_id is None, "execution_invalid")
    chain, seen = [], set()
    current = proof.source_post_id
    while current is not None:
        _require(len(chain) <= max_depth and current not in seen, "lineage_invalid")
        seen.add(current)
        post = posts.get(current)
        _require(post is not None, "source_missing")
        _require(post.world_id == world_id and post.visibility in allowed_visibilities
                 and post.deleted_at is None and post.report_hidden_at is None, "source_forbidden")
        chain.append(post)
        current = post.reply_to_post_id
    _require(bool(chain) and proof.root_post_id == chain[-1].id, "lineage_invalid")
    post = chain[0]
    parent = chain[1] if len(chain) > 1 else None
    reaction = event.event_type in {"like_added", "like_removed"}
    if reaction:
        _require(proof.evidence_kind == "like" and proof.target_post_id == post.id
                 and event.target_world_character_id == post.author_world_character_id,
                 "reaction_invalid")
    else:
        _require(event.actor_world_character_id == post.author_world_character_id, "author_invalid")
        if event.event_type == "post_published":
            _require(proof.evidence_kind == "post" and parent is None
                     and proof.target_post_id is None and event.target_world_character_id is None,
                     "post_invalid")
        else:
            _require(proof.evidence_kind == "reply_post" and parent is not None
                     and proof.target_post_id == parent.id
                     and event.target_world_character_id == parent.author_world_character_id,
                     "reply_invalid")
    _require(proof.source_author_id_at_event == post.author_world_character_id
             and proof.source_visibility_at_event in allowed_visibilities, "evidence_invalid")
    participants = {subject_id, event.actor_world_character_id, event.target_world_character_id,
                    *(p.author_world_character_id for p in chain)} - {None}
    _require(participants <= active_ids and not (participants - {subject_id}) & blocked_ids,
             "participant_forbidden")
    # Event-time content and the currently delivered post version are distinct.
    # An unlike does not invalidate an earlier like, and needs no PostLike row.
    material = {"policy": "delivered-social-event.v1", "event": [event.id, world_id,
        event.actor_world_character_id, event.target_world_character_id, event.event_type,
        event.result, event.retrieval_status, _time(event.occurred_at)],
        "evidence": [proof.id, proof.evidence_kind, proof.source_object_type, proof.source_object_id,
            proof.source_post_id, proof.target_post_id, proof.root_post_id, proof.content_sha256,
            proof.source_author_id_at_event, proof.source_visibility_at_event,
            proof.public_action_execution_id, proof.agent_run_id],
        "posts": [[p.id, p.author_world_character_id, p.reply_to_post_id, p.title, p.body,
                   _time(p.updated_at)] for p in chain]}
    digest = sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")).encode()).hexdigest()
    counterpart = event.target_world_character_id if event.actor_world_character_id == subject_id else event.actor_world_character_id
    return SourceEventBasis(event.id, event.event_type, event.actor_world_character_id, counterpart,
        post.id, proof.target_post_id, chain[-1].id, None if parent is None else parent.id, digest)
