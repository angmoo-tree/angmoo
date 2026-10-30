"""Retain old attempts; only unsubmitted reviews may adopt the new input policy."""
from datetime import UTC, datetime
from sqlalchemy import select, update

from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.items import MemoryItem
from app.domains.relationships.models.personalization import (
    RelationshipPolicy, RelationshipReviewWork, RelationshipReviewMemoryReceipt,
)
from app.domains.relationships.policies.daily_review import REVIEW_INPUT_POLICY


def retire_old_review(db, root):
    if root.status in {"applied", "stale"} or root.manifest.get("input_policy") == REVIEW_INPUT_POLICY:
        return
    # Use the planning lock before inspecting the whole durable attempt tree.
    db.execute(update(RelationshipPolicy).where(RelationshipPolicy.world_id == root.world_id)
        .values(version=RelationshipPolicy.version))
    db.refresh(root, with_for_update=True)
    if root.status in {"applied", "stale"}:
        return
    rows, pending = [root], [root.id]
    while pending:
        children = list(db.scalars(select(RelationshipReviewWork).where(
            RelationshipReviewWork.parent_id.in_(pending)).with_for_update()))
        rows.extend(children)
        pending = [row.id for row in children]
    submitted = any(row.attempts or row.result is not None or row.lease_token for row in rows)
    for row in rows:
        row.status, row.error_code = "stale", "relationship_review_input_policy_changed"
        row.lease_token, row.lease_until, row.next_attempt_at = None, None, None
    receipts = list(db.scalars(select(RelationshipReviewMemoryReceipt).where(
        RelationshipReviewMemoryReceipt.work_id == root.id,
        RelationshipReviewMemoryReceipt.status == "pending")))
    if submitted:
        # Never replay a paid/unknown request under a different policy. Frozen
        # input, received results and journal files remain available for audit.
        for receipt in receipts:
            receipt.status, receipt.reason = "excluded", "review_input_policy_changed_after_submission"
        return
    base = root.manifest["base"]
    policy = db.get(RelationshipPolicy, root.world_id)
    scope = MemoryScope(base["owner_id"], root.world_id, root.actor_world_character_id)
    from app.runtime.relationships.review_memories import resolve_memory_batch
    retained = []
    for start in range(0, len(receipts), 100):
        items = list(db.scalars(select(MemoryItem).where(
            MemoryItem.id.in_([r.memory_id for r in receipts[start:start+100]]),
            MemoryItem.owner_id == scope.owner_id, MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id)))
        if policy is not None and policy.activated_at is not None:
            retained.extend(payload for target, payload, reason in resolve_memory_batch(db,
                scope=scope, items=items, activation=policy.activated_at, now=datetime.now(UTC))
                if reason is None and target == root.target_world_character_id)
    eligible = {m["memory_id"] for m in retained}
    for receipt in receipts:
        if receipt.memory_id not in eligible:
            receipt.status, receipt.reason = "excluded", "memory_or_scope_changed"
    if retained:
        from app.domains.relationships.service.daily_review import plan_review
        # A separate immutable record retains the obsolete input and its hash.
        plan_review(db, world_id=root.world_id, actor_id=root.actor_world_character_id,
            target_id=root.target_world_character_id, period_key="summary-v1-" + root.id,
            base=base, memories=retained, previous_work_id=root.id)
