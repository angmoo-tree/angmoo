"""Real source writers, Today capture, durable receipts and canonical access."""
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import event as sql_event, func, select

from memory.test_situation_delivery_recovery import durable_stack
from memory.test_activity_situation_application import real_source, apply
from memory.test_activity_situation_contract import values, NOW
from memory.test_activity_situation_recall import readers
from memory.test_sqlite_vec1 import index
from app.domains.memory.contracts.activity_situation import CommittedEffect
from app.domains.memory.contracts.access_validation import MemoryAccessValidation
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.relationships.models.social import SocialEvent, SocialEventEvidence, RelationshipState
from app.domains.relationships.service.source_reactions import record_source_reaction_event
from app.domains.relationships.service.source_posts import record_source_post_event
from app.domains.social.models.posts import Post
from app.domains.world_characters.models import WorldCharacter
from app.runtime.autonomous_activity.situation_memory import freeze_social_input
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.memory.situation_source_batch import prepare_sources
from app.runtime.memory.episode_details import _SourceQueries
from app.runtime.social.today_activity import today_social_activity_reader

PEER = "consolidation-counterpart"


def manual_event(db, scope, kind="like_added"):
    root = real_source(db, scope)
    if kind in {"like_added", "like_removed"}:
        identifier = record_source_reaction_event(db, world_id=scope.world_id,
            actor_world_character_id=PEER, target_world_character_id=scope.subject_world_character_id,
            post=root, root_post=root, event_type=kind, transition_key=kind)
    else:
        post = Post(id="manual-source", world_id=scope.world_id,
            author_world_character_id=PEER, author_character_id="consolidation-counterpart-character",
            author_name="peer", title="A note", body="The afternoon was calm.",
            reply_to_post_id=root.id if kind == "reply_created" else None)
        db.add(post); db.flush()
        identifier = record_source_post_event(db, world_id=scope.world_id,
            actor_world_character_id=PEER,
            target_world_character_id=scope.subject_world_character_id if kind == "reply_created" else None,
            operation="reply" if kind == "reply_created" else "post", post=post,
            root_post=root if kind == "reply_created" else post,
            target_post=root if kind == "reply_created" else None,
            request_key="manual-source-0001", failure_injector=None)
    db.commit()
    return db.get(SocialEvent, identifier), root


def today(db, scope):
    result = today_social_activity_reader(db).read(owner_id=scope.owner_id, world_id=scope.world_id,
        subject_world_character_id=scope.subject_world_character_id,
        started_at=datetime(2020, 1, 1, tzinfo=UTC), complete_through=datetime.now(UTC)+timedelta(seconds=1))
    return [asdict(row) for row in result.records]


def capture(db, scope, *, records=None, node="FeedDecisionDraft"):
    base, _, _ = values(db, scope)
    payload = {"context": {"today_activity": {"records": today(db, scope) if records is None else records}}}
    wire = json.dumps(payload, ensure_ascii=False, default=str)
    payload = json.loads(wire)
    return freeze_social_input(SimpleNamespace(db=db, run_id="manual-fixture", user_id=scope.owner_id), base.snapshot,
        node=node, payload=payload, transmitted=wire, state={
            "identity": {"activity_id": "manual-fixture", "world_id": scope.world_id,
                         "actor_id": scope.subject_world_character_id},
            "shared_context": {"today_activity": {"records": json.loads(json.dumps(today(db, scope), default=str))}}})


def receipt(db, scope, post, manifest, lane="feed"):
    _, draft, result = values(db, scope, target=post.id)
    output = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/committed_result/body", role="committed_result", ordinal=len(manifest.sources), target=post.id)
    result = replace(result, lane=lane, planned_effects=("post",),
        effects=(CommittedEffect("post", "POST", post.id, "succeeded"),), result_sources=(output,))
    row = admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    db.commit()
    return row


