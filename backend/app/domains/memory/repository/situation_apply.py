"""Canonical application in one short caller-owned transaction, with no AI I/O."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4
from sqlalchemy import select, update

from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, DeliveredSourceEntry, SITUATION_POLICY
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.contracts.provenance import MemoryKindV1, MemoryItemStatus
from app.domains.memory.exceptions import MemoryCapacityReached, MemoryConflictError, MemoryScopeError
from app.domains.memory.models.batch import MemoryActivationEpoch
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import (
    MemorySituationManifest, MemorySituationReceipt, MemoryActivitySituationInfo, MemoryActivitySituationSource,
    MemorySituationProcessingSetting,
)
from app.domains.memory.repository.capacity import stored_count, STORAGE_LIMIT
from app.domains.memory.repository.situation_runs import require_run_fence
from app.domains.memory.repository.vector_eligibility import register_content


@dataclass(frozen=True)
class SituationSourceAccess:
    state: Literal["available", "deleted", "changed", "forbidden"]
    evidence: CanonicalMemoryEvidence | None = None


class SituationSourceValidator(Protocol):
    def validate(self, manifest: DeliveredInputManifest, source: DeliveredSourceEntry, *, now: datetime) -> SituationSourceAccess: ...


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
        MemorySituationReceipt.state == "pending",
    )
    cutoff_at = run.settings_snapshot.get("cutoff_at")
    if cutoff_at is not None:
        # Sequence bounds protect a frozen run from later arrivals; this time
        # bound also excludes captures after a missed daily due time.
        pending += (MemorySituationReceipt.captured_at <= utc_instant(datetime.fromisoformat(cutoff_at)),)
    rows = list(session.scalars(select(MemorySituationReceipt).where(*pending)
        .order_by(MemorySituationReceipt.sequence).limit(page_size)))
    available_slots = None
    changed_settings = set()
    for receipt in rows:
        stored = session.get(MemorySituationManifest, receipt.manifest_id)
        try:
            manifest = DeliveredInputManifest.from_dict(stored.payload)
            result_sources = tuple(DeliveredSourceEntry(**{**row, "ranges": tuple(tuple(pair) for pair in row.get("ranges", ()))})
                for row in receipt.result.get("result_sources", []))
        except (AttributeError, ValueError, TypeError, KeyError):
            receipt.state, receipt.error_code = "blocked", "situation_manifest_invalid"
            receipt.run_id, run.cursor = run.id, receipt.sequence
            run.blocked_count += 1
            continue
        snapshot = manifest.snapshot
        setting = memory.get_scope_setting(snapshot.scope)
        epoch = session.get(MemoryActivationEpoch, receipt.activation_epoch, populate_existing=True)
        if (setting is None or not setting.enabled or setting.version != receipt.scope_version
            or epoch is None or epoch.closed_at is not None or epoch.scope_setting_id != receipt.scope_setting_id):
            receipt.state, receipt.error_code = "skipped", "situation_activation_closed"
            run.skipped_count += 1
        elif receipt.policy_version != SITUATION_POLICY or receipt.description_status != "valid" or not receipt.description:
            receipt.state, receipt.error_code = "blocked", "situation_policy_or_description_invalid"
            run.blocked_count += 1
        else:
            try:
                memory.validate_scope(snapshot.scope)
            except MemoryScopeError:
                receipt.state, receipt.error_code = "skipped", "situation_scope_removed"
                receipt.run_id, run.cursor = run.id, receipt.sequence
                run.skipped_count += 1
                continue
            access = [(source, validator.validate(manifest, source, now=now)) for source in (*manifest.sources, *result_sources)]
            if (not access or any(value.state not in {"available", "deleted"}
                or (value.state == "deleted" and source.role == "prior") for source, value in access)):
                receipt.state, receipt.error_code = "blocked", "situation_source_changed_or_forbidden"
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
                receipt.state, receipt.applied_item_id, receipt.applied_at = "applied", item.id, now
                register_content(session, item, now=now)
                changed_settings.add(setting.id)
                run.applied_count += 1
        receipt.run_id = run.id
        run.cursor = receipt.sequence
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
