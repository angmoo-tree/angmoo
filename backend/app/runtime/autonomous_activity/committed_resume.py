"""Reuse proven effects only after the caller validates current execution rights."""
from datetime import datetime

from app.domains.world_characters.service.activity_state import confirmed_settlement
from app.runtime.autonomous_activity.contracts import identity_key
from app.domains.social.models.posts import Post


def settlement(adapter, state, lane):
    decision = state.get("decision")
    if not decision or decision.get("state_status") == "invalid":
        return None
    revisions = {identifier: revision for candidate in state.get("candidates", [])
        for identifier, revision in candidate.get("source_revisions", {}).items()}
    if lane == "routine":
        revisions = {row["post_id"]: row["revision"] for row in state.get("decision_context", {}).get("source_manifest", [])}
    keys = [identity_key("post", ref, revisions[ref]) if ref in revisions else "invalid:" + ref
        for ref in decision.get("state_source_refs", [])]
    if lane == "routine" and not keys:
        frozen = state.get("lane_data", {}).get("prepared", {})
        if not frozen.get("beat_id"):
            return None
        keys = ["routine_beat:" + frozen["beat_id"]]
    return confirmed_settlement(adapter.ctx.db, world_id=adapter.actor.world_id, actor_id=adapter.actor.id,
        activity_id=state["identity"]["activity_id"], decision_key=identity_key(state["identity"]["activity_id"], lane, "decision"),
        expected_version=state["shared_context"]["current_state"]["version"], source_keys=keys,
        judged_at=datetime.fromisoformat(decision["judged_at"]))


def public_receipt_current(adapter, receipt):
    if receipt is None or receipt.status != "succeeded":
        return False
    if (receipt.run_id != adapter.ctx.run_id or receipt.character_id != adapter.ctx.character.id
            or receipt.world_id != adapter.actor.world_id or receipt.actor_world_character_id != adapter.actor.id
            or receipt.completed_at is None or not isinstance(receipt.result, dict)):
        raise ValueError("activity_resume_effect_scope_invalid")
    for post_id in (receipt.target_post_id, receipt.result.get("post_id")):
        if post_id is not None:
            post = adapter.ctx.db.get(Post, post_id, populate_existing=True)
            if post is None or post.world_id != adapter.actor.world_id or post.deleted_at or post.report_hidden_at:
                raise ValueError("activity_resume_effect_source_missing")
    return True


def committed_executions(adapter, state, lane, *, partial=False):
    if lane == "routine":
        frozen = state.get("lane_data", {}).get("prepared", {})
        if not frozen.get("execution_signature"):
            return None
        from app.domains.routines.repository.public_action_executions import get_public_action_execution_by_signature
        receipt = get_public_action_execution_by_signature(adapter.ctx.db, frozen["execution_signature"])
        if not public_receipt_current(adapter, receipt):
            return None
        confirm_situation(adapter, state, lane, "routine-post", receipt)
        return [receipt]
    decision = state.get("decision")
    if not decision:
        return None
    results = []
    for item in decision.get("decisions", []):
        if item["action"] == "no_action":
            results.append({"target_id": item["target_id"], "status": "no_action"})
            continue
        receipt = adapter.completed_action(state, item["target_id"])
        if not public_receipt_current(adapter, receipt):
            if partial:
                continue
            return None
        confirm_situation(adapter, state, lane, item["target_id"], receipt)
        results.append({"target_id": item["target_id"], "status": "reused", "execution_id": receipt.id})
    return results


def confirm_situation(adapter, state, lane, target, receipt):
    decision = state["decision"]
    override = decision.get("_situation_overrides", {}).get(target)
    manifest = override["manifest"] if override else decision.get("_situation_manifest")
    if manifest is None:
        return  # This frozen call did not admit situation output.
    from app.domains.memory.contracts.activity_situation import stable_digest
    from app.domains.memory.repository.situation_admission import confirm_committed_result
    action = "reply" if receipt.action_type == "comment" else receipt.action_type
    source_type = "POST" if action == "post" else "REPLY" if action == "reply" else "SOCIAL_EVENT"
    source_id = str(receipt.result.get("social_event_id") if action == "like" else receipt.result.get("post_id") or receipt.id)
    confirm_committed_result(adapter.ctx.db, scope_setting_id=manifest["snapshot"]["setting_id"],
        logical_activity_id=state["identity"]["activity_id"], lane=lane, target_key=target,
        manifest_digest=stable_digest(manifest), source_type=source_type, source_id=source_id, effect_kind=action)


async def resume(adapter, state, lane):
    from app.core.async_session import session_call
    return await session_call(adapter.ctx.db, lambda: _resume(adapter, state, lane))


def _resume(adapter, state, lane):
    effects = committed_executions(adapter, state, lane,
        partial=state["stage"] == "Execute" and bool(state.get("failure")))
    if effects is None:
        return None
    if state["stage"] == "ValidateDecision":
        return {"assignments": []}
    if state["stage"] in {"Writer", "ValidateDraft"}:
        return {"drafts": []}
    if state["stage"] == "Execute":
        if lane == "routine":
            receipt = effects[0]
            from app.domains.routines.policies.execution_results import public_execution_result
            result = {**public_execution_result(receipt.result), "routine_outcome": "REUSED_SUCCESS", "status": "succeeded",
                "publish_result": {"public_action_count": 1, "new_public_action_count": 0}}
            return {"executions": [result]}
        return {"executions": effects}
    if state["stage"] == "Settle" and (receipt := settlement(adapter, state, lane)) is not None:
        return {"settlement": {"state": receipt.outcome, "decision_key": receipt.decision_key, "reused": True}}
    return None
