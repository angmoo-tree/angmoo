"""Trigger identity and request-wide progress on the existing durable queue."""
from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4
from sqlalchemy import func, or_, select, update
from app.domains.memory.contracts.items import normalize_memory_idempotency_key
from app.domains.memory.exceptions import MemoryConflictError, MemoryNotFoundError, MemoryValidationError
from app.domains.memory.models.batch import MemoryBatchProfile, MemoryBatchSetting, MemoryBatchRun, MemorySourceDelivery, MemorySelectionDecisionModel
from app.domains.memory.models.items import MemoryCandidate, MemoryMaintenanceJob, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeBundle, MemoryEpisodeInfo
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest as Request, MemoryConsolidationJob as Link

ACTIVE = ("preparing", "queued")


def admit(session, *, setting, kind, key, now, digest="", scheduled_for=None, coalesce=False):
    # Serialize admission with settings changes and competing HTTP/scheduler requests.
    session.execute(update(MemoryBatchSetting).where(MemoryBatchSetting.scope_setting_id == setting.id)
                    .values(updated_at=MemoryBatchSetting.updated_at))
    old = session.scalar(select(Request).where(Request.scope_setting_id == setting.id, Request.idempotency_key == key))
    if old is not None:
        if old.request_digest != digest:
            raise MemoryConflictError("memory_request_replay_conflict")
        return old, "reused"
    setting = session.get(MemoryScopeSettingModel, setting.id)
    config = session.get(MemoryBatchSetting, setting.id)
    profile = session.get(MemoryBatchProfile, setting.owner_id)
    active = None
    if coalesce:
        for candidate in session.scalars(select(Request).where(Request.scope_setting_id == setting.id,
                Request.state.in_(ACTIVE), Request.coalesced_to_request_id.is_(None),
                Request.scope_version == setting.version, Request.settings_version == config.execution_version,
                Request.profile_version == profile.version).order_by(Request.accepted_at)):
            if progress(session, candidate)["state"] in ("preparing", "queued", "waiting_for_chat", "ai_running", "applying"):
                active = candidate
                break
    row = Request(id=uuid4().hex, scope_setting_id=setting.id, kind=kind, idempotency_key=key,
        request_digest=digest, scheduled_for_utc=scheduled_for, accepted_at=now,
        cutoff_sequence=int(session.scalar(select(func.max(MemorySourceDelivery.sequence)).where(
            MemorySourceDelivery.scope_setting_id == setting.id)) or 0),
        scope_version=setting.version, settings_version=config.execution_version, profile_version=profile.version,
        state="queued" if active else "preparing", coalesced_to_request_id=None if active is None else active.id)
    session.add(row)
    session.flush()
    return row, "already_active" if active else "accepted"


def manual(session, *, repository, scope, data, now):
    repository.memory.validate_scope(scope)
    setting = repository.memory.get_scope_setting(scope)
    if setting is None:
        raise MemoryValidationError("memory_disabled")
    session.execute(update(MemoryBatchSetting).where(MemoryBatchSetting.scope_setting_id == setting.id)
                    .values(updated_at=MemoryBatchSetting.updated_at))
    normalize_memory_idempotency_key(data.idempotency_key)
    receipt_key = "manual:" + hashlib.sha256(data.idempotency_key.encode()).hexdigest()
    digest = hashlib.sha256(json.dumps(data.model_dump(exclude={"idempotency_key"}), sort_keys=True).encode()).hexdigest()
    old = session.scalar(select(Request).where(Request.scope_setting_id == setting.id, Request.idempotency_key == receipt_key))
    if old is not None:
        if old.request_digest != digest:
            raise MemoryConflictError("memory_request_replay_conflict")
        return old, "reused"
    config = session.get(MemoryBatchSetting, setting.id)
    profile = session.get(MemoryBatchProfile, scope.owner_id)
    if config is None or profile is None or not setting.enabled or not config.ai_enabled or config.consent_version != "memory-selection-consent.v1":
        raise MemoryValidationError("memory_selection_consent_required")
    if (data.expected_version, data.expected_profile_version, data.expected_scope_version) != (config.version, profile.version, setting.version):
        raise MemoryConflictError("memory_batch_settings_version_conflict")
    if repository.settings(scope).capacity_blocked:
        raise MemoryConflictError("memory_capacity_reached")
    return admit(session, setting=setting, kind="manual", key=receipt_key, digest=digest, now=now, coalesce=True)


