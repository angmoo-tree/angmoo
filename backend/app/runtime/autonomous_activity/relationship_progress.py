"""Canonical same-decision effect receipts, bounded by admitted SNS targets."""
from dataclasses import asdict
from hashlib import sha256
import json
from sqlalchemy import select
from app.contracts.relationship_currentness import EFFECT_PROGRESS_KEY, EFFECT_PROGRESS_REVISION
from app.domains.relationships.contracts.social_context import (
    RelationshipValidationReceipt, RelationshipValidationReference, CanonicalSocialContextReference,
    SocialContextValidationError,
)
from app.domains.relationships.policies.effect_progress import RelationshipEffect

PRIVATE_KEY = "_relationship_effect_progress"


def enabled(state):
    policy = state.get("identity", {}).get(EFFECT_PROGRESS_KEY)
    if policy not in {None, EFFECT_PROGRESS_REVISION}:
        raise SocialContextValidationError("effect_policy_invalid")
    return policy == EFFECT_PROGRESS_REVISION


def decision_digest(state):
    return sha256(json.dumps({"decision": state.get("decision"), "drafts": state.get("drafts", [])},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _index(state, target):
    return next((i for i, row in enumerate(state.get("decision", {}).get("decisions", []))
        if row["target_id"] == target), len(state.get("decision", {}).get("decisions", [])))


def effects(lane, state, target):
    if not enabled(state) or not state.get("decision"):
        return ()
    from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence
    expected_digest = decision_digest(state)
    output, seen = [], set()
    decisions = state["decision"]["decisions"]
    if len(decisions) > 3:
        raise SocialContextValidationError("effect_receipt_invalid")
    for index, raw in enumerate(decisions[:_index(state, target)]):
        if raw["action"] == "no_action":
            continue
        execution = lane.completed_action(state, raw["target_id"])
        if execution is None:
            continue
        proof = (execution.result or {}).get(PRIVATE_KEY)
        if proof is None:
            continue  # Old successful execution cannot prove a changed fact.
        try:
            keys = {"revision", "owner", "world", "actor", "activity", "lane", "decision", "index", "target", "execution", "signature", "event", "changes"}
            if (not isinstance(proof, dict) or set(proof) != keys or proof["revision"] != EFFECT_PROGRESS_REVISION
                or (proof["owner"], proof["world"], proof["actor"], proof["activity"], proof["lane"]) !=
                    (lane.ctx.user_id, lane.actor.world_id, lane.actor.id, lane.ctx.run_id, lane.lane)
                or proof["decision"] != expected_digest or proof["index"] != index or proof["target"] != raw["target_id"]
                or proof["execution"] != execution.id or proof["signature"] != execution.signature
                or proof["event"] != execution.social_event_id or execution.id in seen
                or not isinstance(proof["changes"], list) or len(proof["changes"]) > 36):
                raise ValueError()
            event = lane.ctx.db.get(SocialEvent, proof["event"], populate_existing=True)
            binding = lane.ctx.db.scalar(select(SocialEventEvidence.id).where(
                SocialEventEvidence.social_event_id == proof["event"],
                SocialEventEvidence.public_action_execution_id == execution.id).limit(1))
            if (event is None or binding is None or event.world_id != lane.actor.world_id
                or event.actor_world_character_id != lane.actor.id or event.result != "succeeded"
                or event.invalidated_at is not None
                or event.event_type not in ({"like_added"} if execution.action_type == "like" else
                    {"comment_created", "reply_created"} if execution.action_type in {"reply", "comment"} else
                    {"repost_created"} if execution.action_type == "repost" else {"follow_created", "follow_removed"})):
                raise ValueError()
            changes = [RelationshipEffect(RelationshipValidationReference(**p["before"]),
                RelationshipValidationReference(**p["after"])) for p in proof["changes"] if set(p) == {"before", "after"}]
            if len(changes) != len(proof["changes"]) or len({c.before.relationship_state_id for c in changes}) != len(changes):
                raise ValueError()
            output.extend(changes)
            seen.add(execution.id)
        except (KeyError, TypeError, ValueError) as exc:
            raise SocialContextValidationError("effect_receipt_invalid") from exc
    return tuple(output)


def capture(lane, state):
    if not enabled(state):
        return None
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope
    from app.domains.relationships.service.social_context_validation import SocialContextValidationService
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    refs = []
    selected = {row["target_id"] for row in state.get("selections", [])}
    for target, raw in state.get("relationship_validation_receipts", {}).items():
        if selected and target not in selected:
            continue
        receipt = RelationshipValidationReceipt.from_dict(raw)
        refs.extend(CanonicalSocialContextReference(r.target_world_character_id, r.relationship_state_id) for r in receipt.references)
    refs = tuple(dict.fromkeys(refs))
    if len(refs) > 36:
        raise SocialContextValidationError("effect_reference_limit")
    service = SocialContextValidationService(SqlAlchemyRelationshipGraphReadGateway(lane.ctx.db))
    return service.capture(scope=GraphRecallScope(lane.ctx.user_id, lane.actor.world_id, lane.actor.id), references=refs)


def record(lane, state, target, before, execution, event):
    if before is None:
        return
    after = capture(lane, state)
    if execution.status != "succeeded" or execution.social_event_id != event.id:
        raise SocialContextValidationError("effect_receipt_invalid")
    changes = [asdict(RelationshipEffect(old, new)) for old, new in zip(before, after, strict=True) if old != new]
    proof = {"revision": EFFECT_PROGRESS_REVISION, "owner": lane.ctx.user_id,
        "world": lane.actor.world_id, "actor": lane.actor.id, "activity": lane.ctx.run_id,
        "lane": lane.lane, "decision": decision_digest(state), "index": _index(state, target),
        "target": target, "execution": execution.id, "signature": execution.signature,
        "event": event.id, "changes": changes}
    execution.result = {**(execution.result or {}), PRIVATE_KEY: proof}
    lane.ctx.db.flush()
