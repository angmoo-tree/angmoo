"""Explicit index preparation uses the same delivery path as incremental work."""
from datetime import UTC, datetime
from sqlalchemy import select
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.models.activity_configuration import MemoryIndexPreparation
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.repository.index_preparation import advance
from app.runtime.memory_embedding_provider import validate_embedding_credential


def pending(projection):
    with projection._factory() as db:
        return tuple(db.scalars(select(MemoryIndexPreparation.scope_setting_id).where(
            MemoryIndexPreparation.state == "running").order_by(MemoryIndexPreparation.scope_setting_id).limit(4)))


def enroll(projection, setting_id):
    with projection._factory() as db:
        def operation():
            row = db.get(MemoryIndexPreparation, setting_id)
            setting = db.get(MemoryScopeSettingModel, setting_id)
            if row is None or setting is None or row.state != "running":
                return None
            scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
            try:
                validate_embedding_credential(db, scope, revision=row.credential_revision)
            except (MemoryValidationError, ValueError):
                row.state, row.last_code = "error", "memory_embedding_preparation_changed"
                return None
            page = advance(db, row, now=datetime.now(UTC))
            if row.state != "running":
                return None
            config = db.get(MemoryEmbeddingSetting, setting_id)
            snapshot = (row.revision, row.source_generation, row.cursor, setting.version, config.version)
            return scope, page, snapshot, row.credential_revision
        return run_sqlite_session_immediate(db, operation, require_clean=True)


def finish(projection, setting_id, prepared, outcomes):
    scope, page, snapshot, revision = prepared
    with projection._factory() as db:
        def operation():
            row = db.get(MemoryIndexPreparation, setting_id)
            if row is None or row.state != "running" or (row.revision, row.source_generation, row.cursor) != snapshot[:3]:
                return
            setting = db.get(MemoryScopeSettingModel, setting_id)
            config = db.get(MemoryEmbeddingSetting, setting_id)
            try:
                valid = (setting is not None and config is not None and setting.enabled and config.enabled
                    and config.profile == row.profile and (setting.version, config.version) == snapshot[3:]
                    and validate_embedding_credential(db, scope, revision=revision) == revision)
            except (MemoryValidationError, ValueError):
                valid = False
            if not valid:
                row.state, row.last_code = "error", "memory_embedding_preparation_changed"
            elif any(outcome in {"local_result_pending", "deferred"} for outcome in outcomes.values()):
                row.last_code = "memory_embedding_storage_pending"
            elif all(outcome in {"indexed", "current", "ineligible", "source_unavailable"} for outcome in outcomes.values()):
                row.cursor = page[-1] if page else row.cursor
                row.last_code = None
                if len(page) < 64:
                    row.state = "ready"
            else:
                row.state, row.last_code = "error", "memory_embedding_preparation_failed"
        run_sqlite_session_immediate(db, operation, require_clean=True)


async def prepare_page(projection):
    for setting_id in await projection._canonical.call(pending, projection):
        prepared = await projection._canonical.call(enroll, projection, setting_id)
        if prepared is None:
            continue
        outcomes = await projection.sync_items(prepared[1], credential_revision=prepared[3])
        await projection._canonical.call(finish, projection, setting_id, prepared, outcomes)