def find(session, *, setting_id, request_id=None):
    query = select(Request).where(Request.scope_setting_id == setting_id)
    if request_id:
        query = query.where(Request.id == request_id)
    else:
        for candidate in session.scalars(query.where(Request.state.in_(ACTIVE),
                Request.coalesced_to_request_id.is_(None)).order_by(Request.accepted_at.desc())):
            if progress(session, candidate)["state"] in ("preparing", "queued", "waiting_for_chat", "ai_running", "applying"):
                return candidate
    row = session.scalar(query.order_by(Request.accepted_at.desc()).limit(1))
    if row is None and request_id:
        raise MemoryNotFoundError("memory_request_not_found")
    return row


def has_manual_alias(session, request_id):
    return session.scalar(select(Request.id).where(Request.coalesced_to_request_id == request_id,
        Request.kind == "manual").limit(1)) is not None


def independently_requested_job(session, job_id):
    # A manual alias of a scheduled receipt is also an independent user request.
    return session.scalar(select(Request.id).select_from(Link).join(Request, or_(
        Request.id == Link.request_id, Request.coalesced_to_request_id == Link.request_id))
        .where(Link.job_id == job_id, Request.kind.in_(("manual", "shutdown"))).limit(1)) is not None


def progress(session, row):
    receipt = row
    if row.coalesced_to_request_id:
        row = session.get(Request, row.coalesced_to_request_id)
    jobs = session.execute(select(Link.job_id, Link.phase, MemoryMaintenanceJob.status, MemoryBatchRun.last_code)
        .join(MemoryMaintenanceJob, MemoryMaintenanceJob.id == Link.job_id)
        .join(MemoryBatchRun, MemoryBatchRun.job_id == Link.job_id).where(Link.request_id == row.id)).all()
    state = row.state
    if state not in ("cancelled", "paused"):
        states = [job.status for job in jobs]
        running = [job for job in jobs if job.status == "running"]
        if running:
            state = next((j.phase for j in running if j.phase in ("ai_running", "applying")), "queued")
        elif state == "preparing":
            pass
        elif "pending" in states:
            state = "waiting_for_chat" if any(j.last_code == "memory_foreground_deferred" for j in jobs) else "queued"
        elif "failed" in states:
            state = "partial_failed" if "succeeded" in states else "failed"
        elif "cancelled" in states:
            state = "cancelled"
        else:
            state = "completed" if jobs else "no_work"
    if state in ("preparing", "queued") and row.last_code == "memory_foreground_deferred":
        state = "waiting_for_chat"
    ids = [j.job_id for j in jobs]
    saved = int(session.scalar(select(func.count()).select_from(MemorySelectionDecisionModel).join(MemoryBatchRun, MemoryBatchRun.job_id == MemorySelectionDecisionModel.job_id).where(
        MemoryBatchRun.policy_version != "episode-selection.v1",
        MemorySelectionDecisionModel.job_id.in_(ids), MemorySelectionDecisionModel.decision == "retain")) or 0) if ids else 0
    # Prefix is the existing durable episode bundle identity, not a content scan.
    if ids:
        saved += int(session.scalar(select(func.count()).select_from(MemoryEpisodeInfo)
            .join(MemoryEpisodeBundle, MemoryEpisodeBundle.id == MemoryEpisodeInfo.bundle_id)
            .join(Link, MemoryEpisodeBundle.id.startswith(Link.job_id + ":"))
            .where(Link.request_id == row.id, MemoryEpisodeBundle.scope_setting_id == row.scope_setting_id)) or 0)
    remaining = int(session.scalar(select(func.count()).select_from(MemorySourceDelivery)
        .join(MemoryCandidate, MemoryCandidate.id == MemorySourceDelivery.candidate_id).where(
            MemorySourceDelivery.batch_job_id.in_(ids), MemoryCandidate.status == "pending")) or 0) if ids else 0
    return dict(request_id=receipt.id, effective_request_id=row.id, kind=receipt.kind,
        accepted_at=receipt.accepted_at, state=state, saved_count=saved, remaining_count=remaining,
        job_count=len(jobs), completed_job_count=sum(j.status == "succeeded" for j in jobs),
        last_code=row.last_code or next((j.last_code for j in jobs if j.last_code), None))


def set_phase(session, *, job_id, phase, now=None, work_id=None, call_number=None, lease_token=None):
    instant = now or datetime.now(UTC)
    job = session.get(MemoryMaintenanceJob, job_id)
    if job is None or job.status != "running" or (lease_token and job.lease_token != lease_token):
        return
    session.execute(update(Link).where(Link.job_id == job_id).values(phase=phase, phase_started_at=instant))
    if work_id:
        row = session.get(MemoryEpisodeBundle, work_id, populate_existing=True)
        value = json.loads(row.manifest_json)
        calls = value.get("calls", [])
        if len(calls) == call_number and calls[-1].get("outcome") == "in_flight":
            calls[-1]["provider_started_at" if phase == "ai_running" else "provider_finished_at"] = instant.isoformat()
            row.manifest_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