@pytest.mark.parametrize("node,lane", [("InboxDecisionDraft", "inbox"), ("FeedDecisionDraft", "feed"), ("RoutineDecisionDraft", "routine")])
@pytest.mark.parametrize("kind", ["like_added", "like_removed", "reply_created"])
def test_manual_event_survives_capture_apply_recall_and_generic_access_stays_denied(durable_stack, kind, node, lane):
    db, scope, setting, memory = durable_stack
    source, post = manual_event(db, scope, kind)
    manifest = capture(db, scope, node=node)
    entry = next(s for s in manifest.sources if s.source_id == source.id)
    assert entry.role == "background" and source.retrieval_status == "audit_only"
    raw = SituationSources(db).read_evidence(scope=scope, source_type=MemorySourceTypeV1.SOCIAL_EVENT, source_id=source.id)
    assert memory_evidence_blocked_code(scope=scope, source_type=raw.source_type, source_id=source.id, evidence=raw) == "memory_source_not_visible"
    row = receipt(db, scope, post, manifest, lane)
    context = restore_context(db, row)
    from app.domains.memory.repository.experience import validate_captured_sources
    direct = next(access for source_entry, access in validate_captured_sources(db, context, (), row, now=NOW, reader=RuntimeEpisodeDetailReader(db))
                  if source_entry == entry)
    assert direct.state == "available" and direct.proof_origin == "stored_experience"
    # Historical delivery grants no permission to read the original event.
    assert SituationSources(db).validate(context, entry, now=NOW).state == "forbidden"
    apply(db, setting, memory)
    assert row.state == "applied", row.error_code
    item = db.get(MemoryItem, row.applied_item_id)
    reader, request, ranked, _ = readers(db, scope, item)
    assert reader.revalidate(request, (ranked,))
    assert reader.hydrate(request, reader.revalidate(request, (ranked,))).records
    db.expire_all()
    apply(db, setting, memory)
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 1
    assert db.scalar(select(func.count()).select_from(RelationshipState)) == 0
    assert db.get(SocialEvent, source.id).retrieval_status == "audit_only"


def test_manual_post_for_author_and_outgoing_reaction(durable_stack):
    db, scope, _, memory = durable_stack
    source, root = manual_event(db, scope, "post_published")
    peer_scope = replace(scope, subject_world_character_id=PEER)
    service = MemoryScopeService(memory)
    setting = service.get_or_create(peer_scope)
    service.update(peer_scope, expected_version=setting.version, enabled=True, retention_days=180)
    db.commit()
    manifest = capture(db, peer_scope)
    assert any(entry.source_id == source.id for entry in manifest.sources)
    assert not any(row["source_id"] == source.id for row in today(db, scope))
    reaction = record_source_reaction_event(db, world_id=scope.world_id,
        actor_world_character_id=PEER, target_world_character_id=scope.subject_world_character_id,
        post=root, root_post=root, event_type="like_added", transition_key="outgoing-0001")
    db.commit()
    assert any(entry.source_id == reaction for entry in capture(db, peer_scope).sources)


@pytest.mark.parametrize("mutation", ["root", "evidence_kind", "invalidation", "hidden", "membership", "duplicate_evidence", "private", "target", "block"])
def test_historical_input_survives_source_changes_without_promoting_event(durable_stack, mutation):
    db, scope, *_ = durable_stack
    source, post = manual_event(db, scope)
    manifest = capture(db, scope)
    row = receipt(db, scope, post, manifest)
    entry = next(s for s in manifest.sources if s.source_id == source.id)
    proof = db.scalar(select(SocialEventEvidence).where(SocialEventEvidence.social_event_id == source.id))
    if mutation == "root": proof.root_post_id = None
    elif mutation == "evidence_kind": proof.evidence_kind = "execution"
    elif mutation == "invalidation": source.invalidated_at, source.invalidation_reason = NOW, "manual_exclusion"
    elif mutation == "hidden": post.report_hidden_at = NOW
    elif mutation == "membership": db.get(WorldCharacter, PEER).status = "inactive"
    elif mutation == "private": post.visibility = "private"
    elif mutation == "target":
        source.actor_world_character_id = scope.subject_world_character_id
        source.target_world_character_id = PEER
    elif mutation == "block":
        from app.domains.social.models.feed import WorldCharacterBlock
        db.add(WorldCharacterBlock(id="manual-source-block", world_id=scope.world_id,
            blocker_world_character_id=scope.subject_world_character_id, blocked_world_character_id=PEER))
    else:
        material = {c.key: getattr(proof, c.key) for c in proof.__table__.columns if c.key != "id"}
        material["evidence_kind"] = "post"
        db.add(SocialEventEvidence(id="ambiguous-evidence", **material))
    db.commit()
    context = restore_context(db, row)
    access = SituationSources(db).validate(context, entry, now=NOW)
    assert access.state in {"forbidden", "changed"}
    from app.domains.memory.repository.experience import validate_captured_sources
    assert next(access for source_entry, access in validate_captured_sources(db, context, (), row, now=NOW, reader=RuntimeEpisodeDetailReader(db))
                if source_entry == entry).state == "available"
    assert source.retrieval_status == "audit_only"


