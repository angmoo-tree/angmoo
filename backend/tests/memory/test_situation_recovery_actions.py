"""Durable real-reader rechecks, cutoff, owner discard and lease races. No AI."""
from dataclasses import replace
from datetime import timedelta
import pytest
from sqlalchemy import func, select

from memory.test_situation_delivery_recovery import durable_stack, delivered_reply
from memory.test_activity_situation_application import real_source, receipt
from memory.test_activity_situation_contract import NOW, values
from app.domains.memory.models.activity_situation import (
    MemorySituationReceipt, MemorySituationManifest, MemorySituationApplyRun, MemorySituationRecheckAttempt,
)
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryActivationEpoch
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.repository.situation_recovery import discard
from app.domains.memory.repository.situation_apply import apply_page
from app.domains.memory.exceptions import MemoryConflictError
from app.runtime.memory.situation_sources import SituationSources


def blocked(db, scope, post, number):
    manifest, draft, result = values(db, scope, target=post.id, logical=f"activity-{number}", call=f"call-{number}")
    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/target/body", role="core", ordinal=0, target=post.id)
    row = admit(db, manifest=replace(manifest, sources=(source,)), draft=draft, result=result, now=NOW)
    row.state, row.error_code = "blocked", "situation_source_changed_or_forbidden"
    db.commit()
    return row, replace(manifest, sources=(source,)), draft, result


def recheck(db, setting, key="recheck-action-0001", row=None):
    get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
    request = request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key=key,
        expected_version=1, receipt_sequence=row.sequence if row else None,
        expected_receipt_version=row.state_version if row else None, now=NOW)
    db.commit()
    return request


def consume(db, memory, request, page_size=100):
    token = claim_run(db, request.run_id, now=NOW)
    db.commit()
    result = apply_page(db, memory, SituationSources(db), run_id=request.run_id, token=token, now=NOW, page_size=page_size)
    db.commit()
    return result


def test_recheck_preserves_original_result_and_is_idempotent(durable_stack):
    db, scope, setting, memory = durable_stack
    row, *_ = blocked(db, scope, real_source(db, scope), 1)
    first = recheck(db, setting, row=row)
    assert consume(db, memory, first) == 1
    assert row.state == "applied" and row.state_version == 2
    # Reuse the initially accepted body after state/version changed.
    replay = request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key="recheck-action-0001",
        expected_version=1, receipt_sequence=row.sequence, expected_receipt_version=1, now=NOW)
    assert replay.run_id == first.run_id
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 1
    attempt = db.scalar(select(MemorySituationRecheckAttempt))
    assert attempt.outcome == "applied" and attempt.previous_error_code == "situation_source_changed_or_forbidden"
    assert attempt.applied_item_id == row.applied_item_id
    with pytest.raises(MemoryConflictError, match="request_conflict"):
        request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key="recheck-action-0001",
            expected_version=1, receipt_sequence=None, now=NOW)


def test_global_cutoff_pages_do_not_include_later_arrivals(durable_stack):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    rows = [blocked(db, scope, post, index)[0] for index in range(102)]
    request = recheck(db, setting)
    late, *_ = blocked(db, scope, post, "late")
    assert consume(db, memory, request) == 100
    assert db.get(MemorySituationApplyRun, request.run_id).state == "deferred"
    assert consume(db, memory, request) == 2
    assert late.state == "blocked"
    assert all(row.state == "applied" for row in rows)
    assert db.scalar(select(func.count()).select_from(MemorySituationRecheckAttempt)) == 102


def test_individual_recheck_does_not_select_another_receipt_and_busy_is_explicit(durable_stack):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    first, *_ = blocked(db, scope, post, 1)
    second, *_ = blocked(db, scope, post, 2)
    request = recheck(db, setting, row=first)
    with pytest.raises(MemoryConflictError, match="scope_busy"):
        recheck(db, setting, key="global-competing-001")
    db.rollback()
    with pytest.raises(MemoryConflictError, match="scope_busy"):
        request_run(db, setting, trigger="quit", request_key="quit-competing-001", expected_version=1, now=NOW)
    db.rollback()
    token = claim_run(db, request.run_id, now=NOW)
    db.commit()
    with pytest.raises(MemoryConflictError, match="scope_busy"):
        discard(db, setting, sequence=first.sequence, expected_version=1, request_key="discard-busy-0001", now=NOW)
    db.rollback()
    apply_page(db, memory, SituationSources(db), run_id=request.run_id, token=token, now=NOW)
    db.commit()
    assert first.state == "applied" and second.state == "blocked"


