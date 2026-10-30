"""Review owned situation summaries, without reading original texts or snapshots."""

from datetime import UTC, datetime
from collections import defaultdict
from sqlalchemy import select, exists, or_
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.activity_configuration import MemorySubjectProfile
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo, MemorySituationReceipt
from app.domains.relationships.contracts.daily_review import manifest_digest
from app.domains.relationships.models.personalization import RelationshipReviewMemoryReceipt
from app.domains.relationships.service.personalized_metrics import interpreted_policy, _utc
from app.domains.world_characters.models import WorldCharacter


def _digest(item):
    return manifest_digest({"id": item.id, "version": item.version, "summary": item.summary})


def resolve_memory_batch(db, *, scope, items, activation, now):
    from app.domains.memory.contracts.access_validation import MemoryAccessValidation
    from app.domains.memory.repository.access_batch import prepare_representation, collection
    from app.domains.memory.repository.experience import prepare
    validation = MemoryAccessValidation(db, now)
    # Current memory rights and stored participant metadata only. In particular,
    # prepare_access would hydrate snapshots intended for SNS/Chat recall.
    with db.no_autoflush:
        prepare_representation(validation, items)
        prepare(db, items, now, validation=validation, include_snapshots=False)
        collection(validation, "review_participants", MemoryItemEvidence, MemoryItemEvidence.memory_item_id,
            [item.id for item in items if item.counterpart_world_character_id is None])
        infos = [validation.get(MemoryActivitySituationInfo, item.id) for item in items
            if item.counterpart_world_character_id is None]
        sequences = [info.receipt_sequence for info in infos if info is not None]
        # Select the participant scalar, never the receipt's input/output text.
        counterparts = dict(db.execute(select(MemorySituationReceipt.sequence,
            MemorySituationReceipt.result["counterpart_id"].as_string()).join(MemoryScopeSettingModel,
                MemoryScopeSettingModel.id == MemorySituationReceipt.scope_setting_id).where(
                    MemorySituationReceipt.sequence.in_(sequences),
                    MemoryScopeSettingModel.owner_id == scope.owner_id,
                    MemoryScopeSettingModel.world_id == scope.world_id,
                    MemoryScopeSettingModel.subject_world_character_id == scope.subject_world_character_id)).all()) if sequences else {}
        return _resolve_memory_batch(db, scope=scope, items=items, activation=activation,
            now=now, validation=validation, counterparts=counterparts)


def _resolve_memory_batch(db, *, scope, items, activation, now, validation, counterparts):
    from app.domains.memory.repository.experience import accessible
    resolved=[]
    for item in items:
        payload={"memory_id":item.id,"summary":item.summary,"digest":_digest(item),
            "occurred_at":item.valid_from.isoformat()}
        if not accessible(db,scope,item,now,validation=validation,check_snapshot=False):
            resolved.append((None,payload,"memory_unavailable_or_changed"));continue
        target=item.counterpart_world_character_id
        situation=validation.get(MemoryActivitySituationInfo,item.id)
        occurred=item.valid_from
        if situation is not None:
            target=target or counterparts.get(situation.receipt_sequence)
            occurred=situation.occurred_at
        if target is None:
            candidates={v for row in validation.collections.get(("review_participants",item.id),())
                if row.source_world_id==scope.world_id
                for v in (row.actor_world_character_id,row.target_world_character_id)
                if v and v!=scope.subject_world_character_id}
            target=next(iter(candidates)) if len(candidates)==1 else None
        reason=None
        if target is None or target==scope.subject_world_character_id:
            reason="counterpart_ambiguous_or_missing"
        elif _utc(occurred)<_utc(activation):
            reason="no_post_activation_experience"
        elif not item.summary.strip() or len(item.summary)>2000:
            reason="memory_summary_invalid"
        payload["occurred_at"]=occurred.isoformat()
        resolved.append((target,payload,reason))
    return resolved


def episode_lineage_ids(scope):
    # Every correction/combination owns direct metadata after migration.
    return select(MemoryItem.id.label("id")).where(
        or_(MemoryItem.memory_kind == "AUTOBIOGRAPHICAL_EVENT",
            exists(select(MemoryEpisodeInfo.memory_item_id).where(MemoryEpisodeInfo.memory_item_id==MemoryItem.id)),
            exists(select(MemoryActivitySituationInfo.memory_item_id).where(MemoryActivitySituationInfo.memory_item_id==MemoryItem.id))),
        MemoryItem.owner_id==scope.owner_id,MemoryItem.world_id==scope.world_id,
        MemoryItem.subject_world_character_id==scope.subject_world_character_id).cte("relationship_episode_lineage")


def collect_new_review_memories(db, *, setting, now, excluded=None):
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
            MemoryItem.created_at <= now,
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
                if excluded is not None:
                    excluded.append((target, payload, reason))
            else:
                grouped[target].append(payload)
        cursor = items[-1].id
    return grouped


class ReviewMemoryReferences:
    def __init__(self, db):
        self.db = db

    def revalidate(self, work):
        base = work.manifest["base"]
        from app.runtime.relationships.situation_ordering import require_application_complete
        require_application_complete(self.db, base["setting_id"])
        from app.runtime.relationships.review_credentials import validate
        validate(self.db, work, base)
        from app.runtime.relationships.review_identity import review_identity_context
        identity = review_identity_context(self.db, owner_id=base["owner_id"], world_id=work.world_id,
            actor_id=work.actor_world_character_id, target_id=work.target_world_character_id)
        if identity != base.get("identity"):
            raise ValueError("relationship_review_identity_changed")
        setting = self.db.get(MemoryScopeSettingModel, base["setting_id"], populate_existing=True)
        batch = self.db.get(MemoryBatchSetting, base["setting_id"], populate_existing=True)
        profile = self.db.get(MemorySubjectProfile, base["setting_id"], populate_existing=True)
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
            if len(items) != len(expected) or any(expected[item.id] != _digest(item) for item in items):
                raise ValueError("relationship_review_memory_changed")
            resolved=resolve_memory_batch(self.db,scope=scope,items=items,activation=policy.activated_at,now=now)
            for target, payload, reason in resolved:
                if reason is not None or target!=work.target_world_character_id:
                    raise ValueError("relationship_review_evidence_changed")
