"""Read saved episodes and verify their counterpart through canonical evidence."""

from datetime import UTC, datetime
from collections import defaultdict
from sqlalchemy import select, exists, or_
from sqlalchemy.orm import aliased

from app.core.ids import uuid7_string
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryBatchProfile, MemoryBatchSetting
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.relationships.contracts.daily_review import manifest_digest
from app.domains.relationships.models.personalization import RelationshipReviewMemoryReceipt
from app.domains.relationships.service.personalized_metrics import interpreted_policy, _utc
from app.domains.world_characters.models import WorldCharacter
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader


def _digest(item):
    return manifest_digest({"id": item.id, "version": item.version, "summary": item.summary})


def resolve_memory_batch(db, *, scope, items, activation, now):
    evidence = list(db.scalars(select(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id.in_([item.id for item in items]))))
    by_item = defaultdict(list)
    for row in evidence:
        by_item[row.memory_item_id].append(row)
    identities = tuple(dict.fromkeys((row.source_type, row.source_id) for row in evidence))
    sources = RuntimeEpisodeDetailReader(db).read_sources(scope=scope, identities=identities)
    resolved = []
    for item in items:
        rows = by_item[item.id]
        counterpart_ids = set()
        reason = None
        has_new_experience = False
        for row in rows:
            current = sources.get((row.source_type, row.source_id))
            canonical = None if current is None else current.evidence
            if (canonical is None or row.source_world_id != scope.world_id
                or memory_evidence_blocked_code(scope=scope, source_type=MemorySourceTypeV1(row.source_type), source_id=row.source_id, evidence=canonical)
                or canonical.source_digest != row.source_digest):
                reason = "source_unavailable_or_changed"
                break
            has_new_experience |= _utc(row.source_created_at) >= _utc(activation)
            counterpart = canonical.counterpart_world_character_id
            if counterpart and counterpart != scope.subject_world_character_id:
                counterpart_ids.add(counterpart)
        if not rows or not has_new_experience:
            reason = reason or "no_post_activation_experience"
        if len(counterpart_ids) != 1:
            reason = reason or "counterpart_ambiguous_or_missing"
        target = next(iter(counterpart_ids)) if len(counterpart_ids) == 1 else None
        if item.counterpart_world_character_id and item.counterpart_world_character_id != target:
            reason = reason or "counterpart_conflict"
        if not item.summary.strip() or len(item.summary) > 2000:
            reason = reason or "memory_summary_invalid"
        payload = {"memory_id": item.id, "summary": item.summary, "digest": _digest(item),
            "source_refs": sorted(f"{r.source_type}:{r.source_id}" for r in rows),
            "occurred_at": item.valid_from.isoformat()}
        resolved.append((target, payload, reason))
    return resolved


def episode_lineage_ids(scope):
    # Owner corrections create replacement IDs while retaining the original
    # episode row. Follow that canonical chain; do not relabel arbitrary memories.
    lineage = select(MemoryEpisodeInfo.memory_item_id.label("id")).join(
        MemoryItem, MemoryItem.id == MemoryEpisodeInfo.memory_item_id).where(
            MemoryItem.owner_id == scope.owner_id, MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id).cte("relationship_episode_lineage", recursive=True)
    previous = aliased(MemoryItem)
    return lineage.union(select(previous.superseded_by_id.label("id")).join(lineage, previous.id == lineage.c.id).where(
        previous.superseded_by_id.is_not(None), previous.owner_id == scope.owner_id,
        previous.world_id == scope.world_id, previous.subject_world_character_id == scope.subject_world_character_id))