def test_recheck_failure_stays_blocked_with_revision_and_specific_reason(durable_stack):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    row, *_ = blocked(db, scope, post, 1)
    post.body = "Edited after the actual input"
    db.commit()
    request = recheck(db, setting, row=row)
    consume(db, memory, request)
    assert row.state == "blocked" and row.error_code == "situation_source_changed" and row.state_version == 2
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert db.scalar(select(MemorySituationRecheckAttempt)).outcome == "rejected"
    assert db.get(MemorySituationApplyRun, request.run_id).blocked_count == 1


def test_recheck_does_not_rewrite_the_completed_original_save(durable_stack):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    row = receipt(db, scope, post)
    original_body = post.body
    post.body = "Changed before the first save"
    get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
    first = request_run(db, setting, trigger="manual", request_key="original-save-001", expected_version=1, now=NOW)
    db.commit()
    consume(db, memory, first)
    old_run = db.get(MemorySituationApplyRun, first.run_id)
    before = (old_run.state, old_run.applied_count, old_run.blocked_count, old_run.cursor, old_run.completed_at)
    assert row.state == "blocked" and old_run.blocked_count == 1
    post.body = original_body; db.commit()
    retry = recheck(db, setting, row=row)
    consume(db, memory, retry)
    assert row.state == "applied"
    db.refresh(old_run)
    assert (old_run.state, old_run.applied_count, old_run.blocked_count, old_run.cursor, old_run.completed_at) == before
    assert db.scalar(select(MemorySituationRecheckAttempt)).previous_run_id == first.run_id


def test_discard_keeps_a_shared_manifest_and_another_receipts_canonical_memory(durable_stack):
    db, scope, setting, memory = durable_stack
    first, manifest, draft, result = blocked(db, scope, real_source(db, scope), 1)
    second = admit(db, manifest=manifest, draft=draft, result=replace(result, logical_activity_id="another-activity"), now=NOW)
    shared_id = first.manifest_id
    get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=NOW)
    saving = request_run(db, setting, trigger="manual", request_key="shared-save-0001", expected_version=1, now=NOW)
    db.commit(); consume(db, memory, saving)
    assert second.state == "applied"
    item = db.get(MemoryItem, second.applied_item_id)
    before = (item.summary, item.version, item.deleted_at, second.content_digest)
    discard(db, setting, sequence=first.sequence, expected_version=1, request_key="discard-shared-001", now=NOW)
    db.commit()
    assert first.manifest_id is None and db.get(MemorySituationManifest, shared_id) is not None
    assert (item.summary, item.version, item.deleted_at, second.content_digest) == before
    assert second.manifest_id == shared_id and second.state == "applied"


def test_discard_off_closed_epoch_cleans_detail_and_prevents_readmission(durable_stack):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    row, manifest, draft, result = blocked(db, scope, post, 1)
    manifest_id, original_digest = row.manifest_id, row.content_digest
    db.get(MemoryScopeSettingModel, setting.id).enabled = False
    db.get(MemoryActivationEpoch, row.activation_epoch).closed_at = NOW
    db.commit()
    first = discard(db, setting, sequence=row.sequence, expected_version=1, request_key="discard-owner-001", now=NOW)
    db.commit()
    db.refresh(row)
    assert row.state == "discarded" and row.state_version == 2 and row.content_digest == original_digest
    assert row.description is None and row.result == {} and row.manifest_id is None
    assert db.get(MemorySituationManifest, manifest_id) is None
    assert db.get(type(post), post.id).body == post.body
    assert discard(db, setting, sequence=row.sequence, expected_version=1, request_key="discard-owner-001", now=NOW).result_code == first.result_code
    assert discard(db, setting, sequence=row.sequence, expected_version=1, request_key="discard-owner-002", now=NOW).result_code == "already_discarded"
    assert admit(db, manifest=manifest, draft=draft, result=result, now=NOW).state == "discarded"
    assert db.get(MemorySituationManifest, manifest_id) is None and row.discarded_at == NOW.replace(tzinfo=None)
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0


