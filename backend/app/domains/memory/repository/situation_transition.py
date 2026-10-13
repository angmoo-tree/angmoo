"""Explicit retirement of legacy work. Never runs from a schema migration."""
from dataclasses import dataclass
import json
from sqlalchemy import delete, func, select, update

from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
from app.domains.memory.contracts.activity_situation import SITUATION_POLICY
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.activity_situation import MemorySituationTransition
from app.domains.memory.models.batch import MemorySourceDelivery, MemoryBatchRun, MemoryActivationEpoch
from app.domains.memory.models.items import MemoryCandidate, MemoryMaintenanceJob, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeBundle, MemoryEpisodeInfo
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest, MemoryConsolidationJob


def retired(session, setting_id):
    return session.get(MemorySituationTransition, setting_id) is not None


def retire_admission(session, setting_id, *, now):
    row = session.get(MemorySituationTransition, setting_id)
    if row is None:
        cutoff = session.scalar(select(func.max(MemorySourceDelivery.sequence)).where(
            MemorySourceDelivery.scope_setting_id == setting_id)) or 0
        row = MemorySituationTransition(scope_setting_id=setting_id, policy_version=SITUATION_POLICY,
            admitted_after=now, legacy_cutoff=cutoff, discarded_job_ids=[])
        session.add(row)
        session.flush()
    return row


@dataclass(frozen=True)
class LegacyDiscardPlan:
    setting_id: str
    cutoff: int
    job_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    request_ids: tuple[str, ...] = ()


def inspect_discard(session, setting_id):
    cutoff = session.scalar(select(func.max(MemorySourceDelivery.sequence)).where(
        MemorySourceDelivery.scope_setting_id == setting_id)) or 0
    jobs = tuple(session.scalars(select(MemoryBatchRun.job_id).join(MemoryMaintenanceJob,
        MemoryMaintenanceJob.id == MemoryBatchRun.job_id).where(MemoryBatchRun.scope_setting_id == setting_id,
        MemoryBatchRun.policy_version == ACTIVITY_POLICY_VERSION,
        MemoryMaintenanceJob.status.in_(("pending", "failed", "running"))).order_by(MemoryBatchRun.job_id)))
    protected = {identifier for raw in session.scalars(select(MemoryBatchRun.candidate_ids_json).where(
        MemoryBatchRun.scope_setting_id == setting_id, MemoryBatchRun.job_id.not_in(jobs))) for identifier in json.loads(raw)}
    candidates = tuple(identifier for identifier in session.scalars(select(MemoryCandidate.id).join(
        MemorySourceDelivery, MemorySourceDelivery.candidate_id == MemoryCandidate.id).where(
        MemorySourceDelivery.scope_setting_id == setting_id, MemorySourceDelivery.sequence <= cutoff,
        MemoryCandidate.status == "pending").distinct().order_by(MemoryCandidate.id)) if identifier not in protected)
    requests = set(session.scalars(select(MemoryConsolidationRequest.id).where(
        MemoryConsolidationRequest.scope_setting_id == setting_id,
        MemoryConsolidationRequest.cutoff_sequence <= cutoff,
        MemoryConsolidationRequest.state.in_(("preparing", "queued", "paused", "failed", "partial_failed")))))
    requests.update(session.scalars(select(MemoryConsolidationJob.request_id).where(MemoryConsolidationJob.job_id.in_(jobs))))
    while requests:
        aliases = set(session.scalars(select(MemoryConsolidationRequest.id).where(
            MemoryConsolidationRequest.coalesced_to_request_id.in_(requests))))
        if aliases <= requests:
            break
        requests.update(aliases)
    # A request sharing completed/non-target work is historical provenance.
    requests -= set(session.scalars(select(MemoryConsolidationJob.request_id).where(
        MemoryConsolidationJob.request_id.in_(requests), MemoryConsolidationJob.job_id.not_in(jobs))))
    return LegacyDiscardPlan(setting_id, cutoff, jobs, candidates, tuple(sorted(requests)))


def discard_legacy(session, plan: LegacyDiscardPlan, *, request_key, now):
    """Caller owns commit; exact IDs and source cutoff are rechecked under a fence."""
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == plan.setting_id).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    transition = retire_admission(session, plan.setting_id, now=now)
    if transition.discard_key == request_key:
        return transition
    if transition.discard_key or inspect_discard(session, plan.setting_id) != plan:
        raise MemoryConflictError("situation_discard_inventory_changed")
    # Removing the job also removes its lease. Every legacy apply renews that
    # exact job/token before writing; the transition fence rejects late replies.
    bundles = list(session.scalars(select(MemoryEpisodeBundle).where(
        MemoryEpisodeBundle.scope_setting_id == plan.setting_id,
        MemoryEpisodeBundle.policy_version == ACTIVITY_POLICY_VERSION)))
    kept = set(session.scalars(select(MemoryEpisodeInfo.bundle_id)))
    for bundle in bundles:
        if bundle.id in kept:
            kept.add(json.loads(bundle.manifest_json).get("lineage_root", bundle.id))
    for bundle in bundles:
        data = json.loads(bundle.manifest_json)
        if data.get("job_id") in plan.job_ids and bundle.id not in kept and data.get("state") != "completed":
            session.delete(bundle)
    # Detach aliases before deleting their target. Relationship's owner removes
    # any exclusive follow-up requests in the same UoW before this function.
    session.execute(update(MemoryConsolidationRequest).where(
        MemoryConsolidationRequest.id.in_(plan.request_ids)).values(coalesced_to_request_id=None))
    session.execute(delete(MemoryConsolidationRequest).where(MemoryConsolidationRequest.id.in_(plan.request_ids)))
    session.execute(delete(MemoryMaintenanceJob).where(MemoryMaintenanceJob.id.in_(plan.job_ids)))
    session.execute(update(MemorySourceDelivery).where(MemorySourceDelivery.scope_setting_id == plan.setting_id,
        MemorySourceDelivery.sequence <= plan.cutoff).values(state="invalidated", reason_code="activity_situation_transition"))
    session.execute(delete(MemoryCandidate).where(MemoryCandidate.id.in_(plan.candidate_ids), MemoryCandidate.status == "pending"))
    session.execute(update(MemoryActivationEpoch).where(MemoryActivationEpoch.scope_setting_id == plan.setting_id).values(last_scanned_at=now))
    transition.legacy_cutoff, transition.discard_key = plan.cutoff, request_key
    transition.discarded_job_ids, transition.discarded_at = list(plan.job_ids), now
    session.flush()
    return transition
