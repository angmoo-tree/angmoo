"""Final selection, binding, freshness and bounded read-only capture."""
import copy
import json
from dataclasses import fields, replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select
from chat.today_like_fixture import prepare, f
from app.domains.chat.contracts.evidence_bundle import MAX_EVIDENCE_BUNDLE_CHARS, MAX_EVIDENCE_ITEMS
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.today_sns_activity import TodaySnsSnapshotChangedError, build_today_sns_hash
from app.domains.chat.exceptions import ChatSituationEvidenceError
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.memory.contracts.activity_situation import FinalDeliveredFragment, stable_digest
from app.domains.memory.exceptions import SituationSourceAdmissionError
from app.domains.memory.service.situation_policy import restore
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.relationships.models.social import SocialEventEvidence
from app.domains.relationships.contracts.source_event_evidence import SourceEventBasis
from app.runtime.chat.situation_memory import ChatSituationMemory
from app.runtime.memory.situation_sources import SituationSources

response_session = f.response_session


def freeze(case):
    return ChatSituationMemory(case.db).freeze(case.command, case.bundle, case.payload)


def snapshot_with(snapshot, **changes):
    values = {field.name: getattr(snapshot, field.name) for field in fields(snapshot) if field.name != "snapshot_hash"}
    values.update(changes)
    return type(snapshot)(**values, snapshot_hash=build_today_sns_hash(**values))


def event_bundle(case):
    case.bundle = EvidenceBundleAssembler()._bundle(request_id=case.bundle.request_id,
        request_scope_hash=case.bundle.request_scope_hash, route=case.bundle.route,
        outcome=case.bundle.retrieval_outcome,
        candidates=tuple(i for i in case.bundle.items if i.locator.source_type == "SOCIAL_EVENT"))
    case.payload["frozen_evidence"] = case.bundle.provider_payload()


@pytest.mark.parametrize("field", ["text", "ref", "kind", "occurred_at", "missing", "extra", "path"])
def test_actual_final_payload_cannot_borrow_another_binding(response_session, field):
    case = prepare(response_session)
    items = case.payload["frozen_evidence"]["items"]
    if field == "missing": items.clear()
    elif field == "extra": items.append(copy.deepcopy(items[0]))
    elif field == "path": case.payload["different_path"] = case.payload.pop("frozen_evidence")
    else: items[0][field] = "forged"
    with pytest.raises(ChatSituationEvidenceError, match="situation_today_payload_invalid"):
        freeze(case)


@pytest.mark.parametrize("field", ["source_id", "source_revision", "actor_id", "counterpart_id",
    "source_post_id", "target_post_id", "root_post_id", "parent_post_id", "opaque_reference", "body"])
def test_private_preparation_reference_is_not_permission(response_session, field):
    case = prepare(response_session)
    entry = next(e for e in case.snapshot.entries if e.source_type == "social_event")
    forged = replace(entry, **{field: "f" * 64 if field == "source_revision" else "forged"})
    case.command = replace(case.command, today_sns_snapshot=snapshot_with(case.snapshot,
        entries=tuple(forged if e is entry else e for e in case.snapshot.entries)))
    with pytest.raises((ChatSituationEvidenceError, TodaySnsSnapshotChangedError)):
        freeze(case)


@pytest.mark.parametrize("field", ["owner", "world", "subject", "thread", "request", "hash", "policy"])
def test_scope_and_request_binding_are_private_and_exact(response_session, field):
    case = prepare(response_session)
    if field in {"owner", "world", "subject"}:
        key = {"owner": "owner_id", "world": "world_id", "subject": "subject_world_character_id"}[field]
        with pytest.raises(RetrievalContractError, match="response_workflow_today_scope_mismatch"):
            replace(case.command, today_sns_snapshot=snapshot_with(case.snapshot, **{key: "elsewhere"}))
        return
    elif field == "thread":
        case.command = replace(case.command, request=replace(case.record, thread_id="another-thread"),
            preflight=replace(case.command.preflight, thread_id="another-thread"))
    elif field in {"request", "hash"}:
        case.bundle = EvidenceBundleAssembler().current_context(
            request_id="another-request" if field == "request" else case.record.request_id,
            request_scope_hash="b" * 64 if field == "hash" else case.record.request_scope_hash)
        case.bundle = EvidenceBundleAssembler().with_today_sns(case.bundle, case.snapshot, user_message="today")
        case.payload["frozen_evidence"] = case.bundle.provider_payload()
    else:
        state = copy.deepcopy(case.record.node_state)
        # Use a genuine second scope policy shape, not an invalid serialized policy.
        state["_situation_policy"]["snapshot"]["scope"]["world_id"] = "elsewhere"
        case.command = replace(case.command, request=replace(case.record, node_state=state))
    with pytest.raises(ChatSituationEvidenceError, match="situation_today_scope_invalid"):
        freeze(case)


@pytest.mark.parametrize("mutation", ["content", "private", "hidden", "deleted", "inactive", "block", "invalidated", "duplicate_proof", "parent"])
def test_freeze_rechecks_source_after_preparation(response_session, mutation):
    case = prepare(response_session, nested=mutation == "parent")
    freeze(case)
    if mutation == "content": case.post.body = "Changed after preparation."
    elif mutation == "private": case.post.visibility = "private"
    elif mutation == "hidden": case.post.report_hidden_at = datetime.now(UTC)
    elif mutation == "deleted": case.post.deleted_at = datetime.now(UTC)
    elif mutation == "inactive": case.db.get(f.models.WorldCharacter, "p-requester").status = "left"
    elif mutation == "block":
        case.db.add(WorldCharacterBlock(id="today-block", world_id="p-world",
            blocker_world_character_id="p-responding", blocked_world_character_id="p-requester"))
    elif mutation == "invalidated":
        case.events[0].invalidated_at = datetime.now(UTC)
        case.events[0].invalidation_reason = "manual_exclusion"
    elif mutation == "parent": case.posts[-2].body = "A changed parent."
    else:
        proof = case.db.scalar(select(SocialEventEvidence))
        values = {c.key: getattr(proof, c.key) for c in proof.__table__.columns if c.key != "id"}
        values["evidence_kind"] = "post"
        case.db.add(SocialEventEvidence(id="duplicate-proof", **values))
    case.db.commit()
    with pytest.raises(TodaySnsSnapshotChangedError):
        freeze(case)
    assert all(e.retrieval_status == "audit_only" for e in case.events)


