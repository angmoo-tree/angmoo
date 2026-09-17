"""Bounded request preparation; HTTP never calls the selection provider."""
from datetime import UTC, datetime
from app.domains.memory.repository import consolidation_preparation as preparation
from app.domains.memory.repository import consolidation_requests as receipts
from app.domains.memory.service.batch_preparation import deliver_candidates, enqueue_scope


def submit(*, scope, db, workflows, data):
    try:
        repository = workflows.batch_repository(db)
        row, disposition = receipts.manual(db, repository=repository, scope=scope, data=data, now=datetime.now(UTC))
        if disposition == "accepted":
            workflows.validate_provider(db, scope.owner_id, preparation.profile_model(db, scope.owner_id))
        db.commit()
        return dict(scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
            disposition=disposition, **receipts.progress(db, row))
    except Exception:
        db.rollback()
        raise


def read(*, scope, db, workflows, request_id=None):
    repo = workflows.batch_repository(db)
    repo.memory.validate_scope(scope)
    setting = repo.memory.get_scope_setting(scope)
    row = receipts.find(db, setting_id=None if setting is None else setting.id, request_id=request_id)
    return dict(scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
        progress=None if row is None else receipts.progress(db, row))


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
        enqueue_scope(session, dependencies=dependencies, scope_setting_id=setting.id,
            trigger=row.kind, now=now, cutoff=row.cutoff_sequence, requested_at=row.accepted_at, request_id=row.id)
        remaining = preparation.attach_overlapping_and_count_remaining(session, row)
        if not more and not remaining:
            row.state = "queued"
        session.commit()
    preparation.cache_terminal_states(session, now=now)
    session.commit()
