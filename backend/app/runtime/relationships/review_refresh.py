"""Refresh changed scope inputs without replaying unaffected completed parts."""

from datetime import UTC, datetime
from sqlalchemy import select, or_
from app.domains.memory.models.batch import MemoryBatchProfile
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.contracts.daily_review import manifest_digest
from app.domains.relationships.service.daily_review import rebase_review
from app.domains.relationships.service.state import _relationship_state
from app.domains.relationships.service.personalized_metrics import interpreted_policy
from app.runtime.relationships.review_memories import resolve_memory_batch
from app.runtime.relationships.review_identity import review_identity_context


def refresh_review_inputs(db, root):
    base = root.manifest['base']
    policy = interpreted_policy(db, root.world_id)
    if policy is None:
        return
    scope = MemoryScope(base['owner_id'], root.world_id, root.actor_world_character_id)
    now = datetime.now(UTC)
    retained, changed, excluded = [], set(), set()
    frozen = root.manifest['memories']
    for start in range(0, len(frozen), 100):
        page = frozen[start:start+100]
        items = list(db.scalars(select(MemoryItem).where(MemoryItem.id.in_([m['memory_id'] for m in page]),
            MemoryItem.owner_id == scope.owner_id, MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id,
            MemoryItem.status == 'active', MemoryItem.deleted_at.is_(None), MemoryItem.superseded_by_id.is_(None),
            MemoryItem.valid_from <= now, or_(MemoryItem.pinned_at.is_not(None), MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now))))
        resolved = {payload['memory_id']: (target, payload, reason) for target, payload, reason in
            resolve_memory_batch(db, scope=scope, items=items, activation=policy.activated_at, now=now)}
        for old in page:
            target, payload, reason = resolved.get(old['memory_id'], (None, None, 'memory_unavailable'))
            if reason or target != root.target_world_character_id:
                excluded.add(old['memory_id'])
                changed.add(old['memory_id'])
            else:
                retained.append(payload)
                if payload["digest"] != old["digest"] or payload["source_refs"] != old["source_refs"]:
                    changed.add(old['memory_id'])
    if changed:
        by_id = {m['memory_id']: m for m in retained}
        receipts = db.scalars(select(RelationshipReviewMemoryReceipt).where(RelationshipReviewMemoryReceipt.work_id == root.id))
        for receipt in receipts:
            if receipt.memory_id in excluded:
                receipt.status, receipt.reason = 'excluded', 'memory_or_evidence_changed'
            elif receipt.memory_id in changed:
                receipt.memory_digest = by_id[receipt.memory_id]['digest']
        root.manifest = {**root.manifest, 'memories': retained if root.phase == 'direct' else [{k: v for k, v in m.items() if k != 'summary'} for m in retained]}
        root.manifest_digest = manifest_digest(root.manifest)
        descendants = list(db.scalars(select(RelationshipReviewWork).where(
            RelationshipReviewWork.world_id == root.world_id,
            RelationshipReviewWork.actor_world_character_id == root.actor_world_character_id,
            RelationshipReviewWork.target_world_character_id == root.target_world_character_id,
            RelationshipReviewWork.period_key == root.period_key)))
        affected = {root.id}
        for part in descendants:
            if part.phase != 'partial':
                continue
            memories = part.manifest['payload']['memories']
            if not any(m['memory_id'] in changed for m in memories):
                continue
            updated = [by_id[m['memory_id']] for m in memories if m['memory_id'] in by_id]
            part.manifest = {'payload': {**part.manifest['payload'], 'memories': updated}}
            part.manifest_digest = manifest_digest(part.manifest)
            affected.add(part.id)
            if not updated:
                empty = dict(findings=[], uncertainty='', memory_refs=[])
                part.status, part.result = 'ready', {**empty, '_execution': {'result_digest': manifest_digest(empty)}}
                affected.remove(part.id)
                if part.parent_id:
                    affected.add(part.parent_id)
        rows = {p.id: p for p in descendants}
        for identifier in list(affected):
            parent = rows[identifier].parent_id
            while parent:
                affected.add(parent)
                parent = rows[parent].parent_id
        for identifier in affected:
            part = rows[identifier]
            part.status, part.result, part.error_code = 'pending', None, None
            part.lease_token, part.lease_until, part.next_attempt_at = None, None, None
        if not retained:
            for row in descendants:
                row.status, row.error_code = 'stale', 'relationship_review_no_eligible_memory'
    profile = db.get(MemoryBatchProfile, base['owner_id'])
    identity = review_identity_context(db, owner_id=base['owner_id'], world_id=root.world_id,
        actor_id=root.actor_world_character_id, target_id=root.target_world_character_id)
    if profile and (profile.version != base['profile_version'] or identity != base.get('identity')) and retained:
        root.manifest = {**root.manifest, 'base': {**root.manifest['base'], 'profile_version': profile.version, 'identity': identity,
            'model_id': profile.model_id, 'thinking_level': profile.thinking_level}}
        rebase_review(db, root, _relationship_state(db, world_id=root.world_id,
            actor_world_character_id=root.actor_world_character_id, target_world_character_id=root.target_world_character_id))
