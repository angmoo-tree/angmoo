"""Real SQLite sources, canonical application and reads; all providers are absent."""
from dataclasses import replace
from datetime import timedelta
from sqlalchemy import select

from memory.test_activity_situation_contract import stack, values, NOW
from app.domains.social.models.posts import Post
from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, stable_digest
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.repository.situation_apply import apply_page
from app.domains.memory.repository.episode_privacy import currently_accessible
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.recall import SqlAlchemyMemoryRecallDocumentSource
from app.domains.memory.models.items import MemoryItem
from app.runtime.memory.situation_application_sources import PreparedSituationSources
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.source_composition import source_evidence_reader


def real_source(session, scope):
    post = Post(id="situation-post", world_id=scope.world_id, author_world_character_id=scope.subject_world_character_id,
        author_character_id="consolidation-subject-character", author_name="subject", title="Daily note", body="A quiet ordinary afternoon.", created_at=NOW)
    session.add(post)
    session.commit()
    return post


def receipt(session, scope, post):
    manifest, draft, result = values(session, scope, target=post.id)
    source = PreparedSituationSources(session).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/target/body", role="core", ordinal=0, target=post.id)
    manifest = replace(manifest, sources=(source,))
    return admit(session, manifest=manifest, draft=draft, result=result, now=NOW)


def apply(session, setting, memory):
    get_or_create_settings(session, setting.id, timezone="Asia/Seoul", now=NOW)
    request = request_run(session, setting, trigger="manual", request_key="save-situation-0001", expected_version=1, now=NOW)
    token = claim_run(session, request.run_id, now=NOW)
    session.commit()
    from app.domains.memory.models.activity_situation import MemorySituationApplyRun
    while token:
        apply_page(session, memory, PreparedSituationSources(session), run_id=request.run_id, token=token, now=NOW)
        session.commit()
        if session.get(MemorySituationApplyRun, request.run_id).state == "completed":
            break
        token = claim_run(session, request.run_id, now=NOW)
        session.commit()


def test_deleted_original_preserves_canonical_summary_and_never_hydrates_body(stack):
    session, scope, setting, memory = stack
    post = real_source(session, scope)
    row = receipt(session, scope, post)
    post.deleted_at = NOW + timedelta(seconds=1)
    session.commit()
    apply(session, setting, memory)
    assert row.state == "applied"
    item = session.get(MemoryItem, row.applied_item_id)
    assert currently_accessible(session, source_evidence_reader(session), scope, item, NOW)
    packet, = SqlAlchemyEpisodePackets(session, detail_reader=RuntimeEpisodeDetailReader(session)).read(scope=scope, item_ids=(item.id,), now=NOW)
    assert packet.representation == "activity_situation_v1"
    assert packet.units[0].sources[0].status == "missing"
    assert packet.units[0].sources[0].text is None
    documents = SqlAlchemyMemoryRecallDocumentSource._documents_for_item(session=session,
        reader=source_evidence_reader(session), item=item, evidences=[], now=NOW, episode_only=False)
    assert len(documents) == 1 and documents[0].text == row.description
    assert post.body not in documents[0].text


def test_changed_original_blocks_application_and_unknown_policy_fails_closed(stack):
    session, scope, setting, memory = stack
    post = real_source(session, scope)
    row = receipt(session, scope, post)
    post.body = "Edited after delivery"
    session.commit()
    apply(session, setting, memory)
    assert row.state == "blocked"
    assert session.scalar(select(MemoryItem.id)) is None


def test_current_body_ranges_and_summary_only_documents(stack):
    session, scope, setting, memory = stack
    post = real_source(session, scope)
    row = receipt(session, scope, post)
    apply(session, setting, memory)
    item = session.get(MemoryItem, row.applied_item_id)
    packet, = SqlAlchemyEpisodePackets(session, detail_reader=RuntimeEpisodeDetailReader(session)).read(scope=scope, item_ids=(item.id,), now=NOW)
    assert packet.units[0].sources[0].text == post.body
    from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo
    session.get(MemoryActivitySituationInfo, item.id).policy_version = "unknown-policy"
    session.flush()
    assert not currently_accessible(session, source_evidence_reader(session), scope, item, NOW)


def test_correction_after_source_deletion_keeps_privacy_metadata_after_parent_retention(stack):
    from app.domains.memory.service.items import MemoryWriteLifecycleService
    from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo
    session, scope, setting, memory = stack
    post = real_source(session, scope)
    row = receipt(session, scope, post)
    apply(session, setting, memory)
    parent_id = row.applied_item_id
    post.deleted_at = NOW
    session.commit()
    corrected = MemoryWriteLifecycleService(memory, source_evidence_reader(session)).correct_summary(
        scope=scope, old_item_id=parent_id, expected_item_version=1, expected_scope_version=setting.version,
        summary="오후에 안부를 나눴다.", idempotency_key="situation-correction-001", now=NOW)
    session.commit()
    from sqlalchemy import delete
    from app.domains.memory.models.items import MemoryItemEvidence
    session.execute(delete(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id == parent_id))
    session.delete(session.get(MemoryItem, parent_id))
    session.commit()
    item = session.get(MemoryItem, corrected.item.id)
    assert session.get(MemoryActivitySituationInfo, item.id) is not None
    assert currently_accessible(session, source_evidence_reader(session), scope, item, NOW)
    packet, = SqlAlchemyEpisodePackets(session, detail_reader=RuntimeEpisodeDetailReader(session)).read(scope=scope, item_ids=(item.id,), now=NOW)
    assert packet.units[0].sources[0].text is None
    assert row.state == "applied"