def test_non_successful_event_is_never_a_source_basis():
    from app.domains.relationships.service.source_event_evidence import manual_source_basis, SourceEventEvidenceError
    # Canonical DB also rejects this result; validate the pure boundary separately.
    event = SimpleNamespace(world_id="world", actor_world_character_id="actor",
        target_world_character_id="subject", event_type="like_added", retrieval_status="audit_only",
        result="failed", invalidated_at=None, invalidation_reason=None)
    with pytest.raises(SourceEventEvidenceError, match="event_unavailable"):
        manual_source_basis(event, (), {}, world_id="world", subject_id="subject",
            active_ids={"actor", "subject"}, blocked_ids=set(), max_depth=8, allowed_visibilities={"public"})


@pytest.mark.parametrize("field", ["source_id", "actor_world_character_id", "target_post_id", "source_revision"])
def test_final_record_must_match_canonical_binding(durable_stack, field):
    db, scope, *_ = durable_stack
    source, _ = manual_event(db, scope)
    records = today(db, scope)
    record = next(r for r in records if r["source_id"] == source.id)
    record[field] = "forged"
    with pytest.raises(ValueError, match="situation_source_not_admitted"):
        capture(db, scope, records=records)


def test_no_delivery_or_legacy_revision_cannot_borrow_cached_permission(durable_stack):
    db, scope, *_ = durable_stack
    source, post = manual_event(db, scope)
    manifest = capture(db, scope)
    row = receipt(db, scope, post, manifest)
    context = restore_context(db, row)
    entry = next(s for s in manifest.sources if s.source_id == source.id)
    validation = MemoryAccessValidation(db, NOW)
    reader = SituationSources(db)
    assert reader.validate(context, entry, now=NOW, validation=validation).state == "forbidden"
    assert reader.validate(context.manifest, entry, now=NOW, validation=validation).state == "forbidden"
    for revision in ("situation-validation.v2", "situation-validation.v3", "situation-validation.v4", "situation-validation.v5"):
        assert reader.validate(replace(context, revision=revision), entry, now=NOW, validation=validation).state == "forbidden"
    for forged in (replace(entry, payload_path="/another"), replace(entry, delivery_payload_digest="0"*64),
                   replace(entry, role="core")):
        assert reader.validate(context, forged, now=NOW, validation=validation).state == "forbidden"


def test_event_time_content_and_unlike_do_not_rewrite_prior_event(durable_stack):
    db, scope, *_ = durable_stack
    source, post = manual_event(db, scope)
    before = capture(db, scope)
    post.body = "An edited ordinary afternoon."; db.commit()
    after = capture(db, scope)
    first = next(s for s in before.sources if s.source_id == source.id)
    second = next(s for s in after.sources if s.source_id == source.id)
    assert first.source_digest != second.source_digest
    record_source_reaction_event(db, world_id=scope.world_id, actor_world_character_id=PEER,
        target_world_character_id=scope.subject_world_character_id, post=post, root_post=post,
        event_type="like_removed", transition_key="unlike-transition")
    db.commit()
    later = capture(db, scope)
    assert next(s for s in later.sources if s.source_id == source.id).source_digest == second.source_digest
    assert len([s for s in later.sources if s.source_type == "SOCIAL_EVENT"]) == 2


def test_capture_reads_only_and_trimmed_event_has_no_manifest_entry(durable_stack):
    db, scope, *_ = durable_stack
    source, _ = manual_event(db, scope)
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany): statements.append(statement.lstrip().split()[0].upper())
    sql_event.listen(db.bind, "before_cursor_execute", record)
    try:
        manifest = capture(db, scope)
        assert any(s.source_id == source.id for s in manifest.sources)
        trimmed = capture(db, scope, records=[])
        assert not trimmed.sources
    finally:
        sql_event.remove(db.bind, "before_cursor_execute", record)
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE", "REPLACE"}


