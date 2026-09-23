"""Bounded manual follow-up discovery using frozen saved-memory identities."""
from collections import defaultdict
from sqlalchemy import select, update, or_
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
from app.domains.memory.models.items import MemoryScopeSettingModel, MemoryItem
from app.domains.memory.models.batch import MemoryBatchSetting, MemoryBatchProfile
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.consolidation_requests import progress
from app.domains.relationships.models.manual_review import RelationshipReviewRequest as Request
from app.domains.relationships.models.personalization import RelationshipReviewMemoryReceipt as Receipt, RelationshipReviewWork as Work, RelationshipPolicy
from app.domains.relationships.service.daily_review import plan_review
from app.domains.relationships.service.personalized_metrics import interpreted_policy
from app.runtime.relationships.review_memories import collect_new_review_memories, resolve_memory_batch
from app.runtime.relationships.review_identity import review_identity_context
from app.runtime.relationships.manual_review import TERMINAL


def advance_manual_requests(db, now):
    ids = list(db.scalars(select(Request.memory_request_id).where(Request.canonical_request_id.is_(None),
        Request.state.not_in(TERMINAL + ("paused",))).order_by(Request.accepted_at).limit(16)))
    for identifier in ids:
        # SQLite write reservation / PostgreSQL row lock through the same update.
        db.execute(update(Request).where(Request.memory_request_id == identifier).values(state=Request.state))
        request = db.get(Request, identifier, populate_existing=True)
        if request.state in TERMINAL + ("paused",):
            continue
        memory = db.get(MemoryConsolidationRequest, identifier)
        memory_state = progress(db, memory)["state"]
        if memory_state not in ("completed", "no_work"):
            if memory_state in ("failed", "partial_failed", "paused", "cancelled"):
                request.state, request.last_code = "paused", "memory_stage_incomplete"
            continue
        setting = db.get(MemoryScopeSettingModel, request.scope_setting_id)
        config = db.get(MemoryBatchSetting, request.scope_setting_id)
        profile = db.get(MemoryBatchProfile, setting.owner_id)
        policy = interpreted_policy(db, setting.world_id)
        if not setting.enabled or not config or not config.ai_enabled or not config.consent_version or not profile or not policy:
            request.state, request.last_code = "paused", "relationship_review_scope_changed"
            continue
        from app.runtime.memory.composition import memory_repository
        from app.domains.memory.exceptions import MemoryDomainError
        from app.domains.world_characters.models import WorldCharacter
        actor = db.get(WorldCharacter, setting.subject_world_character_id)
        try:
            memory_repository(db).validate_scope(MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id))
            if actor is None or actor.status != "active" or actor.control_mode != "autonomous":
                raise ValueError("relationship_review_identity_unavailable")
        except (MemoryDomainError, ValueError):
            request.state, request.last_code = "paused", "relationship_review_identity_unavailable"
            continue
        db.execute(update(RelationshipPolicy).where(RelationshipPolicy.world_id == setting.world_id).values(version=RelationshipPolicy.version))
        if request.snapshot is None:
            grouped = collect_new_review_memories(db, setting=setting, now=now)
            snapshot = [{"memory_id": m["memory_id"], "digest": m["digest"], "target_id": target}
                for target, memories in grouped.items() for m in memories]
            # Include already claimed automatic work rather than treating it as no work.
            for receipt in db.scalars(select(Receipt).where(Receipt.world_id == setting.world_id,
                Receipt.actor_world_character_id == setting.subject_world_character_id, Receipt.status == "pending")):
                snapshot.append({"memory_id": receipt.memory_id, "digest": receipt.memory_digest,
                    "target_id": receipt.target_world_character_id})
            request.snapshot = snapshot
        _plan_remaining(db, request, setting, profile, policy, now)
    db.flush()


def _plan_remaining(db, request, setting, profile, policy, now):
    scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
    remaining = defaultdict(list)
    linked = set(request.work_ids)
    waiting = False
    # Page all lookups so large requests do not exceed SQLite parameter limits.
    snapshot = [dict(ref) for ref in request.snapshot]
    for start in range(0, len(snapshot), 100):
        page = snapshot[start:start + 100]
        ids = [r["memory_id"] for r in page]
        receipts = {r.memory_id: r for r in db.scalars(select(Receipt).where(Receipt.world_id == scope.world_id,
            Receipt.actor_world_character_id == scope.subject_world_character_id, Receipt.memory_id.in_(ids)))}
        unclaimed = []
        for ref in page:
            if ref.get("excluded_reason"):
                continue
            receipt = receipts.get(ref["memory_id"])
            if receipt:
                if receipt.status == "excluded":
                    ref["excluded_reason"] = receipt.reason
                if receipt.work_id:
                    linked.add(receipt.work_id)
                waiting |= receipt.status == "pending"
            else:
                unclaimed.append(ref["memory_id"])
        items = list(db.scalars(select(MemoryItem).where(MemoryItem.id.in_(unclaimed),
            MemoryItem.owner_id == scope.owner_id, MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id,
            MemoryItem.status == "active", MemoryItem.deleted_at.is_(None), MemoryItem.superseded_by_id.is_(None),
            MemoryItem.valid_from <= now,
            or_(MemoryItem.pinned_at.is_not(None), MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now))))
        by_id = {ref["memory_id"]: ref for ref in page}
        found = {item.id for item in items}
        for identifier in unclaimed:
            if identifier not in found:
                by_id[identifier]["excluded_reason"] = "memory_unavailable"
        for target, payload, reason in resolve_memory_batch(db, scope=scope, items=items, activation=policy.activated_at, now=now):
            ref = by_id[payload["memory_id"]]
            if reason or target != ref["target_id"] or payload["digest"] != ref["digest"]:
                ref["excluded_reason"] = reason or "memory_or_counterpart_changed"
                continue  # Changed/unavailable inputs are not substituted into this snapshot.
            remaining[target].append(payload)
    for target, memories in remaining.items():
        try:
            identity = review_identity_context(db, owner_id=scope.owner_id, world_id=scope.world_id,
                actor_id=scope.subject_world_character_id, target_id=target)
        except ValueError:
            request.state, request.last_code = "paused", "relationship_review_identity_unavailable"
            return
        root = plan_review(db, world_id=scope.world_id, actor_id=scope.subject_world_character_id, target_id=target,
            period_key="manual:" + request.memory_request_id, memories=memories,
            base={"identity": identity, "owner_id": scope.owner_id, "setting_id": setting.id,
                "profile_version": profile.version, "model_id": profile.model_id, "thinking_level": profile.thinking_level})
        linked.add(root.id)
        waiting = True  # If an active root was reused, remaining refs are revisited next tick.
    request.snapshot = snapshot
    request.work_ids = sorted(linked)
    works = list(db.scalars(select(Work).where(Work.id.in_(linked))))
    waiting |= any(w.status not in ("applied", "stale") for w in works)
    request.state = "running" if waiting else "completed" if any(w.status == "applied" for w in works) else "no_relationship_work"
    if not waiting:
        request.completed_at = now
