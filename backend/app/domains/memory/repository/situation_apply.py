"""Canonical application in one short caller-owned transaction, with no AI I/O."""
from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, update

from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import SITUATION_POLICY, VALIDATION_REVISION
from app.domains.memory.contracts.situation_validation import SituationSourceAccess, SituationSourceValidator
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.memory.contracts.provenance import MemoryKindV1, MemoryItemStatus
from app.domains.memory.exceptions import MemoryCapacityReached, MemoryConflictError, MemoryScopeError
from app.domains.memory.models.batch import MemoryActivationEpoch
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import (
    MemorySituationManifest, MemorySituationReceipt, MemoryActivitySituationInfo, MemoryActivitySituationSource,
    MemorySituationProcessingSetting,
    MemorySituationRecheckAttempt,
)
from app.domains.memory.repository.capacity import stored_count, STORAGE_LIMIT
from app.domains.memory.repository.situation_runs import require_run_fence
from app.domains.memory.repository.vector_eligibility import register_content


def apply_page(session, memory, validator: SituationSourceValidator, *, run_id, token, now, page_size=100):
    if not 1 <= page_size <= 100:
        raise ValueError("situation_page_size_invalid")
    run = require_run_fence(session, run_id, token, now)
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == run.scope_setting_id).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    run = require_run_fence(session, run_id, token, now)
    pending = (
        MemorySituationReceipt.scope_setting_id == run.scope_setting_id,
        MemorySituationReceipt.sequence > run.cursor,
        MemorySituationReceipt.sequence <= run.cutoff_sequence,
        MemorySituationReceipt.state == ("blocked" if run.work_kind == "blocked_recheck" else "pending"),
    )
    if run.settings_snapshot.get("receipt_sequence") is not None:
        pending += (MemorySituationReceipt.sequence == run.settings_snapshot["receipt_sequence"],)
    cutoff_at = run.settings_snapshot.get("cutoff_at")
    if cutoff_at is not None:
        # Sequence bounds protect a frozen run from later arrivals; this time
        # bound also excludes captures after a missed daily due time.
        pending += (MemorySituationReceipt.captured_at <= utc_instant(datetime.fromisoformat(cutoff_at)),)
    rows = list(session.scalars(select(MemorySituationReceipt).where(*pending)
        .order_by(MemorySituationReceipt.sequence).limit(page_size)))
    available_slots = None
    changed_settings = set()
    def processed(receipt, before_version, previous):
        receipt.state_version += 1
        receipt.run_id, run.cursor = run.id, receipt.sequence
        if run.work_kind == "blocked_recheck":
            session.add(MemorySituationRecheckAttempt(run_id=run.id, receipt_sequence=receipt.sequence,
                validation_revision=VALIDATION_REVISION,
                outcome="applied" if receipt.state == "applied" else "rejected",
                reason=receipt.error_code, previous_run_id=previous[0], previous_state=previous[1],
                previous_error_code=previous[2], applied_item_id=receipt.applied_item_id,
                before_version=before_version, after_version=receipt.state_version, created_at=now))
    for receipt in rows:
        before_version = receipt.state_version
        previous = receipt.run_id, receipt.state, receipt.error_code
        if receipt.applied_item_id is not None or session.scalar(select(MemoryActivitySituationInfo.memory_item_id).where(
                MemoryActivitySituationInfo.receipt_sequence == receipt.sequence).limit(1)) is not None:
            receipt.state, receipt.error_code = "blocked", "situation_already_applied"
            run.blocked_count += 1
            processed(receipt, before_version, previous)
            continue
        try:
            manifest = restore_context(session, receipt)
            result_sources = manifest.result_sources
        except (AttributeError, ValueError, TypeError, KeyError) as exc:
            code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("situation_") else "situation_manifest_invalid"
            receipt.state, receipt.error_code = "blocked", code[:80]
            processed(receipt, before_version, previous)
            run.blocked_count += 1
            continue
        snapshot = manifest.snapshot
        setting = memory.get_scope_setting(snapshot.scope)
        epoch = session.get(MemoryActivationEpoch, receipt.activation_epoch, populate_existing=True)
        if (setting is None or not setting.enabled or setting.version != receipt.scope_version
            or epoch is None or epoch.closed_at is not None or epoch.scope_setting_id != receipt.scope_setting_id):
            receipt.state, receipt.error_code = ("blocked" if run.work_kind == "blocked_recheck" else "skipped"), "situation_activation_closed"
            if run.work_kind == "blocked_recheck":
                run.blocked_count += 1
            else:
                run.skipped_count += 1
        elif receipt.policy_version != SITUATION_POLICY or receipt.description_status != "valid" or not receipt.description:
            receipt.state, receipt.error_code = "blocked", "situation_policy_or_description_invalid"
            run.blocked_count += 1
        else:
            try:
                memory.validate_scope(snapshot.scope)
            except MemoryScopeError:
                receipt.state, receipt.error_code = "skipped", "situation_scope_removed"
                processed(receipt, before_version, previous)
                run.skipped_count += 1
                continue
            access = [(source, validator.validate(manifest, source, now=now)) for source in (*manifest.sources, *result_sources)]
            legacy_deleted = run.work_kind == "blocked_recheck" and manifest.version == 1 and any(
                value.state == "deleted" and source.role == "core" for source, value in access)
            if (not access or any(value.state not in {"available", "deleted"}
                or (value.state == "deleted" and source.role == "prior") for source, value in access) or legacy_deleted):
                receipt.state, receipt.error_code = "blocked", "situation_legacy_source_unavailable" if legacy_deleted else next((value.reason for source, value in access
                    if value.reason and value.state not in {"available", "deleted"}), "situation_source_changed_or_forbidden")
                run.blocked_count += 1
            else:
                # The scope row is already write-locked for this page. Count
                # holdings once, then reserve each slot under that same lock.
                if available_slots is None:
                    available_slots = STORAGE_LIMIT - stored_count(session, setting.scope, now=now)
                if available_slots <= 0:
                    raise MemoryCapacityReached()
                available_slots -= 1
                item = MemoryItem(id=str(uuid4()), owner_id=setting.scope.owner_id, world_id=setting.scope.world_id,
                    subject_world_character_id=setting.scope.subject_world_character_id,
                    counterpart_world_character_id=receipt.result.get("counterpart_id"), thread_id=manifest.private_thread_id,
                    memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT.value, summary=receipt.description, status=MemoryItemStatus.ACTIVE.value,
                    confidence=1.0, salience=0.5, version=1,
                    valid_from=receipt.occurred_at, valid_until=now + timedelta(days=setting.retention_days),
                    created_at=now, updated_at=now)
                session.add(item)
                session.flush()
                session.add(MemoryActivitySituationInfo(memory_item_id=item.id, receipt_sequence=receipt.sequence,
                    policy_version=SITUATION_POLICY, locale=snapshot.memory_search_locale,
                    occurred_at=receipt.occurred_at, thought_reference=receipt.result.get("thought_reference")))
                evidence_ids = {}
                for source, value in access:
                    # All inputs constrain privacy, but only this target's core and
                    # successful result become visible provenance for this item.
                    if source.role not in {"core", "committed_result", "thought"} or source.target_key not in {None, receipt.target_key}:
                        continue
                    evidence_id = None
                    if value.evidence is not None:
                        identity = source.source_type, source.source_id, source.source_digest
                        evidence_id = evidence_ids.get(identity)
                        if evidence_id is None:
                            evidence = memory._new_evidence(item.id, value.evidence)
                            session.add(evidence)
                            session.flush()
                            evidence_id = evidence.id
                            evidence_ids[identity] = evidence_id
                    session.add(MemoryActivitySituationSource(memory_item_id=item.id, ordinal=source.ordinal,
                        evidence_id=evidence_id, source=asdict(source), state=value.state))
                receipt.state, receipt.applied_item_id, receipt.applied_at, receipt.error_code = "applied", item.id, now, None
                register_content(session, item, now=now)
                changed_settings.add(setting.id)
                run.applied_count += 1
        processed(receipt, before_version, previous)
    for setting_id in changed_settings:
        memory._invalidate_hot_briefs(setting_id, now=now)
    session.flush()
    more = session.scalar(select(MemorySituationReceipt.sequence).where(
        *pending, MemorySituationReceipt.sequence > run.cursor).limit(1))
    # Yield after every bounded page. A new claimant uses a new token, so a late
    # worker cannot advance a page under the previous lease.
    run.lease_token = run.lease_until = None
    run.state = "deferred" if more else "completed"
    if not more:
        run.completed_at = now
        config = session.get(MemorySituationProcessingSetting, run.scope_setting_id)
        if config is not None and run.applied_count:
            config.last_applied_at = now
    session.flush()
    return len(rows)
