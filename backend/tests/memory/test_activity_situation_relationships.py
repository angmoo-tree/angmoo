"""Saved old/new experience union and same-scope relationship ordering."""
from dataclasses import replace
from datetime import timedelta
from sqlalchemy import select

from memory.test_activity_situation_contract import stack, values, NOW
from memory.test_activity_situation_application import real_source, apply
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeBundle, MemoryEpisodeInfo
from app.domains.relationships.models.personalization import RelationshipPolicy
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.relationships.review_memories import collect_new_review_memories, resolve_memory_batch
from app.runtime.relationships.situation_ordering import require_application_complete
import pytest


def test_old_and_new_memory_union_uses_core_counterpart_and_keeps_deleted_new_summary(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    post.author_world_character_id = "consolidation-counterpart"
    post.author_character_id = "consolidation-counterpart-character"
    db.add(WorldCharacterFeedObservation(id="situation-observed", world_id=scope.world_id,
        observer_world_character_id=scope.subject_world_character_id, post_id=post.id,
        status="observed", claim_token="fixture", cycle_key="fixture", run_id="fixture",
        lease_expires_at=NOW, observed_at=NOW, post_created_at=NOW, claimed_at=NOW))
    db.add(RelationshipPolicy(world_id=scope.world_id, mode="interpreted", activated_at=NOW-timedelta(days=1)))
    db.commit()
    manifest, draft, result = values(db, scope, target=post.id)
    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/selected/body", role="core", ordinal=0, target=post.id)
    row = admit(db, manifest=replace(manifest, sources=(source,)), draft=draft,
        result=replace(result, counterpart_id=post.author_world_character_id), now=NOW)
    apply(db, setting, memory)
    new = db.get(MemoryItem, row.applied_item_id)
    assert new is not None
    old = MemoryItem(id="historical-episode", owner_id=scope.owner_id, world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id,
        counterpart_world_character_id=post.author_world_character_id, summary="이전 방식의 저장된 경험",
        memory_kind="AUTOBIOGRAPHICAL_EVENT", status="active", confidence=1, salience=.5,
        created_at=NOW, valid_from=NOW, valid_until=NOW+timedelta(days=180))
    db.add(old)
    db.add(MemoryEpisodeBundle(id="historical-bundle", scope_setting_id=setting.id, activation_epoch="history",
        policy_version="episode-selection.v1", cutoff_sequence=1, manifest_hash="0"*64,
        result_hash="0"*64, manifest_json="{}"))
    db.flush()
    db.add(MemoryEpisodeInfo(memory_item_id=old.id, bundle_id="historical-bundle", policy_version="episode-selection.v1"))
    evidence = db.scalar(select(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id == new.id))
    db.add(MemoryItemEvidence(id="historical-evidence", memory_item_id=old.id, source_type=evidence.source_type,
        source_id=evidence.source_id, source_world_id=evidence.source_world_id,
        source_created_at=evidence.source_created_at, source_digest=evidence.source_digest))
    db.commit()
    grouped = collect_new_review_memories(db, setting=db.get(MemoryScopeSettingModel, setting.id), now=NOW+timedelta(seconds=1))
    assert {value["memory_id"] for value in grouped[post.author_world_character_id]} == {old.id, new.id}
    db.rollback()
    post.deleted_at = NOW
    db.commit()
    resolved = resolve_memory_batch(db, scope=scope, items=[new, old], activation=NOW-timedelta(days=1), now=NOW)
    assert resolved[0][0] == post.author_world_character_id and resolved[0][2] is None
    assert resolved[1][0] == post.author_world_character_id and resolved[1][2] is None


def test_manual_relationship_freeze_waits_only_for_accepted_same_scope_cutoff(stack):
    from types import SimpleNamespace
    from app.runtime.relationships.review_refresh import refresh_review_inputs
    from app.runtime.relationships.review_memories import ReviewMemoryReferences
    db, scope, setting, _ = stack
    manifest, draft, result = values(db, scope)
    admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    # Pending activities are not a request: relationship reads must not flush them.
    require_application_complete(db, setting.id)
    request_run(db, setting, trigger="manual", request_key="relation-order-0001", expected_version=1, now=NOW)
    from app.domains.relationships.policies.daily_review import REVIEW_INPUT_POLICY
    root = SimpleNamespace(manifest={"input_policy": REVIEW_INPUT_POLICY, "base": {"setting_id": setting.id}})
    for operation in (lambda: require_application_complete(db, setting.id),
        lambda: refresh_review_inputs(db, root), lambda: ReviewMemoryReferences(db).revalidate(root)):
        with pytest.raises(ValueError, match="relationship_memory_application_pending"):
            operation()
    require_application_complete(db, "another-scope")
    assert db.scalar(select(MemoryItem.id)) is None
    # Selection must reach another actor even if the oldest review is blocked.
    from sqlalchemy import literal, union_all
    from app.runtime.relationships.situation_ordering import scope_application_pending
    queue = union_all(select(literal(scope.world_id).label("world"),
        literal(scope.subject_world_character_id).label("actor"), literal(0).label("order")),
        select(literal(scope.world_id), literal("another-actor"), literal(1))).subquery()
    selected = db.scalar(select(queue.c.actor).where(
        ~scope_application_pending(queue.c.world, queue.c.actor)).order_by(queue.c.order).limit(1))
    assert selected == "another-actor"
