"""Bounded request preparation; HTTP never calls the selection provider."""
from datetime import UTC, datetime
from app.domains.memory.repository import consolidation_preparation as preparation
from app.domains.memory.repository import consolidation_requests as receipts
from app.domains.memory.service.batch_preparation import deliver_candidates, enqueue_scope


def submit(*, scope, db, workflows, data):
    try:
        repository = workflows.batch_repository(db)
        row, disposition = receipts.manual(db, repository=repository, scope=scope, data=data, now=datetime.now(UTC))
        followup = workflows.consolidation_followup(db) if workflows.consolidation_followup else None
        if data.followup:
            if followup is None:
                from app.domains.memory.exceptions import MemoryValidationError
                raise MemoryValidationError("relationship_followup_unavailable")
            followup.admit(scope, row)
            if disposition == "accepted" and row.coalesced_to_request_id:
                disposition = "already_active"
        if disposition == "accepted" and not row.coalesced_to_request_id:
            workflows.validate_provider(db, scope.owner_id, preparation.profile_model(db, scope.owner_id))
        db.commit()
        value = receipts.progress(db, row)
        if followup:
            value = followup.extend(row, value)
        return dict(scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
            disposition=disposition, **value)
    except Exception:
        db.rollback()
        raise


def read(*, scope, db, workflows, request_id=None):
    repo = workflows.batch_repository(db)
    repo.memory.validate_scope(scope)
    setting = repo.memory.get_scope_setting(scope)
    followup = workflows.consolidation_followup(db) if workflows.consolidation_followup else None
    row = followup.active(setting.id) if followup and setting and not request_id else None
    row = row or receipts.find(db, setting_id=None if setting is None else setting.id, request_id=request_id)
    value = None if row is None else receipts.progress(db, row)
    if row is not None and followup:
        value = followup.extend(row, value)
    return dict(scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
        progress=value, capability=followup.capability(scope) if followup else {"relationships": False, "reason": "unsupported"})


def prepare_requests(session, *, dependencies, now):
    for row in preparation.pending_requests(session):
        setting, config, profile = preparation.request_context(session, row)
        if (not setting.enabled or config is None or profile is None or not config.ai_enabled
                or setting.version != row.scope_version or config.execution_version != row.settings_version
                or profile.version != row.profile_version):
            row.state, row.last_code = "paused", "memory_request_settings_changed"
            continue
        if row.kind == "scheduled" and not config.schedule_enabled and not receipts.has_manual_alias(session, row.id):
            row.state, row.last_code, row.completed_at = "cancelled", "memory_schedule_disabled", now
            continue
        row.last_code = None
        more = preparation.recover_request(session, row=row, setting=setting, source_catalog_factory=dependencies.source_catalog_factory)
        # Delivery commits bounded work. A crash leaves the original request
        # preparing and the anti-join resumes only missing sources next tick.
        deliver_candidates(session, dependencies=dependencies)
        from app.domains.memory.contracts.scope import MemoryScope
        scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
        repository = dependencies.batch_repository(session)
        from app.domains.memory.exceptions import MemoryScopeError
        try:
            capacity_blocked = repository.settings(scope).capacity_blocked
        except MemoryScopeError:
            row.state, row.last_code = "paused", "memory_scope_invalid"
            session.commit()
            continue
        if capacity_blocked:
            # Recovery must finish before declaring no work. Never admit new
            # generation when storage is full, but allow a genuine empty stage.
            from sqlalchemy import select, exists, or_
            from app.domains.memory.models.items import MemoryCandidate
            from app.domains.memory.models.batch import MemorySourceDelivery
            pending = session.scalar(select(exists().where(
                MemorySourceDelivery.scope_setting_id == setting.id,
                MemorySourceDelivery.candidate_id == MemoryCandidate.id,
                MemoryCandidate.status == "pending",
                or_(MemorySourceDelivery.sequence <= row.cutoff_sequence,
                    MemorySourceDelivery.captured_at <= row.accepted_at))))
            if pending:
                row.state, row.last_code = "paused", "memory_capacity_reached"
                session.commit()
                continue
        enqueue_scope(session, dependencies=dependencies, scope_setting_id=setting.id,
            trigger=row.kind, now=now, cutoff=row.cutoff_sequence, requested_at=row.accepted_at, request_id=row.id)
        remaining = preparation.attach_overlapping_and_count_remaining(session, row)
        if not more and not remaining:
            row.state = "queued"
        session.commit()
    preparation.cache_terminal_states(session, now=now)
    session.commit()


def retry(*, scope, db, workflows, request_id, key):
    repo = workflows.batch_repository(db)
    repo.memory.validate_scope(scope)
    setting = repo.memory.get_scope_setting(scope)
    row = receipts.find(db, setting_id=None if setting is None else setting.id, request_id=request_id)
    try:
        root = db.get(type(row), row.coalesced_to_request_id) if row.coalesced_to_request_id else row
        from sqlalchemy import select
        from app.domains.memory.models.consolidation_request import MemoryConsolidationJob
        jobs = tuple(db.scalars(select(MemoryConsolidationJob.job_id).where(MemoryConsolidationJob.request_id == root.id)))
        repo.retry_failed(scope, idempotency_key=key, now=datetime.now(UTC), request_job_ids=jobs)
        if root.state == "paused":
            # Re-admit the same frozen cutoff against explicitly confirmed current settings.
            from app.domains.memory.models.batch import MemoryBatchSetting, MemoryBatchProfile
            config = db.get(MemoryBatchSetting, setting.id)
            profile = db.get(MemoryBatchProfile, setting.owner_id)
            root.scope_version, root.settings_version, root.profile_version = setting.version, config.execution_version, profile.version
            root.state, root.last_code = "preparing", None
        if workflows.consolidation_followup:
            workflows.consolidation_followup(db).retry(scope, row)
        db.commit()
        return read(scope=scope, db=db, workflows=workflows, request_id=request_id)
    except Exception:
        db.rollback()
        raise
