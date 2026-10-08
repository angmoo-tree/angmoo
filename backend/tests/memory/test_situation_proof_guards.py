"""Persisted proof integrity and current access remain mandatory on every read."""
from copy import deepcopy
from dataclasses import replace
import pytest
from sqlalchemy import func, select

from memory.test_situation_delivery_recovery import durable_stack, delivered_reply
from memory.test_activity_situation_contract import NOW
from memory.test_activity_situation_application import apply
from memory.test_activity_situation_recall import readers
from app.domains.memory.contracts.activity_situation import FinalDeliveredFragment
from app.domains.memory.models.activity_situation import MemorySituationManifest
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.memory.repository.situation_validation import restore_context
from app.runtime.memory.situation_sources import SituationSources


@pytest.mark.parametrize("field", ["ordinal", "source_id", "role", "target_key", "payload_path", "ranges", "source_digest", "call_identity"])
def test_persisted_manifest_tampering_is_not_a_delivery_proof(durable_stack, field):
    db, scope, setting, memory = durable_stack
    row, _ = delivered_reply(db, scope)
    stored = db.get(MemorySituationManifest, row.manifest_id)
    payload = deepcopy(stored.payload)
    if field == "call_identity":
        payload[field] = "another-call"
    else:
        payload["sources"][0][field] = {"ordinal": 99, "ranges": [[0, 99999]]}.get(field, "tampered")
    stored.payload = payload
    db.commit()
    apply(db, setting, memory)
    assert row.state == "blocked" and row.error_code == "situation_manifest_integrity_invalid"
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0


@pytest.mark.parametrize("field", ["logical_activity_id", "scope_version", "target_key", "description", "result"])
def test_cross_call_scope_target_and_success_bindings_are_not_reinterpreted(durable_stack, field):
    db, scope, setting, memory = durable_stack
    row, _ = delivered_reply(db, scope)
    if field == "result":
        result = deepcopy(row.result)
        result["effects"][0]["source_id"] = "another-result"
        row.result = result
    else:
        setattr(row, field, 999 if field == "scope_version" else "unrelated")
    db.commit()
    apply(db, setting, memory)
    assert row.state == "blocked"
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0


def test_only_actual_path_fragment_and_exact_persisted_entry_grant_observation(durable_stack):
    db, scope, _, _ = durable_stack
    row, reply = delivered_reply(db, scope)
    context = restore_context(db, row)
    source = context.sources[0]
    assert db.scalar(select(func.count()).select_from(WorldCharacterFeedObservation)) == 0
    access = SituationSources(db).validate(context, source, now=NOW)
    assert access.state == "available" and access.proof_origin == "situation_delivered"
    assert access.evidence.observation_id is None
    for forged in (replace(source, payload_path="/not-delivered"), replace(source, target_key="another-target"),
                   replace(source, delivery_payload_digest="0" * 64), replace(source, ranges=(), delivered_ranges=())):
        assert SituationSources(db).validate(context, forged, now=NOW).state == "forbidden"
    with pytest.raises(ValueError):
        FinalDeliveredFragment.capture({"selected": "different"}, path="/selected", text=reply.body, payload_digest="a" * 64)
    with pytest.raises((ValueError, KeyError)):
        FinalDeliveredFragment.capture({"selected": reply.body}, path="/omitted", text=reply.body, payload_digest="a" * 64)
    # Untrusted manifest alone does not supply persisted receipt/result binding.
    assert SituationSources(db).validate(context.manifest, source, now=NOW).state == "forbidden"


@pytest.mark.parametrize("change", ["body", "hidden", "visibility", "participant"])
def test_delivery_proof_does_not_override_current_privacy_at_apply_or_hydration(durable_stack, change):
    from app.domains.world_characters.models import WorldCharacter
    db, scope, setting, memory = durable_stack
    row, reply = delivered_reply(db, scope)
    db.commit()
    apply(db, setting, memory)
    item = db.get(MemoryItem, row.applied_item_id)
    assert item is not None
    reader, request, ranked, _ = readers(db, scope, item)
    from app.domains.memory.contracts.recall import RecallDocumentKind
    request = replace(request, episode_source_kinds=(RecallDocumentKind.REPLY,))
    selected = reader.revalidate(request, (ranked,))
    assert len(selected) == 1
    if change == "body":
        reply.body = "Edited source"
    elif change == "hidden":
        reply.report_hidden_at = NOW
    elif change == "visibility":
        reply.visibility = "private"
    else:
        db.get(WorldCharacter, reply.author_world_character_id).status = "inactive"
    db.commit()
    assert reader.revalidate(request, (ranked,)) == ()
    assert reader.hydrate(request, selected).records == ()
    evidence = db.scalar(select(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id == item.id,
        MemoryItemEvidence.source_id == reply.id))
    assert evidence.observation_id is None


def test_inbox_delivery_lineage_is_shared_by_recall_prior_hotbrief_and_relationship_reads(durable_stack):
    from datetime import timedelta
    from app.domains.memory.repository.recall import SqlAlchemyCanonicalRecallRepository
    from app.runtime.memory.source_composition import source_evidence_reader
    from app.runtime.memory.composition import memory_consolidation_repository
    from app.domains.memory.repository.situation_validation import restore_context
    from app.domains.relationships.models.personalization import RelationshipPolicy
    from app.runtime.relationships.review_memories import collect_new_review_memories
    from sqlalchemy.orm import sessionmaker
    db, scope, setting, memory = durable_stack
    row, reply = delivered_reply(db, scope)
    db.add(RelationshipPolicy(world_id=scope.world_id, mode="interpreted", activated_at=NOW-timedelta(days=1)))
    db.commit(); apply(db, setting, memory)
    item = db.get(MemoryItem, row.applied_item_id)
    _, _, ranked, _ = readers(db, scope, item)
    canonical = SqlAlchemyCanonicalRecallRepository(sessionmaker(db.bind), source_reader_factory=source_evidence_reader,
        character_rows=lambda *_: ())
    hotbrief = memory_consolidation_repository(db)
    setting_model = db.get(MemoryScopeSettingModel, setting.id)
    def review_ids():
        grouped = collect_new_review_memories(db, setting=setting_model, now=NOW+timedelta(seconds=1))
        return {value["memory_id"] for values in grouped.values() for value in values}
    prior = SituationSources(db).describe(scope, kind="MEMORY_ITEM", identifier=item.id, delivered=item.summary,
        path="/prior", role="prior", ordinal=99)
    context = restore_context(db, row)
    assert canonical.revalidate_candidates(scope=scope, candidates=(ranked.candidate,), now=NOW)
    assert item.id in {value.id for value in hotbrief.hot_brief_source_items(setting=setting, now=NOW, limit=20)}
    assert item.id in review_ids()
    assert SituationSources(db).validate(context, prior, now=NOW).state == "available"
    reply.report_hidden_at = NOW; db.commit()
    assert canonical.revalidate_candidates(scope=scope, candidates=(ranked.candidate,), now=NOW) == ()
    assert item.id not in {value.id for value in hotbrief.hot_brief_source_items(setting=setting, now=NOW, limit=20)}
    assert item.id not in review_ids()
    assert SituationSources(db).validate(context, prior, now=NOW).state == "forbidden"
