"""Bounded SQL for request preparation; the service owns commit and scheduling."""
from sqlalchemy import func, or_, select
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest as Request, MemoryConsolidationJob as Link
from app.domains.memory.models.batch import MemoryActivationEpoch, MemoryBatchProfile, MemoryBatchSetting, MemorySourceDelivery
from app.domains.memory.models.items import MemoryCandidate, MemoryMaintenanceJob, MemoryScopeSettingModel
from app.domains.memory.repository.reconciliation import recover_catalog
from app.domains.memory.repository.consolidation_requests import progress


def pending_requests(session):
    return session.scalars(select(Request).where(Request.state == "preparing", Request.coalesced_to_request_id.is_(None))
        .order_by(Request.accepted_at).limit(16)).all()


def request_context(session, row):
    setting = session.get(MemoryScopeSettingModel, row.scope_setting_id)
    config = session.get(MemoryBatchSetting, row.scope_setting_id)
    profile = session.get(MemoryBatchProfile, setting.owner_id)
    return setting, config, profile


def profile_model(session, owner_id):
    return session.get(MemoryBatchProfile, owner_id).model_id


def recover_request(session, *, row, setting, source_catalog_factory):
    more = False
    for epoch in session.scalars(select(MemoryActivationEpoch).where(
            MemoryActivationEpoch.scope_setting_id == setting.id, MemoryActivationEpoch.opened_at <= row.accepted_at)):
        for catalog in source_catalog_factory()(setting, setting.subject_world_character_id):
            more |= recover_catalog(session, setting=setting, epoch=epoch, catalog=catalog, before=row.accepted_at) == 32
    session.flush()
    return more


def attach_overlapping_and_count_remaining(session, row):
    boundary = or_(MemorySourceDelivery.sequence <= row.cutoff_sequence, MemorySourceDelivery.captured_at <= row.accepted_at)
    for job in session.scalars(select(MemorySourceDelivery.batch_job_id).join(
            MemoryMaintenanceJob, MemoryMaintenanceJob.id == MemorySourceDelivery.batch_job_id).where(
                MemorySourceDelivery.scope_setting_id == row.scope_setting_id, boundary,
                MemoryMaintenanceJob.status.in_(("pending", "running"))).distinct()):
        if session.get(Link, (row.id, job)) is None:
            session.add(Link(request_id=row.id, job_id=job, phase="queued"))
    return session.scalar(select(func.count()).select_from(MemorySourceDelivery).outerjoin(
        MemoryCandidate, MemoryCandidate.id == MemorySourceDelivery.candidate_id).where(
            MemorySourceDelivery.scope_setting_id == row.scope_setting_id, boundary, MemorySourceDelivery.batch_job_id.is_(None),
            or_(MemorySourceDelivery.state == "pending", MemoryCandidate.status == "pending"))) or 0


def cache_terminal_states(session, *, now):
    for row in session.scalars(select(Request).where(Request.state == "queued", Request.coalesced_to_request_id.is_(None)).limit(64)):
        if row.last_code == "memory_foreground_deferred":
            row.last_code = None
        state = progress(session, row)["state"]
        if state in ("completed", "no_work", "partial_failed", "failed", "cancelled"):
            row.state, row.completed_at = state, now