def test_source_changed_after_page_preparation_uses_stored_experience(durable_stack):
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
    from app.domains.memory.repository.situation_apply import prepare_page, apply_page
    from app.runtime.memory.situation_application_sources import PreparedSituationSources
    db, scope, setting, memory = durable_stack
    _, post = manual_event(db, scope)
    row = receipt(db, scope, post, capture(db, scope))
    get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
    request = request_run(db, setting, trigger="manual", request_key="source-preparation-change", expected_version=1, now=NOW)
    token = claim_run(db, request.run_id, now=NOW); db.commit()
    page = prepare_page(db, run_id=request.run_id, token=token, now=NOW)
    post.body += " changed after immutable preparation"; db.commit()
    apply_page(db, memory, PreparedSituationSources(db), run_id=request.run_id, token=token, now=NOW, prepared=page)
    db.commit()
    assert row.state == "applied" and db.scalar(select(MemoryItem.id)) is not None


def test_nested_manual_reply_keeps_parent_root_and_cycle_guard(durable_stack):
    db, scope, *_ = durable_stack
    source, root = manual_event(db, scope, "reply_created")
    child = db.get(Post, "manual-source")
    parent = Post(id="manual-intermediate", world_id=scope.world_id,
        author_world_character_id=scope.subject_world_character_id,
        author_character_id="consolidation-subject-character", author_name="subject",
        title="Nested note", body="An intermediate reply.", reply_to_post_id=root.id)
    db.add(parent); db.flush()
    child.reply_to_post_id = parent.id
    proof = db.scalar(select(SocialEventEvidence).where(SocialEventEvidence.social_event_id == source.id))
    proof.target_post_id = parent.id; db.commit()
    records = today(db, scope)
    record = next(value for value in records if value["source_id"] == source.id)
    assert record["parent_post_id"] == parent.id and record["root_post_id"] == root.id
    assert len([s for s in capture(db, scope).sources if s.source_id == source.id]) == 1
    parent.reply_to_post_id = child.id; db.commit()
    assert all(value["source_id"] != source.id for value in today(db, scope))
    with pytest.raises(ValueError, match="situation_source_not_admitted"):
        capture(db, scope, records=records)


def test_deleted_manual_source_keeps_delivered_snapshot_without_live_original(durable_stack):
    db, scope, setting, memory = durable_stack
    source, post = manual_event(db, scope)
    row = receipt(db, scope, post, capture(db, scope))
    source.invalidation_reason, source.invalidated_at, post.deleted_at = "source_deleted", NOW, NOW
    db.commit(); apply(db, setting, memory)
    assert row.state == "applied"
    item = db.get(MemoryItem, row.applied_item_id)
    reader, request, ranked, _ = readers(db, scope, item)
    hydrated = reader.hydrate(request, reader.revalidate(request, (ranked,)))
    assert hydrated.records and post.body in hydrated.records[0].text


def test_unlisted_visibility_and_reused_reader_still_check_fresh_facts(durable_stack):
    from app.domains.memory.contracts.activity_situation import FinalDeliveredFragment
    from hashlib import sha256
    db, scope, *_ = durable_stack
    source, post = manual_event(db, scope)
    proof = db.scalar(select(SocialEventEvidence).where(SocialEventEvidence.social_event_id == source.id))
    post.visibility = proof.source_visibility_at_event = "unlisted"; db.commit()
    record = next(value for value in today(db, scope) if value["source_id"] == source.id)
    payload = json.loads(json.dumps({"record": record}, default=str))
    text = json.dumps(payload["record"])
    delivery = FinalDeliveredFragment.capture(payload, path="/record", text=text,
        payload_digest=sha256(json.dumps(payload).encode()).hexdigest())
    reader = SituationSources(db)
    arguments = dict(kind="SOCIAL_EVENT", identifier=source.id, delivered=text, path="/record",
        role="background", ordinal=0, delivery=delivery)
    reader.describe(scope, **arguments)
    post.report_hidden_at = NOW; db.commit()
    with pytest.raises(ValueError, match="situation_source_not_admitted"):
        reader.describe(scope, **arguments)


def test_manual_source_batch_has_bounded_reads_and_no_writes(durable_stack):
    from app.runtime.memory import manual_situation_sources
    db, scope, *_ = durable_stack
    source, post = manual_event(db, scope)
    identifiers = [source.id]
    for number in range(12):
        identifiers.append(record_source_reaction_event(db, world_id=scope.world_id,
            actor_world_character_id=PEER, target_world_character_id=scope.subject_world_character_id,
            post=post, root_post=post, event_type="like_added", transition_key=f"batch-{number}"))
    db.commit()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    sql_event.listen(db.bind, "before_cursor_execute", record)
    try:
        validation = MemoryAccessValidation(db, NOW)
        manual_situation_sources.prepare(validation, identifiers)
        for identifier in identifiers:
            manual_situation_sources.basis(db, scope, validation.get(SocialEvent, identifier), validation)
    finally:
        sql_event.remove(db.bind, "before_cursor_execute", record)
    assert statements == ["SELECT"] * 5