@pytest.mark.parametrize("count", [1, 12])
def test_capture_is_batched_bounded_read_only_and_keeps_pending_writes(response_session, count, record_property):
    case = prepare(response_session, count=count)
    event_bundle(case)
    assert len(case.bundle.items) == count
    db = case.db
    db.autoflush = True
    pending = f.models.Post(id="unrelated-pending", author_name="fixture", title="Caller", body="Owns write.")
    db.add(pending)
    sql, flushes, commits = [], [], []
    def statement(_connection, _cursor, text, *_): sql.append(text)
    def flushing(*_): flushes.append(1)
    def committing(*_): commits.append(1)
    event.listen(db.bind, "before_cursor_execute", statement)
    event.listen(db, "before_flush", flushing)
    event.listen(db, "after_commit", committing)
    try:
        result = freeze(case)
        assert len([s for s in result.sources if s.source_type == "SOCIAL_EVENT"]) == count
        assert all(s.lstrip().upper().startswith("SELECT") for s in sql)
        assert not flushes and not commits and pending in db.new
        assert not db.connection().connection.driver_connection.in_transaction
        proof_reads = [s for s in sql if "FROM social_event_evidence " in s or "FROM social_event_evidence\n" in s]
        # One shared proof batch plus the existing reader's per-event source
        # counterpart resolution. Neither scans unrelated event history.
        assert len(proof_reads) == count + 1
        assert sum(" IN (" in s for s in proof_reads) == 1
        assert len(sql) <= 25 * count + 30
        record_property("selected_events", count)
        record_property("capture_selects", len(sql))
        record_property("evidence_batch_queries", 1)
        record_property("existing_reader_evidence_queries", count)
        record_property("new_dml_flushes_commits", 0)
    finally:
        event.remove(db.bind, "before_cursor_execute", statement)
        event.remove(db, "before_flush", flushing)
        event.remove(db, "after_commit", committing)
        db.rollback()


def test_equal_prose_different_events_and_limits_preserve_atomic_identity(response_session):
    case = prepare(response_session, count=12)
    items = case.bundle.items
    assert len({i.text for i in items}) == 1 and len(items) == 12
    assert len({i.locator.source_id for i in items}) == 12
    assert EvidenceBundleAssembler._dedupe_sort_truncate(items + items) == items
    # Exact text (including Unicode), never normalized/case-folded into another event.
    assert "🙂" in items[0].text
    candidates = tuple(replace(i, text=(i.text + "한 é🙂 " * 1000)[:2000]) for i in items)
    limited = EvidenceBundleAssembler._dedupe_sort_truncate(candidates)
    assert len(limited) == 4 and len(limited) <= MAX_EVIDENCE_ITEMS
    assert sum(len(i.text) for i in limited) == MAX_EVIDENCE_BUNDLE_CHARS
    assert all(i in candidates for i in limited)
    wire = json.dumps(case.bundle.provider_payload(), ensure_ascii=False)
    inspector = json.dumps(case.bundle.inspector_snapshot())
    for entry in case.snapshot.entries:
        assert entry.source_id not in wire
    assert "parent_post_id" not in inspector and "manual_event_reference" not in inspector
    assert "parent_post_id" not in json.dumps(case.snapshot.entries[0].provider_payload(include_content=True))
    assert all(len(i.text) <= 2000 for i in items)


def test_reference_alone_or_legacy_proof_does_not_admit_audit_only_source(response_session):
    case = prepare(response_session)
    item = case.bundle.items[0]
    entry = EvidenceBundleAssembler.today_event_entry(item, case.snapshot)
    reference = SourceEventBasis(entry.source_id, entry.event_type, entry.actor_id, entry.counterpart_id,
        entry.source_post_id, entry.target_post_id, entry.root_post_id, entry.parent_post_id, entry.source_revision)
    source = SituationSources(case.db)
    with pytest.raises(SituationSourceAdmissionError):
        source.describe(case.scope, kind="SOCIAL_EVENT", identifier=reference.event_id,
            delivered=item.text, path="/text", role="background", ordinal=0, manual_event_reference=reference)
    with pytest.raises(SituationSourceAdmissionError):
        source.describe(case.scope, kind="SOCIAL_EVENT", identifier=reference.event_id,
            delivered=item.text, path="/text", role="background", ordinal=0,
            delivery=FinalDeliveredFragment.capture({"text": item.text}, path="/text",
                text=item.text, payload_digest=stable_digest({"text": item.text})))
    assert restore(case.command.request.node_state["_situation_policy"]).scope == case.scope


@pytest.mark.parametrize("delete", [False, True])
def test_fresh_capture_never_overwrites_or_flushes_uncommitted_source_edits(response_session, delete):
    case = prepare(response_session)
    if delete:
        case.db.delete(case.post)
    else:
        case.post.body = "Uncommitted caller edit."
    with pytest.raises(ChatSituationEvidenceError, match="situation_today_pending_changes"):
        freeze(case)
    if delete:
        assert case.post in case.db.deleted
    else:
        assert case.post in case.db.dirty and case.post.body == "Uncommitted caller edit."
