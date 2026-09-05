"""Read source evidence through its owners and apply Relationships eligibility rules."""
from app.domains.relationships.contracts.events import EvidenceInput, EventReferences
from app.domains.relationships.exceptions import SocialEventRuntimeError
from app.domains.relationships.policies.events import _validate_live_public_post


def _validate_evidence_source(
    references: EventReferences, *, world_id: str, evidence: EvidenceInput
) -> None:
    source: object | None
    if evidence.source_object_type == "post":
        source = references.get_post(evidence.source_object_id)
        _validate_live_public_post(source, world_id=world_id)
    elif evidence.source_object_type in {
        "post_like",
        "post_repost",
        "profile_follow",
        "notification",
        "agent_public_action_execution",
    }:
        try:
            source_id = int(evidence.source_object_id)
        except (TypeError, ValueError) as exc:
            raise SocialEventRuntimeError("evidence_source_invalid") from exc
        source = references.get_numeric_source(
            source_object_type=evidence.source_object_type, source_id=source_id
        )
    else:
        source = references.get_joint_activity(evidence.source_object_id)
    if source is None:
        raise SocialEventRuntimeError("evidence_source_invalid")
    if getattr(source, "world_id", None) != world_id:
        raise SocialEventRuntimeError("evidence_source_world_mismatch")
    post_ids = {
        post_id
        for post_id in (
            evidence.root_post_id,
            evidence.source_post_id,
            evidence.target_post_id,
        )
        if post_id is not None
    }
    for post_id in post_ids:
        _validate_live_public_post(references.get_post(post_id), world_id=world_id)
