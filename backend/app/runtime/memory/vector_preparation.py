"""Explicit preparation enrolls and claims the same durable projection work."""
from app.core import work_observation as observation
from datetime import UTC, datetime
from sqlalchemy import select
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.models.activity_configuration import MemoryIndexPreparation
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.vector_work import MemoryVectorWork
from app.domains.memory.repository.index_preparation import advance
from app.domains.memory.repository import vector_queue as queue
from app.runtime.memory_embedding_provider import validate_embedding_credential
from app.runtime.memory.vector_proof import revisions

PAGE_SIZE = 20


def pending(projection):
    with projection._factory() as db:
        return tuple(db.scalars(select(MemoryIndexPreparation.scope_setting_id).where(
            MemoryIndexPreparation.state == "running").order_by(MemoryIndexPreparation.scope_setting_id).limit(4)))


def credential_proof(projection, setting_id):
    with projection._factory() as db:
        db.connection().exec_driver_sql("BEGIN")
        row = db.get(MemoryIndexPreparation, setting_id)
        setting = db.get(MemoryScopeSettingModel, setting_id)
        if row is None or setting is None or row.state != "running":
            return None
        scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
        epochs = revisions(db, (f"world:{scope.world_id}", f"owner:{scope.owner_id}"))
        try:
            valid = validate_embedding_credential(db, scope, revision=row.credential_revision) == row.credential_revision
        except (MemoryValidationError, ValueError):
            valid = False
        from app.domains.worlds.models_deletion import WorldDeletionRequest
        if db.scalar(select(WorldDeletionRequest.id).where(WorldDeletionRequest.world_id == scope.world_id)):
            return None
        return scope, row.revision, row.source_generation, row.credential_revision, epochs, valid


def enroll(projection, setting_id):
    proof = credential_proof(projection, setting_id)
    if proof is None:
        return None
    scope, request_revision, source_generation, credential, epochs, valid = proof
    with projection._factory() as db:
        def operation():
            row = db.get(MemoryIndexPreparation, setting_id)
            setting = db.get(MemoryScopeSettingModel, setting_id)
            if row is None or setting is None or row.state != "running" or (row.revision, row.source_generation) != (request_revision, source_generation):
                return None
            if revisions(db, (key for key, _ in epochs)) != epochs:
                return None
            if not valid:
                row.state, row.last_code = "error", "memory_embedding_preparation_changed"
                return None
            page = advance(db, row, now=datetime.now(UTC), limit=PAGE_SIZE)
            if row.state != "running":
                return None
            config = db.get(MemoryEmbeddingSetting, setting_id)
            snapshot = (row.revision, row.source_generation, row.cursor, setting.version, config.version)
            for item_id in page:
                work = db.get(MemoryVectorWork, (projection.generation, item_id))
                changed = work is not None and work.preparation_key != source_generation
                queue.enqueue(db, projection.generation, item_id, scope.world_id, force=changed)
                work = db.get(MemoryVectorWork, (projection.generation, item_id), populate_existing=True)
                work.preparation_key = source_generation
            db.flush()
            claims = queue.claim(db, projection.generation, page)
            return scope, page, snapshot, credential, claims
        return run_sqlite_session_immediate(db, operation, require_clean=True)


def finish(projection, setting_id, prepared, outcomes):
    scope, page, snapshot, revision, claims = prepared
    proof = credential_proof(projection, setting_id)
    if proof is None:
        return
    with projection._factory() as db:
        def operation():
            row = db.get(MemoryIndexPreparation, setting_id)
            if row is None or row.state != "running" or (row.revision, row.source_generation, row.cursor) != snapshot[:3]:
                return
            if revisions(db, (key for key, _ in proof[4])) != proof[4]:
                return
            setting = db.get(MemoryScopeSettingModel, setting_id)
            config = db.get(MemoryEmbeddingSetting, setting_id)
            valid = (proof[5] and proof[3] == revision and setting is not None and config is not None
                and setting.enabled and config.enabled and config.profile == row.profile
                and (setting.version, config.version) == snapshot[3:])
            if not valid:
                row.state, row.last_code = "error", "memory_embedding_preparation_changed"
            elif any(value in {"local_result_pending", "deferred", "changed"} for value in outcomes.values()):
                row.last_code = "memory_embedding_storage_pending"
            elif all(value in {"indexed", "current", "ineligible", "source_unavailable"} for value in outcomes.values()):
                row.cursor, row.last_code = page[-1] if page else row.cursor, None
                if len(page) < PAGE_SIZE:
                    row.state = "ready"
            else:
                row.state, row.last_code = "error", "memory_embedding_preparation_failed"
        run_sqlite_session_immediate(db, operation, require_clean=True)


@observation.observed("vector_preparation")
async def prepare_page(projection):
    from app.runtime.memory.vector_queue_worker import acknowledge
    for setting_id in await projection._canonical.call(pending, projection):
        prepared = await projection._canonical.call(enroll, projection, setting_id)
        if prepared is None:
            continue
        claims = prepared[4]
        projection._claims = {claim.item_id: claim for claim in claims}
        try:
            with observation.scope(purpose="document_preparation"):
                outcomes = await projection.sync_items(tuple(projection._claims), credential_revision=prepared[3])
            for claim in claims:
                await projection._canonical.call(acknowledge, projection, claim, outcomes[claim.item_id])
            with projection._factory() as db:
                for item_id in prepared[1]:
                    if item_id not in outcomes:
                        work = db.get(MemoryVectorWork, (projection.generation, item_id))
                        outcomes[item_id] = work.last_code if work and work.applied_revision == work.desired_revision else "deferred"
            await projection._canonical.call(finish, projection, setting_id, prepared, outcomes)
        finally:
            projection._claims.clear()
            projection._boundaries.clear()
            projection._attempt_keys.clear()