def collect_new_review_memories(db, *, setting, now):
    scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
    policy = interpreted_policy(db, scope.world_id)
    actor = db.get(WorldCharacter, scope.subject_world_character_id)
    if policy is None or actor is None or actor.control_mode != "autonomous" or actor.status != "active":
        return {}
    grouped = defaultdict(list)
    lineage = episode_lineage_ids(scope)
    cursor = None
    while True:
        query = select(MemoryItem).where(MemoryItem.id.in_(select(lineage.c.id)),
            MemoryItem.owner_id == scope.owner_id, MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id,
            MemoryItem.status == "active", MemoryItem.deleted_at.is_(None), MemoryItem.superseded_by_id.is_(None),
            MemoryItem.valid_from <= now, or_(MemoryItem.pinned_at.is_not(None), MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now),
            MemoryItem.created_at >= policy.activated_at,
            ~exists(select(RelationshipReviewMemoryReceipt.id).where(RelationshipReviewMemoryReceipt.memory_id == MemoryItem.id,
                RelationshipReviewMemoryReceipt.world_id == scope.world_id,
                RelationshipReviewMemoryReceipt.actor_world_character_id == scope.subject_world_character_id)))
        if cursor:
            query = query.where(MemoryItem.id > cursor)
        items = list(db.scalars(query.order_by(MemoryItem.id).limit(100)))
        if not items:
            break
        for target, payload, reason in resolve_memory_batch(db, scope=scope, items=items, activation=policy.activated_at, now=now):
            if reason:
                db.add(RelationshipReviewMemoryReceipt(id=uuid7_string(), world_id=scope.world_id,
                    actor_world_character_id=scope.subject_world_character_id, target_world_character_id=target,
                    memory_id=payload["memory_id"], memory_digest=payload["digest"], status="excluded", reason=reason))
            else:
                grouped[target].append(payload)
        cursor = items[-1].id
    return grouped


class ReviewMemoryReferences:
    def __init__(self, db):
        self.db = db

    def revalidate(self, work):
        base = work.manifest["base"]
        from app.runtime.relationships.review_identity import review_identity_context
        identity = review_identity_context(self.db, owner_id=base["owner_id"], world_id=work.world_id,
            actor_id=work.actor_world_character_id, target_id=work.target_world_character_id)
        if identity != base.get("identity"):
            raise ValueError("relationship_review_identity_changed")
        setting = self.db.get(MemoryScopeSettingModel, base["setting_id"], populate_existing=True)
        batch = self.db.get(MemoryBatchSetting, base["setting_id"], populate_existing=True)
        profile = self.db.get(MemoryBatchProfile, base["owner_id"], populate_existing=True)
        policy = interpreted_policy(self.db, work.world_id)
        actor = self.db.get(WorldCharacter, work.actor_world_character_id)
        if (setting is None or not setting.enabled or batch is None or not batch.ai_enabled or not batch.consent_version
            or profile is None or profile.version != base["profile_version"] or policy is None
            or actor is None or actor.control_mode != "autonomous" or actor.status != "active"
            or setting.owner_id != base["owner_id"] or setting.world_id != work.world_id
            or setting.subject_world_character_id != work.actor_world_character_id):
            raise ValueError("relationship_review_scope_changed")
        scope = MemoryScope(setting.owner_id, work.world_id, work.actor_world_character_id)
        now = datetime.now(UTC)
        frozen = work.manifest["memories"]
        for start in range(0, len(frozen), 100):
            page = frozen[start:start+100]
            items = list(self.db.scalars(select(MemoryItem).where(MemoryItem.id.in_([m["memory_id"] for m in page]),
                MemoryItem.owner_id == scope.owner_id, MemoryItem.world_id == scope.world_id,
                MemoryItem.subject_world_character_id == scope.subject_world_character_id,
                MemoryItem.status == "active", MemoryItem.deleted_at.is_(None), MemoryItem.superseded_by_id.is_(None),
                MemoryItem.valid_from <= now, or_(MemoryItem.pinned_at.is_not(None), MemoryItem.valid_until.is_(None), MemoryItem.valid_until > now)).execution_options(populate_existing=True)))
            expected = {m["memory_id"]: m["digest"] for m in page}
            if len(items) != len(page) or any(expected[item.id] != _digest(item) for item in items):
                raise ValueError("relationship_review_memory_changed")
            for target, _, reason in resolve_memory_batch(self.db, scope=scope, items=items, activation=policy.activated_at, now=now):
                if reason or target != work.target_world_character_id:
                    raise ValueError("relationship_review_evidence_changed")