def test_manual_situation_fts_vector_and_downstream_guards(durable_stack, index, tmp_path, monkeypatch, deny_external_network):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from time import monotonic
    from memory.test_world_embedding_preparation import Embeddings
    from memory.test_sqlite_vec1 import A
    from app.domains.identity.schemas import WorldCredentialWrite
    from app.domains.identity.service import world_credentials
    from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
    from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, RecallDocumentKind
    from app.domains.memory.contracts.vector_projection import MemoryVectorQuery
    from app.domains.memory.models.embedding import MemoryEmbeddingSetting
    from app.runtime.memory.recall_composition import recall_document_source
    from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, MemoryRecallIndexSettings
    from app.runtime.memory.sqlite_vec1 import VectorCancellation
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
    from app.runtime.memory.vector_projection import MemoryVectorProjection
    from app.runtime.memory.situation_detail import situation_detail
    from app.runtime.memory.composition import memory_consolidation_repository
    # The real result journal must share this test's isolated writable storage,
    # including when the candidate runs as its unchanged non-root image user.
    media_root = tmp_path / "media"
    monkeypatch.setattr("app.config.settings.MEDIA_ROOT", str(media_root))
    db, scope, setting, memory = durable_stack
    world_credentials.save(db, owner_id=scope.owner_id, world_id=scope.world_id,
        world_character_id=scope.subject_world_character_id, purpose="embedding",
        data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-embedding-2", api_key="synthetic-source-index-key"))
    db.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True, provider="google",
        model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1)); db.commit()
    _, post = manual_event(db, scope)
    row = receipt(db, scope, post, capture(db, scope)); apply(db, setting, memory)
    item = db.get(MemoryItem, row.applied_item_id)
    factory = sessionmaker(db.bind)
    source = recall_document_source(factory, now_factory=lambda: NOW, episode_only=True)
    documents = source.documents_for_item_ids((item.id,))
    fts = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "manual-fts"),
        settings=MemoryRecallIndexSettings(generation="memory-episode-v1")); fts.open()
    try:
        fts.replace_memory_items(documents)
        assert [hit.memory_item_id for hit in fts.search(MemoryRecallSearchQuery(
            scope, row.description, (RecallDocumentKind.MEMORY_ITEM,), 5))] == [item.id]
        fake = Embeddings()
        projection = MemoryVectorProjection(factory, index, provider=fake, episode_only=True)
        assert projection.journal.root.is_relative_to(media_root)
        assert asyncio.run(projection.sync_item(item.id)) == "indexed"
        hits = index.search(MemoryVectorQuery(scope, EMBEDDING_PROFILE, A),
            cancellation=VectorCancellation(monotonic()+10)).hits
        assert [hit.memory_item_id for hit in hits] == [item.id] and len(fake.requests) == 1
        reader, request, ranked, _ = readers(db, scope, item)
        selected = reader.revalidate(request, (ranked,))
        assert len(selected) == 1 and reader.hydrate(request, selected).records
        assert situation_detail(db, scope, item.id, NOW).evidence
        hotbrief = memory_consolidation_repository(db)
        assert item.id in {value.id for value in hotbrief.hot_brief_source_items(setting=setting, now=NOW, limit=20)}
        prior = SituationSources(db).describe(scope, kind="MEMORY_ITEM", identifier=item.id,
            delivered=item.summary, path="/prior", role="prior", ordinal=99)
        context = restore_context(db, row)
        assert SituationSources(db).validate(context, prior, now=NOW).state == "available"
        post.report_hidden_at = NOW; db.commit()
        assert reader.hydrate(request, selected).records == ()
        assert source.documents_for_item_ids((item.id,))[item.id] == ()
        assert SituationSources(db).validate(context, prior, now=NOW).state == "forbidden"
        assert item.id not in {value.id for value in hotbrief.hot_brief_source_items(setting=setting, now=NOW, limit=20)}
    finally:
        fts.close()
