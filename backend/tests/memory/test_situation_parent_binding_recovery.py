"""Historic SNS parent repair through the real receipt/UoW and current source ports."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import pytest
from sqlalchemy import select, func
from memory.test_situation_delivery_recovery import durable_stack
from memory.test_activity_situation_application import real_source, apply
from memory.test_activity_situation_contract import values, NOW
from memory.test_situation_recovery_actions import recheck, consume
from app.domains.social.models.posts import Post
from app.domains.memory.contracts.activity_situation import FinalDeliveredFragment, CommittedEffect, CommittedActivityResult, DeliveredSourceEntry, SituationDraft, stable_digest
from app.domains.memory.models.activity_situation import MemorySituationManifest, MemorySituationApplyRun
from app.domains.memory.models.situation_source_binding import MemorySituationSourceBinding
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.memory.repository.episode_privacy import currently_accessible
from app.runtime.memory.situation_sources import SituationSources
from memory.projection_fixture import index


def historic(db, scope, *, parent_text=None, path="/context/today_activity/records/0/parent_body", child_ranges=True, missing=False):
    core = real_source(db, scope)
    parent = Post(id="actual-parent", world_id=scope.world_id, author_world_character_id=scope.subject_world_character_id,
        author_character_id="consolidation-subject-character", author_name="subject", title="약속", body="내일 시계탑에서 파란 책을 가져올게요.", created_at=NOW - timedelta(minutes=2))
    child = Post(id="observed-child", world_id=scope.world_id, author_world_character_id="consolidation-counterpart",
        author_character_id="consolidation-counterpart-character", author_name="counterpart", reply_to_post_id=parent.id,
        title="답글", body="좋아요. 따뜻한 차를 가져갈게요.", created_at=NOW - timedelta(minutes=1))
    db.add_all([parent, child]); db.commit()
    text = parent.body if parent_text is None else parent_text
    records = [{"body": child.body, "parent_body": text}]
    if "/records/1/" in path:
        records.append({"body": "different input", "parent_body": text})
    payload = {"selected": {"body": core.body}, "context": {"today_activity": {"records": records}}}
    digest = stable_digest(payload); reader = SituationSources(db)
    normal = reader.describe(scope, kind="POST", identifier=core.id, delivered=core.body, path="/selected/body", role="core", ordinal=0, target=core.id,
        delivery=FinalDeliveredFragment.capture(payload, path="/selected/body", text=core.body, payload_digest=digest))
    background = reader.describe(scope, kind="REPLY", identifier=child.id, delivered=child.body, path="/context/today_activity/records/0/body", role="background", ordinal=1,
        delivery=FinalDeliveredFragment.capture(payload, path="/context/today_activity/records/0/body", text=child.body, payload_digest=digest))
    if not child_ranges: background = replace(background, ranges=(), delivered_ranges=())
    wrong = reader.describe(scope, kind="REPLY", identifier=child.id, delivered=text, path=path, role="background", ordinal=2,
        delivery=FinalDeliveredFragment.capture(payload, path=path, text=text, payload_digest=digest))
    output = reader.describe(scope, kind="POST", identifier=core.id, delivered=core.body, path="/committed_result/body", role="committed_result", ordinal=3, target=core.id)
    manifest, draft, result = values(db, scope, target=core.id, call="sns:historic:feed:1")
    manifest = replace(manifest, sources=(normal, background, wrong), version=2, payload_digest=digest)
    result = replace(result, planned_effects=("post",), effects=(CommittedEffect("post", "POST", core.id, "succeeded"),), result_sources=(output,))
    if missing: draft = replace(draft, description=None, status="missing")
    row = admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    if not missing: row.state, row.error_code = "blocked", "situation_source_changed_or_forbidden"
    db.commit()
    return row, parent, child


def count(db): return db.scalar(select(func.count()).select_from(MemorySituationSourceBinding))


def test_recheck_repairs_only_view_and_reuses_fixed_binding(durable_stack):
    db, scope, setting, memory = durable_stack
    row, parent, child = historic(db, scope)
    frozen = db.get(MemorySituationManifest, row.manifest_id).payload.copy()
    admission = row.content_digest
    request = recheck(db, setting, row=row); assert consume(db, memory, request) == 1
    assert row.state == "applied", row.error_code
    assert count(db) == 1
    context = restore_context(db, row)
    assert context.manifest.sources[2].source_id == child.id
    assert context.sources[2].source_id == parent.id
    assert context.proof_for(context.sources[2]).origin == "situation_source_binding"
    assert context.sources[2].delivered_digest == sha256(parent.body.encode()).hexdigest()
    assert db.get(MemorySituationManifest, row.manifest_id).payload == frozen
    assert row.content_digest == admission
    assert currently_accessible(db, SituationSources(db), scope, db.get(MemoryItem, row.applied_item_id), NOW)
    from app.domains.memory.repository.situation_runs import request_run, claim_run
    replay = request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key="recheck-action-0001",
        expected_version=1, receipt_sequence=row.sequence, expected_receipt_version=1, now=NOW)
    assert replay.run_id == request.run_id
    assert claim_run(db, request.run_id, now=NOW) is None
    assert count(db) == 1


@pytest.mark.parametrize("change", ["child-body", "child-parent", "parent-body", "parent-private", "parent-hidden", "parent-deleted", "child-future"])
def test_changed_canonical_facts_do_not_leave_binding(durable_stack, change):
    db, scope, setting, memory = durable_stack
    row, parent, child = historic(db, scope)
    if change == "child-body": child.body += " 수정"
    elif change == "child-parent": child.reply_to_post_id = "situation-post"
    elif change == "parent-body": parent.body += " 수정"
    elif change == "parent-private": parent.visibility = "private"
    elif change == "parent-hidden": parent.report_hidden_at = NOW
    elif change == "parent-deleted": parent.deleted_at = NOW
    else: child.created_at = NOW + timedelta(seconds=1)
    db.commit(); consume(db, memory, recheck(db, setting, row=row))
    assert row.state == "blocked" and row.applied_item_id is None
    assert count(db) == 0


@pytest.mark.parametrize("case", ["partial-parent", "wrong-record", "child-no-range", "missing-description"])
def test_no_guessing_from_partial_or_other_input(durable_stack, case):
    db, scope, setting, memory = durable_stack
    args = {"parent_text": "내일 시계탑"} if case == "partial-parent" else {"path": "/context/today_activity/records/1/parent_body"} if case == "wrong-record" else {"child_ranges": False} if case == "child-no-range" else {"missing": True}
    row, *_ = historic(db, scope, **args)
    consume(db, memory, recheck(db, setting, row=row))
    assert row.state == "blocked" and count(db) == 0


@pytest.mark.parametrize("change", ["body", "delete", "hide", "reparent", "child-body", "child-delete", "child-private", "child-hide"])
def test_saved_binding_remains_subject_to_current_access(durable_stack, change):
    db, scope, setting, memory = durable_stack
    row, parent, child = historic(db, scope)
    consume(db, memory, recheck(db, setting, row=row)); assert row.state == "applied"
    if change == "body": parent.body += " changed"
    elif change == "delete": parent.deleted_at = NOW
    elif change == "hide": parent.report_hidden_at = NOW
    elif change == "reparent": child.reply_to_post_id = "situation-post"
    elif change == "child-body": child.body += " changed"
    elif change == "child-delete": child.deleted_at = NOW
    elif change == "child-private": child.visibility = "private"
    else: child.report_hidden_at = NOW
    db.commit()
    assert not currently_accessible(db, SituationSources(db), scope, db.get(MemoryItem, row.applied_item_id), NOW)
    assert count(db) == 1  # Fixed evidence is never rewritten on a read.


def test_old_revision_never_infers_parent_binding(durable_stack):
    db, scope, setting, memory = durable_stack
    row, *_ = historic(db, scope)
    request = recheck(db, setting, row=row)
    run = db.get(MemorySituationApplyRun, request.run_id)
    run.settings_snapshot = {**run.settings_snapshot, "validation_revision": "situation-validation.v2"}; db.commit()
    consume(db, memory, request)
    assert row.state == "blocked" and count(db) == 0


def test_other_source_failure_rolls_back_new_binding(durable_stack):
    db, scope, setting, memory = durable_stack
    row, *_ = historic(db, scope)
    db.get(Post, "situation-post").body += " changed after capture"; db.commit()
    consume(db, memory, recheck(db, setting, row=row))
    assert row.state == "blocked" and count(db) == 0


def test_outer_uow_failure_rolls_back_binding_memory_and_index(durable_stack, monkeypatch):
    from app.domains.memory.repository import situation_apply
    db, scope, setting, memory = durable_stack
    row, *_ = historic(db, scope)
    request = recheck(db, setting, row=row)
    def fail(*args, **kwargs): raise RuntimeError("injected_content_registration_failure")
    monkeypatch.setattr(situation_apply, "register_content", fail)
    with pytest.raises(RuntimeError, match="injected_content_registration_failure"):
        consume(db, memory, request)
    db.rollback()
    assert count(db) == 0 and db.scalar(select(func.count()).select_from(MemoryItem)) == 0
    db.refresh(row); assert row.state == "blocked" and row.applied_item_id is None


@pytest.mark.parametrize("trigger", ["manual", "scheduled", "quit"])
def test_pending_consumers_share_resolution_without_touching_blocked(durable_stack, trigger):
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run
    db, scope, setting, memory = durable_stack
    row, *_ = historic(db, scope)
    row.state, row.error_code = "pending", None
    config = get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
    config.daily_enabled, config.next_due_at, config.shutdown_apply_enabled = True, NOW, True
    db.commit()
    request = request_run(db, setting, trigger=trigger, request_key=f"parent-save-{trigger}-0001", expected_version=1, now=NOW)
    db.commit(); consume(db, memory, request)
    assert row.state == "applied" and count(db) == 1


def test_unknown_revision_stops_without_guessing(durable_stack):
    from app.domains.memory.repository.situation_runs import request_run
    from app.domains.memory.exceptions import MemoryConflictError
    db, scope, setting, memory = durable_stack
    row, *_ = historic(db, scope)
    request = recheck(db, setting, row=row)
    run = db.get(MemorySituationApplyRun, request.run_id)
    run.settings_snapshot = {**run.settings_snapshot, "validation_revision": "unknown.v99"}; db.commit()
    assert consume(db, memory, request) == 0
    assert run.error_code == "situation_validation_revision_unsupported" and count(db) == 0
    with pytest.raises(MemoryConflictError, match="revision_unsupported"):
        request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key="recheck-action-0001",
            expected_version=1, receipt_sequence=row.sequence, expected_receipt_version=row.state_version, now=NOW)
    fresh = request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key="unknown-retry-0001",
        expected_version=1, receipt_sequence=row.sequence, expected_receipt_version=row.state_version, now=NOW)
    assert fresh.run_id != run.id
    assert db.get(MemorySituationApplyRun, fresh.run_id).settings_snapshot["validation_revision"] == "situation-validation.v6"


def test_shared_binding_discard_and_owner_cleanup_preserve_posts(durable_stack):
    from app.domains.memory.models.embedding import MemoryVectorEligibility
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run
    from app.domains.memory.repository.situation_recovery import discard
    from app.runtime.memory_privacy import scrub_memory_data
    from app.domains.memory.models.activity_situation import MemorySituationReceipt
    db, scope, setting, memory = durable_stack
    first, parent, child = historic(db, scope)
    context = restore_context(db, first)
    draft = SituationDraft(first.target_key, first.description, first.description_status)
    raw = dict(first.result); raw.pop('_admission', None)
    committed = CommittedActivityResult('shared-parent-another-activity', raw['lane'], raw['target_key'], tuple(raw['planned_effects']),
        tuple(CommittedEffect(**value) for value in raw['effects']), raw['planned_output_digest'], raw['final_output_digest'], NOW,
        counterpart_id=raw.get('counterpart_id'), thought_reference=raw.get('thought_reference'),
        result_sources=tuple(DeliveredSourceEntry.from_dict(value) for value in raw['result_sources']))
    second = admit(db, manifest=context.manifest, draft=draft,
        result=committed, now=NOW)
    shared = first.manifest_id
    config = get_or_create_settings(db, setting.id, timezone='Asia/Seoul', now=NOW)
    request = request_run(db, setting, trigger='manual', request_key='shared-parent-save-0001', expected_version=config.version, now=NOW)
    db.commit(); consume(db, memory, request)
    assert second.state == 'applied' and first.state == 'blocked' and count(db) == 1
    eligible = db.get(MemoryVectorEligibility, second.applied_item_id)
    assert eligible is not None and eligible.item_version == 1
    assert db.scalar(select(func.count()).select_from(MemoryVectorEligibility)) == 1
    discard(db, setting, sequence=first.sequence, expected_version=first.state_version, request_key='discard-shared-parent-0001', now=NOW)
    db.commit()
    assert count(db) == 1 and db.get(MemorySituationManifest, shared) is not None
    assert second.state == 'applied' and currently_accessible(db, SituationSources(db), scope, db.get(MemoryItem, second.applied_item_id), NOW)
    scrub_memory_data(db, owner_id=scope.owner_id, character_id='consolidation-subject-character')
    db.commit(); db.expire_all()
    assert count(db) == 0 and db.get(MemorySituationManifest, shared) is None
    assert db.get(Post, parent.id) is not None and db.get(Post, child.id) is not None
    assert db.scalar(select(func.count()).select_from(MemoryVectorEligibility)) == 0
    assert db.connection().exec_driver_sql('PRAGMA foreign_key_check').all() == []


def test_repaired_memory_incremental_fts_embedding_recall_and_current_guard(durable_stack, index, tmp_path, deny_external_network):
    import asyncio
    from sqlalchemy.orm import sessionmaker
    from memory.test_activity_situation_recall import readers
    from memory.test_world_embedding_preparation import Embeddings
    from app.domains.identity.schemas import WorldCredentialWrite
    from app.domains.identity.service import world_credentials
    from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
    from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, RecallDocumentKind
    from app.domains.memory.models.embedding import MemoryEmbeddingSetting, MemoryVectorEligibility
    from app.runtime.memory.recall_composition import recall_document_source
    from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, MemoryRecallIndexSettings
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
    from app.runtime.memory.vector_projection import MemoryVectorProjection
    db, scope, setting, memory = durable_stack
    world_credentials.save(db, owner_id=scope.owner_id, world_id=scope.world_id,
        world_character_id=scope.subject_world_character_id, purpose="embedding",
        data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-embedding-2", api_key="synthetic-parent-index-key"))
    db.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True, provider="google", model="gemini-embedding-2",
        profile=EMBEDDING_PROFILE, version=1))
    db.commit()
    row, parent, _ = historic(db, scope)
    consume(db, memory, recheck(db, setting, row=row))
    item = db.get(MemoryItem, row.applied_item_id)
    eligible = db.get(MemoryVectorEligibility, item.id)
    assert eligible.registration_revision == "memory-vector.incremental.v2"
    factory = sessionmaker(db.bind)
    source = recall_document_source(factory, now_factory=lambda: NOW, episode_only=True)
    documents = source.documents_for_item_ids((item.id,))
    assert len(documents[item.id]) == 1 and documents[item.id][0].text == row.description
    fts = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "parent-fts"),
        settings=MemoryRecallIndexSettings(generation="memory-episode-v1"))
    fts.open()
    try:
        fts.replace_memory_items(documents)
        query = MemoryRecallSearchQuery(scope, row.description, (RecallDocumentKind.MEMORY_ITEM,), 5)
        assert [hit.memory_item_id for hit in fts.search(query)] == [item.id]
        fake = Embeddings()
        projection = MemoryVectorProjection(factory, index, provider=fake, episode_only=True)
        assert asyncio.run(projection.sync_item(item.id)) == "indexed"
        assert asyncio.run(projection.sync_item(item.id)) == "current"
        assert len(fake.requests) == 1 and index.identity(f"memory-item:{item.id}") is not None
        reader, request, ranked, _ = readers(db, scope, item)
        selected = reader.revalidate(request, (ranked,))
        assert len(selected) == 1 and reader.hydrate(request, selected).records
        parent.body += " altered after search"
        db.commit()
        assert reader.hydrate(request, selected).records == ()
        assert source.documents_for_item_ids((item.id,))[item.id] == ()
        assert asyncio.run(projection.sync_item(item.id)) == "source_unavailable"
        assert index.identity(f"memory-item:{item.id}") is None
        assert count(db) == 1 and db.get(MemoryVectorEligibility, item.id) is not None
    finally:
        fts.close()