def test_stale_version_discard_and_stale_worker_never_apply(durable_stack):
    db, scope, setting, memory = durable_stack
    row, *_ = blocked(db, scope, real_source(db, scope), 1)
    with pytest.raises(MemoryConflictError, match="version_conflict"):
        discard(db, setting, sequence=row.sequence, expected_version=3, request_key="discard-stale-0001", now=NOW)
    db.rollback()
    request = recheck(db, setting, row=row)
    token = claim_run(db, request.run_id, now=NOW, lease_seconds=30)
    db.commit()
    replacement = claim_run(db, request.run_id, now=NOW + timedelta(seconds=31))
    db.commit()
    assert replacement != token
    with pytest.raises(MemoryConflictError, match="fence_lost"):
        apply_page(db, memory, SituationSources(db), run_id=request.run_id, token=token, now=NOW + timedelta(seconds=32))
    db.rollback()
    assert row.state == "blocked" and db.scalar(select(func.count()).select_from(MemoryItem)) == 0


@pytest.mark.parametrize("state", ["pending", "error", "deferred"])
def test_discard_queued_candidate_is_audited_and_never_revived_on_restart(durable_stack, state):
    db, scope, setting, memory = durable_stack
    row, *_ = blocked(db, scope, real_source(db, scope), 1)
    request = recheck(db, setting, row=row)
    run = db.get(MemorySituationApplyRun, request.run_id)
    run.state = state
    db.commit()
    discard(db, setting, sequence=row.sequence, expected_version=1, request_key="discard-queued-001", now=NOW)
    db.commit()
    # An error run resumes only through the same owner's accepted request.
    request_run(db, setting, trigger="manual", work_kind="blocked_recheck", request_key="recheck-action-0001",
        expected_version=1, receipt_sequence=row.sequence, expected_receipt_version=1, now=NOW)
    db.commit()
    db.expire_all()
    assert consume(db, memory, request) == 0
    assert row.state == "discarded" and run.skipped_count == 1 and run.applied_count == 0
    attempt = db.scalar(select(MemorySituationRecheckAttempt))
    assert attempt.outcome == "discarded" and attempt.before_version == 1 and attempt.after_version == 2
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0


def test_closed_activation_recheck_is_rejected_but_discard_is_allowed(durable_stack):
    db, scope, setting, _ = durable_stack
    row, *_ = blocked(db, scope, real_source(db, scope), 1)
    db.get(MemoryActivationEpoch, row.activation_epoch).closed_at = NOW
    db.commit()
    with pytest.raises(MemoryConflictError, match="activation_closed"):
        recheck(db, setting)
    db.rollback()
    discard(db, setting, sequence=row.sequence, expected_version=1, request_key="discard-closed-001", now=NOW)
    db.commit()
    assert row.state == "discarded"


def test_application_and_discard_transactions_roll_back_whole_page(durable_stack):
    from sqlalchemy import event
    db, scope, setting, memory = durable_stack
    row, *_ = blocked(db, scope, real_source(db, scope), 1)
    request = recheck(db, setting, row=row)
    token = claim_run(db, request.run_id, now=NOW)
    db.commit()
    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO memory_situation_recheck_attempts"):
            raise RuntimeError("injected_audit_failure")
    event.listen(db.bind, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected_audit_failure"):
            apply_page(db, memory, SituationSources(db), run_id=request.run_id, token=token, now=NOW)
        db.rollback()
    finally:
        event.remove(db.bind, "before_cursor_execute", fail)
    assert row.state == "blocked" and row.state_version == 1
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0
    run = db.get(MemorySituationApplyRun, request.run_id)
    assert run.cursor == run.applied_count == 0
    run.lease_until = NOW - timedelta(seconds=1)
    db.commit()
    event.listen(db.bind, "before_cursor_execute", fail)
    original_manifest = row.manifest_id
    try:
        with pytest.raises(RuntimeError, match="injected_audit_failure"):
            discard(db, setting, sequence=row.sequence, expected_version=1, request_key="discard-rollback-001", now=NOW)
        db.rollback()
    finally:
        event.remove(db.bind, "before_cursor_execute", fail)
    assert row.state == "blocked" and row.manifest_id == original_manifest and row.description
    assert db.get(MemorySituationManifest, original_manifest) is not None
